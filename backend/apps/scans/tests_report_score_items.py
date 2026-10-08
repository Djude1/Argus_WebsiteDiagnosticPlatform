"""PDF 報告附錄的各分類扣分明細（roadmap 優先序第 4 項：報告內的逐項扣分）。

與網頁「分數說明」分頁同一份資料（score_explain.py）；保存的分數依目前公式加不回來時
不列明細、只說明原因。
"""

from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from docx import Document
from jsonschema import Draft7Validator

from apps.scans.models import Finding, ScanJob
from apps.scans.reports import build_report_payload, render_report_docx

User = get_user_model()
SCHEMA = json.loads(
    (Path(__file__).resolve().parent / "report_render" / "schema.json").read_text("utf-8")
)


class ReportScoreItemsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="score-items", password="safe-test-password")
        self.scan_job = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="example.com",
            status=ScanJob.Status.COMPLETED, completed_at=timezone.now(),
        )
        self._finding("seo", "medium", "seo-a", "標題太短")
        self._finding("seo", "medium", "seo-a", "標題太短")
        self._finding("seo", "low", "seo-b", "缺少 alt")
        self._finding("security", "info", "sec-waf", "位於 WAF 之後")
        # 依目前公式：SEO 扣 16 → 73；資安只有資訊提示 → 100
        self.scan_job.category_scores = {"seo": 73, "security": 100}
        self.scan_job.overall_score = 87
        self.scan_job.save()

    def _finding(self, category, severity, rule_id, title):
        Finding.objects.create(
            scan_job=self.scan_job, page=None, category=category, severity=severity,
            title=title, description="d", remediation="r", rule_id=rule_id,
            ai_handoff_prompt="p", priority_score=10,
        )

    def test_payload_lists_deductions_with_refs_and_matches_schema(self):
        payload = build_report_payload(self.scan_job)
        errors = list(Draft7Validator(SCHEMA).iter_errors(payload))
        self.assertEqual(errors, [])

        seo, security = payload["appendix"]["score_items"]["categories"]
        self.assertEqual((seo["name"], seo["score"], seo["basis"]),
                         ("SEO 搜尋引擎最佳化", 73, "起始分 100"))
        first = seo["items"][0]
        self.assertEqual(
            (first["title"], first["severity"], first["weight"], first["occurrences"]),
            ("標題太短", "中風險", 12, 2),
        )
        self.assertEqual(first["score_without"], 92)
        # 項次對回第 4 章的卡片編號
        refs = {f["title"]: f["id"] for f in payload["findings"]}
        self.assertEqual(first["ref"], refs["標題太短"])
        self.assertEqual(security["items"], [])
        self.assertEqual(security["notes"], "1 筆資訊提示不扣分")

    def test_aeo_basis_names_answerability(self):
        self.scan_job.aeo_report = {"status": "evaluated", "score": 80}
        self.scan_job.category_scores = {**self.scan_job.category_scores, "aeo": 80}
        self.scan_job.save()
        self._finding("aeo", "medium", "aeo-answer-missing", "問題「電話」：找不到")
        categories = build_report_payload(self.scan_job)["appendix"]["score_items"]["categories"]
        aeo = next(c for c in categories if c["name"].startswith("AEO"))
        self.assertIn("起始分 80（可回答性分數", aeo["basis"])
        self.assertEqual(aeo["notes"], "1 筆問答檢測結果已計入起始分")

    def test_scores_from_older_formula_only_explain(self):
        self.scan_job.category_scores = {"seo": 70, "security": 100}
        self.scan_job.save()
        score_items = build_report_payload(self.scan_job)["appendix"]["score_items"]
        self.assertNotIn("categories", score_items)
        self.assertIn("舊版計分公式", score_items["note"])

    def test_unscored_scan_has_no_section(self):
        self.scan_job.category_scores = {}
        self.scan_job.save()
        self.assertNotIn("score_items", build_report_payload(self.scan_job)["appendix"])

    def test_rendered_report_has_the_table(self):
        document = Document(render_report_docx(self.scan_job))
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("各分類扣分明細", text)
        self.assertIn("SEO 搜尋引擎最佳化　73 分", text)
        cells = {cell.text for table in document.tables for row in table.rows for cell in row.cells}
        self.assertTrue({"只修好這項時", "−12", "92 分"} <= cells)
