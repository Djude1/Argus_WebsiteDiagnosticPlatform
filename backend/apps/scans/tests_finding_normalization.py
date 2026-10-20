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

    def test_scanner_egress_ip_observation_downgraded_on_renormalize(self):
        # 部署後設定 ARGUS_SCANNER_EGRESS_IPS，重算既有掃描就能把誤報降為資訊提示
        self._finding(
            rule_id="agent-observed-security-a76d654edb", severity="medium",
            title="WAF 攔截頁面洩漏後端伺服器內部 IP 與時間戳記",
            description="AI Agent 在實際操作網站時觀察到：攔截頁內嵌 IP 211.75.1.199",
            evidence="<div class=\"waferr\">211.75.1.199<br>2026-10-19 18:42:26</div>",
        )
        with self.settings(ARGUS_SCANNER_EGRESS_IPS=["211.75.1.199"]):
            counts = renormalize_scan(self.scan)
        self.assertEqual(counts["agent"], 1)
        finding = self.scan.findings.get()
        self.assertEqual(finding.severity, "info")
        self.assertIn("掃描器自己的出口位址", finding.description)
        # 再跑一次不重複附註
        with self.settings(ARGUS_SCANNER_EGRESS_IPS=["211.75.1.199"]):
            renormalize_scan(self.scan)
        self.assertEqual(self.scan.findings.get().description.count("掃描器自己的出口位址"), 1)

    def test_legacy_agent_rule_rekeyed_and_rescored(self):
        # 2026-10-16（migration 0035）：舊版所有 Agent 觀察共用代號，優先處理只留第一筆
        import importlib

        from django.apps import apps as django_apps

        migration = importlib.import_module(
            "apps.scans.migrations.0035_rekey_agent_security_findings"
        )
        self.scan.top_actions = [{"title": "API 規格公開（中）", "severity": "medium"}]
        self.scan.save(update_fields=["top_actions"])
        legacy = dict(rule_id="agent-observed-security", evidence_json={})
        self._finding(
            **legacy, severity="medium", priority_score=55.0,
            title="完整 OpenAPI/Swagger 規格公開暴露（含內部 IP 位址）",
            description="AI Agent 在實際操作網站時觀察到：規格公開"
            "（觀察端點：https://example.com/swagger (or /openapi.json)）",
        )
        self._finding(
            rule_id="agent-observed-security", severity="critical", priority_score=90.0,
            evidence_json={"tool_verified": True},
            title="完整 OpenAPI / Swagger 規格公開暴露（含內部 IP）",
            description="AI Agent 在實際操作網站時觀察到：規格公開"
            "（觀察端點：https://example.com/api_proxy/v3/api-docs）",
        )
        self._finding(
            **legacy, severity="low", title="上傳的檔案可被直接讀取",
            description="AI Agent 在實際操作網站時觀察到：上傳後可讀（觀察端點：https://example.com/upload）",
        )

        migration.rekey(django_apps, None)

        rules = dict(self.scan.findings.values_list("title", "rule_id"))
        self.assertFalse(any(rule == "agent-observed-security" for rule in rules.values()))
        swagger_rules = {r for t, r in rules.items() if "Swagger" in t}
        self.assertEqual(len(swagger_rules), 1, "同一個問題的兩次回報要共用代號")
        self.assertNotIn(rules["上傳的檔案可被直接讀取"], swagger_rules)
        self.assertEqual(self.scan.findings.count(), 3, "只改代號，不刪發現")
        self.scan.refresh_from_db()
        # ADR-0006 決策 C：Agent 觀察不進基準分與優先處理，改以 agent_findings_summary 獨立呈現
        self.assertEqual(self.scan.top_actions, [])
        self.assertEqual(self.scan.agent_findings_summary["count"], 3)
        self.assertEqual(self.scan.agent_findings_summary["max_severity"], "critical")
        self.assertEqual(self.scan.agent_findings_summary["severity_counts"]["critical"], 1)
        # 再跑一次沒有東西可改
        migration.rekey(django_apps, None)
        self.assertEqual(dict(self.scan.findings.values_list("title", "rule_id")), rules)

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
        self.assertEqual(
            renormalize_scan(self.scan), {"pii": 0, "agent": 0, "agent_rule": 0, "cookie": 0}
        )

    def test_command_reports_changed_scan(self):
        out = StringIO()
        self._finding(page=self.page, rule_id=LEGACY_PII_RULE)
        call_command("renormalize_findings", "--scan-id", str(self.scan.pk), stdout=out)
        self.assertIn(f"scan {self.scan.pk}", out.getvalue())
