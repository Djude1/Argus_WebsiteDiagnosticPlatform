"""既有掃描套用新版判定並重算分數（apps/scans/finding_normalization.py）。"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.scans.finding_normalization import LEGACY_PII_RULE, renormalize_scan
from apps.scans.models import Finding, Page, ScanJob


class RenormalizeFindingsTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="renorm", password="safe-test-password"
        )
        self.scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", status=ScanJob.Status.COMPLETED, overall_score=10,
            category_scores={"security": 10, "seo": 100},
        )
        self.page = Page.objects.create(
            scan_job=self.scan, url="https://example.com/", final_url="https://example.com/",
            origin="https://example.com", status_code=200,
            html=(
                '<html><body><a href="mailto:service@example.com">'
                "service@example.com</a></body></html>"
            ),
        )

    def _finding(self, **kw):
        base = dict(
            scan_job=self.scan, page=None, severity="high", category=Finding.Category.SECURITY,
            title="t", description="d", remediation="r", evidence="e", rule_id="r",
            ai_handoff_prompt="p", priority_score=10.0,
        )
        base.update(kw)
        return Finding.objects.create(**base)

    def test_legacy_pii_is_rechecked_with_current_rules(self):
        self._finding(page=self.page, rule_id=LEGACY_PII_RULE, title="頁面外洩個人資料 (PII)")
        counts = renormalize_scan(self.scan)
        self.assertEqual(counts["pii"], 1)
        rules = list(self.scan.findings.values_list("rule_id", "severity"))
        self.assertEqual(rules, [("security-pii-public-contact", "info")])
        self.scan.refresh_from_db()
        # 唯一的高風險被降為資訊提示後，資安分數回到滿分
        self.assertEqual(self.scan.category_scores["security"], 100)
        self.assertGreater(self.scan.overall_score, 10)

    def test_agent_observation_is_capped_with_ip_notes(self):
        self._finding(
            rule_id="agent-observed-security", evidence="WAF page shows 10.0.0.8",
            description="Hermes-Agent 在實際操作與 probe 觀察中發現：頁面顯示 IP",
        )
        with patch("apps.scans.security.ip_context._resolve", return_value=set()):
            counts = renormalize_scan(self.scan)
        self.assertEqual(counts["agent"], 1)
        finding = self.scan.findings.get()
        self.assertEqual(finding.severity, "medium")
        self.assertIn("AI Agent 在實際操作網站時觀察到", finding.description)
        self.assertIn("10.0.0.8", finding.description)
        self.assertIn("未經工具或人工驗證", finding.description)

    def test_cookie_value_is_masked(self):
        self._finding(
            rule_id="cookie-no-secure", severity="medium",
            evidence="TS01abcd=0123456789abcdef0123; Path=/",
        )
        renormalize_scan(self.scan)
        evidence = self.scan.findings.get().evidence
        self.assertNotIn("0123456789abcdef0123", evidence)
        self.assertIn("已遮蔽", evidence)

    def test_second_run_changes_nothing(self):
        self._finding(page=self.page, rule_id=LEGACY_PII_RULE)
        renormalize_scan(self.scan)
        self.assertEqual(renormalize_scan(self.scan), {"pii": 0, "agent": 0, "cookie": 0})

    def test_command_reports_changed_scan(self):
        out = StringIO()
        self._finding(page=self.page, rule_id=LEGACY_PII_RULE)
        call_command("renormalize_findings", "--scan-id", str(self.scan.pk), stdout=out)
        self.assertIn(f"scan {self.scan.pk}", out.getvalue())
