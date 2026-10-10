"""分數說明：score_breakdown() 與 /api/scans/<id>/score-breakdown/（roadmap §12 第 3 項）。"""

from __future__ import annotations

import math

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.scans.models import Finding, ScanJob
from apps.scans.scanners import SCORE_DECAY_CONSTANT, calculate_scores, score_breakdown

User = get_user_model()


def _f(category, severity, rule_id, title=None):
    return {"category": category, "severity": severity, "rule_id": rule_id,
            "title": title or rule_id, "priority_score": 10}


class ScoreBreakdownTests(SimpleTestCase):
    def test_matches_calculate_scores(self):
        findings = [
            _f("seo", "medium", "seo-a"), _f("seo", "medium", "seo-a"), _f("seo", "low", "seo-b"),
            _f("security", "high", "sec-a"), _f("security", "info", "sec-waf"),
            _f("aeo", "medium", "aeo-answer-1"), _f("aeo", "low", "aeo-noindex"),
        ]
        tested = {"seo", "security", "aeo", "geo"}
        base = {"aeo": 70}
        _, category_scores, _ = calculate_scores(
            findings, tested_categories=tested, base_scores=base
        )
        breakdown = score_breakdown(findings, tested_categories=tested, base_scores=base)
        self.assertEqual({c: e["score"] for c, e in breakdown.items()}, category_scores)
        self.assertNotIn("ux", breakdown)

    def test_deductions_count_each_rule_once_with_occurrences(self):
        findings = [_f("seo", "medium", "seo-a")] * 3 + [_f("seo", "low", "seo-b")]
        seo = score_breakdown(findings)["seo"]
        self.assertEqual(seo["penalty"], 16)
        self.assertEqual(
            [(d["rule_id"], d["weight"], d["occurrences"]) for d in seo["deductions"]],
            [("seo-a", 12, 3), ("seo-b", 4, 1)],
        )
        # 只修好 seo-a：剩下 4 點權重
        self.assertEqual(
            seo["deductions"][0]["score_without"],
            round(100 * math.exp(-4 / SCORE_DECAY_CONSTANT)),
        )

    def test_info_and_base_scored_findings_do_not_deduct(self):
        findings = [
            _f("aeo", "medium", "aeo-answer-1"), _f("aeo", "medium", "aeo-answer-2"),
            _f("aeo", "info", "aeo-llms"),
        ]
        aeo = score_breakdown(findings, base_scores={"aeo": 80})["aeo"]
        self.assertEqual(aeo["score"], 80)
        self.assertEqual(aeo["base_source"], "aeo_answerability")
        self.assertEqual((aeo["in_base"], aeo["info"], aeo["deductions"]), (2, 1, []))

    def test_without_base_score_aeo_answer_findings_deduct(self):
        aeo = score_breakdown([_f("aeo", "medium", "aeo-answer-1")])["aeo"]
        self.assertEqual((aeo["base"], aeo["base_source"], aeo["penalty"]), (100, "", 12))


class ScoreBreakdownEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="explain", password="safe-test-password")
        self.scan_job = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="example.com",
            status=ScanJob.Status.COMPLETED, completed_at=timezone.now(),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _finding(self, category, severity, rule_id):
        Finding.objects.create(
            scan_job=self.scan_job, page=None, category=category, severity=severity,
            title=rule_id, description="d", remediation="r", rule_id=rule_id,
            ai_handoff_prompt="p", priority_score=10,
        )

    def _get(self):
        response = self.client.get(f"/api/scans/{self.scan_job.id}/score-breakdown/")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_explains_stored_scores_with_coverage(self):
        self._finding("seo", "medium", "seo-a")
        self._finding("seo", "medium", "seo-a")
        self._finding("security", "high", "sec-a")
        self.scan_job.category_scores = {"seo": 89, "security": 70}
        self.scan_job.overall_score = 80
        self.scan_job.coverage = {
            "version": 1,
            "checks": {"nuclei": {"status": "failed", "category": "security",
                                  "reason": "TimeoutError", "keys": []}},
            "categories": {"seo": "completed", "security": "partial"},
        }
        self.scan_job.save()

        data = self._get()

        self.assertTrue(data["available"])
        self.assertTrue(data["matches"])
        self.assertEqual([c["category"] for c in data["categories"]], ["seo", "security"])
        seo, security = data["categories"]
        self.assertEqual(seo["deductions"][0]["occurrences"], 2)
        self.assertEqual(security["coverage"], "partial")
        self.assertEqual(security["incomplete_checks"], ["Nuclei 主動弱點掃描"])
        self.assertEqual(seo["incomplete_checks"], [])

    def test_flags_scores_computed_by_an_older_formula(self):
        self._finding("seo", "low", "seo-a")
        self.scan_job.category_scores = {"seo": 94}  # 舊公式算出的數字
        self.scan_job.save()
        data = self._get()
        self.assertFalse(data["matches"])
        seo = data["categories"][0]
        self.assertEqual((seo["score"], seo["recomputed_score"]), (94, 96))

    def test_unscored_scan_is_not_available(self):
        self.assertEqual(self._get()["categories"], [])
        self.assertFalse(self._get()["available"])

    def test_other_users_cannot_read(self):
        other = User.objects.create_user(username="other", password="safe-test-password")
        self.client.force_authenticate(user=other)
        response = self.client.get(f"/api/scans/{self.scan_job.id}/score-breakdown/")
        self.assertEqual(response.status_code, 404)
