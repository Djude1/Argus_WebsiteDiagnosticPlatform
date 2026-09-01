"""report_render 的輸入契約測試。

排版改由 vendored 的 report_render 負責後，本模組的職責變成「產生正確的 payload」。
payload 若不符合 schema，錯誤會在排版階段以難懂的 KeyError 爆出來，所以直接對
report_render/schema.json 驗證。
"""

from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from jsonschema import Draft7Validator

from apps.scans.models import AuthorizationConsent, Finding, Page, ScanJob
from apps.scans.reports import build_report_payload

User = get_user_model()
SCHEMA = json.loads(
    (Path(__file__).resolve().parent / "report_render" / "schema.json").read_text("utf-8")
)


class ReportPayloadSchemaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="payload", password="safe-test-password")
        self.scan_job = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="example.com",
            status=ScanJob.Status.COMPLETED, overall_score=65,
            category_scores={"seo": 70, "security": 39, "geo": 59, "aeo": 100},
            top_actions=[{"title": "缺少 HSTS", "category": "security", "severity": "high"}],
            completed_at=timezone.now(),
        )
        page = Page.objects.create(
            scan_job=self.scan_job, url="https://example.com/a",
            final_url="https://example.com/a", origin="example.com", depth=0,
        )
        Finding.objects.create(
            scan_job=self.scan_job, page=page, severity="high",
            category=Finding.Category.SECURITY, title="缺少 HSTS",
            description="回應未帶 Strict-Transport-Security。",
            remediation="於 web server 加上 HSTS 標頭。",
            evidence="查無 strict-transport-security", rule_id="header-hsts-missing",
            owasp_category="A05", cwe_id="CWE-319",
            ai_handoff_prompt="p", priority_score=75.0,
        )

    def _payload(self) -> dict:
        return build_report_payload(self.scan_job)

    def _assert_valid(self, payload: dict) -> None:
        errors = sorted(Draft7Validator(SCHEMA).iter_errors(payload), key=lambda e: e.path)
        self.assertEqual(
            errors, [], "payload 不符合 schema：" + "; ".join(
                f"{list(e.path)}: {e.message}" for e in errors
            ),
        )

    def test_payload_matches_schema(self):
        self._assert_valid(self._payload())

    def test_payload_valid_with_no_findings(self):
        self.scan_job.findings.all().delete()
        self.scan_job.top_actions = []
        self.scan_job.save(update_fields=["top_actions"])

        self._assert_valid(self._payload())

    def test_payload_valid_with_previous_scan_and_consent(self):
        ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="example.com",
            status=ScanJob.Status.COMPLETED, overall_score=39,
            completed_at=timezone.now() - timezone.timedelta(days=7),
        )
        AuthorizationConsent.objects.create(
            scan_job=self.scan_job, user=self.user, ip_address="203.0.113.9",
            user_agent="Mozilla/5.0", authorized_domain="example.com",
            statement="本人確認擁有 example.com 的管理權限。",
        )

        payload = self._payload()

        self._assert_valid(payload)
        self.assertEqual(payload["summary"]["previous"]["score"], 39)

    def test_unevaluated_category_is_null_not_missing(self):
        """未評估要送 null——report_render 才會標「未評估」且不計顏色。

        送 0 的話會被畫成一條紅色滿分條，把「沒測」說成「很糟」。
        """
        categories = {c["name"]: c["score"] for c in self._payload()["summary"]["categories"]}

        self.assertEqual(len(categories), 5)
        self.assertIsNone(categories["使用者體驗"])

    def test_findings_are_numbered_in_severity_order(self):
        """report_render 依嚴重度分組顯示，編號必須先排好才會連續。"""
        for index, severity in enumerate(["low", "critical", "medium"]):
            Finding.objects.create(
                scan_job=self.scan_job, page=None, severity=severity,
                category=Finding.Category.SEO, title=f"問題 {severity}",
                description="d", remediation="r", rule_id=f"r-{index}",
                ai_handoff_prompt="p", priority_score=10.0,
            )

        findings = self._payload()["findings"]

        self.assertEqual([f["id"] for f in findings], ["4.1", "4.2", "4.3", "4.4"])
        self.assertEqual(findings[0]["severity"], "嚴重風險")
        self.assertEqual(findings[-1]["severity"], "低風險")

    def test_authorization_never_leaks_ip_or_user_agent(self):
        AuthorizationConsent.objects.create(
            scan_job=self.scan_job, user=self.user, ip_address="203.0.113.9",
            user_agent="Mozilla/5.0 (TestAgent)", authorized_domain="example.com",
            statement="授權聲明",
        )

        payload = json.dumps(self._payload(), ensure_ascii=False)

        self.assertNotIn("203.0.113.9", payload)
        self.assertNotIn("TestAgent", payload)
        self.assertNotIn(self.user.username, payload)

    def test_evidence_is_pii_masked(self):
        self.scan_job.findings.update(evidence="台灣手機：0912345678")

        payload = json.dumps(self._payload(), ensure_ascii=False)

        self.assertNotIn("0912345678", payload)

    def test_internal_billing_error_is_not_exposed(self):
        self.scan_job.warning_summary = {"settlement_error": "CoinWalletDoesNotExist"}
        self.scan_job.save(update_fields=["warning_summary"])

        self.assertNotIn("CoinWalletDoesNotExist", json.dumps(self._payload(), ensure_ascii=False))
