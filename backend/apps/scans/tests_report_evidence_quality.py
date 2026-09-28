"""報告的證據品質（2026-09-28 報告審查）：

- 高風險與 AI 觀察項目交代成立條件、實際觀察、尚缺證據、驗證方法；AI 觀察以中風險為上限
- 掃描範圍講清楚已檢查幾頁、是否達上限、被擋或錯誤幾頁、哪些檢查沒跑
- 合併多頁時保留每一頁自己的證據；Cookie 值遮蔽
- 修補驗證與原問題一一對應，並提醒「重掃沒出現」不等於修好
- 內容類建議附規則依據與適用限制；逐項標示來源（規則／工具／AI）
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.scans.models import AuthorizationConsent, Finding, Page, ScanJob
from apps.scans.reports import build_report_payload


class ReportEvidenceQualityTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="evq", password="safe-test-password")
        self.user = user
        self.scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", status=ScanJob.Status.COMPLETED, overall_score=70,
            category_scores={"security": 60, "geo": 80}, max_pages=2, max_depth=2,
            completed_at=timezone.now(),
        )
        self.p1 = Page.objects.create(
            scan_job=self.scan, url="https://example.com/a", final_url="https://example.com/a",
            origin="https://example.com", status_code=200,
        )
        self.p2 = Page.objects.create(
            scan_job=self.scan, url="https://example.com/b", final_url="https://example.com/b",
            origin="https://example.com", status_code=200,
        )

    def _finding(self, **kw):
        base = dict(
            scan_job=self.scan, page=None, severity="low", category=Finding.Category.SEO,
            title="t", description="d", remediation="r", evidence="e", rule_id="r",
            ai_handoff_prompt="p", priority_score=10.0,
        )
        base.update(kw)
        return Finding.objects.create(**base)

    def _find(self, payload, title):
        return next(f for f in payload["findings"] if f["title"] == title)

    def test_agent_observation_is_capped_and_explained(self):
        self._finding(
            severity="high", category=Finding.Category.SECURITY, rule_id="agent-observed-security",
            title="WAF 攔截頁顯示 IP", evidence="GET /.env → 406, body: 203.0.113.5",
            description="Hermes-Agent 在實際操作與 probe 觀察中發現：頁面顯示 IP",
            evidence_source="hermes_agent",
        )
        payload = build_report_payload(self.scan)
        item = self._find(payload, "WAF 攔截頁顯示 IP")
        self.assertEqual(item["severity"], "中風險")
        self.assertEqual(
            set(item["assessment"]), {"condition", "observed", "missing", "verify"},
        )
        self.assertIn("AI Agent", item["trace"])
        self.assertNotIn("Hermes-Agent", item["problem"])
        self.assertIn("AI Agent", payload["appendix"]["method_note"])

    def test_method_note_without_agent_says_rules_do_not_use_ai(self):
        self._finding(title="缺 title")
        note = build_report_payload(self.scan)["appendix"]["method_note"]
        self.assertIn("不使用 AI", note)
        self.assertNotIn("AI Agent 在實際操作", note)

    def test_merged_pages_keep_each_location_evidence(self):
        self._finding(page=self.p1, title="Meta title 長度不理想", evidence="title='A', length=1")
        self._finding(page=self.p2, title="Meta title 長度不理想", evidence="title='BB', length=2")
        item = self._find(build_report_payload(self.scan), "Meta title 長度不理想")
        self.assertEqual(
            sorted((loc["url"], loc["evidence"]) for loc in item["locations"]),
            [("https://example.com/a", "title='A', length=1"),
             ("https://example.com/b", "title='BB', length=2")],
        )

    def test_cookie_values_are_masked(self):
        self._finding(
            category=Finding.Category.SECURITY, rule_id="cookie-no-secure",
            title="Cookie 缺少 Secure",
            evidence="TS01bd6677=0136abcdef0123456789deadbeef; Path=/;",
        )
        item = self._find(build_report_payload(self.scan), "Cookie 缺少 Secure")
        self.assertNotIn("0136abcdef0123456789", item["evidence"])
        self.assertIn("已遮蔽", item["evidence"])

    def test_scope_states_page_cap_blocked_pages_and_skipped_checks(self):
        Page.objects.filter(pk=self.p2.pk).update(status_code=500)
        rows = build_report_payload(self.scan)["scan_info"]["scope"]
        self.assertIn("已檢查 2 頁", rows["實際掃描頁數"])
        self.assertIn("已達頁數上限", rows["實際掃描頁數"])
        self.assertIn("HTTP 4xx／5xx 1 頁", rows["被阻擋／回應錯誤"])
        self.assertIn("Nuclei", rows["本次未執行的檢查"])

    def test_verify_items_cover_every_finding_with_caveat(self):
        self._finding(title="A")
        self._finding(title="B", rule_id="r2", category=Finding.Category.GEO)
        appendix = build_report_payload(self.scan)["appendix"]
        self.assertEqual(len(appendix["verify_items"]), 2)
        self.assertIn("不一定代表已修好", appendix["verify_note"])

    def test_content_findings_carry_basis_and_security_does_not(self):
        self._finding(
            category=Finding.Category.GEO, rule_id="GEO_LLMS_TXT_C8A1E5700E",
            title="網站未提供 llms.txt",
        )
        self._finding(category=Finding.Category.SECURITY, rule_id="x", title="資安項目")
        payload = build_report_payload(self.scan)
        self.assertIn("限制", self._find(payload, "網站未提供 llms.txt")["basis"])
        self.assertNotIn("basis", self._find(payload, "資安項目"))

    def test_score_note_explains_weights(self):
        note = build_report_payload(self.scan)["summary"]["score_note"]
        self.assertIn("高風險 35", note)
        self.assertIn("平均", note)

    def test_authorization_time_uses_local_timezone(self):
        consent = AuthorizationConsent.objects.create(
            scan_job=self.scan, user=self.user, ip_address="203.0.113.9",
            user_agent="ua", authorized_domain="example.com", statement="s",
        )
        utc_time = datetime(2026, 9, 28, 4, 47, 17, tzinfo=ZoneInfo("UTC"))
        AuthorizationConsent.objects.filter(pk=consent.pk).update(created_at=utc_time)
        self.scan.refresh_from_db()
        auth = build_report_payload(self.scan)["appendix"]["authorization"]
        self.assertEqual(auth["授權時間"], "2026-09-28 12:47:17")


class IpContextTests(SimpleTestCase):
    def test_classifies_private_public_and_unknown_ips(self):
        from apps.scans.security.ip_context import describe_ips

        with patch("apps.scans.security.ip_context._resolve", return_value={"8.8.8.8"}):
            lines = describe_ips("10.0.0.5 / 8.8.8.8 / 1.1.1.1", "example.com")
        self.assertIn("私有", lines[0])
        self.assertIn("本來就是公開位址", lines[1])
        self.assertIn("可能是掃描器自己的位址", lines[2])

    def test_no_ip_returns_empty(self):
        from apps.scans.security.ip_context import describe_ips

        self.assertEqual(describe_ips("沒有位址", "example.com"), [])


class ScannerRefinementTests(SimpleTestCase):
    def test_cookie_line_masking_keeps_attributes(self):
        from apps.scans.security.cookie_scanner import mask_cookie_line

        masked = mask_cookie_line("sid=abcdefghijklmnop; Path=/; HttpOnly")
        self.assertTrue(masked.startswith("sid=abcd…op"))
        self.assertIn("Path=/; HttpOnly", masked)

    def test_sri_skips_dynamic_tag_manager_scripts(self):
        from apps.scans.security.sri_scanner import analyze_sri

        html = (
            '<script src="https://www.googletagmanager.com/gtag/js?id=X"></script>'
            '<script src="https://cdn.example.net/lib.js"></script>'
        )
        findings = analyze_sri([{"html": html, "url": "https://example.com/"}])
        self.assertEqual(len(findings), 1)
        self.assertIn("cdn.example.net", findings[0]["description"])

    def test_text_blocks_count_div_based_layout(self):
        from apps.scans.scanners import _text_block_count

        body = "".join(f"<div>{'這是一段足夠長的說明文字，' * 4}</div>" for _ in range(3))
        self.assertEqual(_text_block_count(body), 3)
        self.assertEqual(_text_block_count("<p>短</p><br>短"), 0)
