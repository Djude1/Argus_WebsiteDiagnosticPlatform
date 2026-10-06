"""2026-10-06 第二輪獨立審查（argus-scan-17 報告）後的判定修正。

每一項都對應審查指出的「說得太滿」或「嚴重度偏重」：規則依據要精確，
嚴重度要反映實際風險，而不是「某條規則沒過」。
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.scans import tasks
from apps.scans.scanners import (
    PageAnalysisInput,
    analyze_page,
    analyze_security_site_level,
    analyze_site_signals,
    analyze_ux,
    is_admin_path,
)


def _site_findings(headers: dict) -> dict:
    page = {"url": "https://example.tw/", "final_url": "https://example.tw/", "headers": headers}
    return {f["title"]: f for f in analyze_security_site_level([page])}


def _page(url="https://example.tw/", html="<html><head><title>t</title></head><body></body></html>",
          **kw) -> PageAnalysisInput:
    return PageAnalysisInput(url=url, final_url=url, title="t", html=html, headers={},
                             element_boxes={}, **kw)


class HeaderSeverityTests(SimpleTestCase):
    def test_missing_csp_is_defense_in_depth_low(self):
        findings = _site_findings({"strict-transport-security": "max-age=31536000"})
        self.assertEqual(findings["缺少 CSP"]["severity"], "low")

    def test_frame_ancestors_counts_as_clickjacking_protection(self):
        protected = _site_findings({"content-security-policy": "frame-ancestors 'self'"})
        self.assertNotIn("缺少 X-Frame-Options", protected)
        unprotected = _site_findings({"content-security-policy": "default-src 'self'"})
        self.assertIn("frame-ancestors", unprotected["缺少 X-Frame-Options"]["description"])


class PageTypeTests(SimpleTestCase):
    def test_login_and_register_pages_skip_seo(self):
        for path in ("/management/login", "/management/register", "/account/sign-in"):
            self.assertTrue(is_admin_path(f"https://example.tw{path}"), path)
        self.assertFalse(is_admin_path("https://example.tw/gbprivacy"))
        titles = {f["title"] for f in analyze_page(_page("https://example.tw/management/login"))}
        self.assertNotIn("H1 標題數量不正確", titles)

    def test_h1_severity_reflects_real_impact(self):
        missing = [f for f in analyze_page(_page(), {"seo"}) if f["title"] == "H1 標題數量不正確"]
        self.assertEqual(missing[0]["severity"], "low")
        two = _page(html="<html><body><h1>a</h1><h1>b</h1></body></html>")
        multiple = [f for f in analyze_page(two, {"seo"}) if f["title"] == "H1 標題數量不正確"]
        self.assertEqual(multiple[0]["severity"], "info")


class TapTargetWordingTests(SimpleTestCase):
    def _finding(self, offenders):
        page = _page(ux_signals={"small_tap_targets": offenders}, layout_metrics={})
        return next(f for f in analyze_ux(page) if f["title"] == "觸控目標過小")

    def test_wcag_levels_are_cited_precisely(self):
        tiny = self._finding([{"selector": "a", "width_px": 18, "height_px": 18}])
        self.assertIn("WCAG 2.2 AA（2.5.8）", tiny["description"])
        self.assertIn("1 個小於 24×24px", tiny["description"])
        self.assertNotIn("WCAG 2.1 目標尺寸", tiny["description"])
        usability = self._finding([{"selector": "a", "width_px": 36, "height_px": 30}])
        self.assertIn("不是合規問題", usability["description"])


class MaturityAndWafWordingTests(SimpleTestCase):
    def test_llms_txt_is_marked_emerging(self):
        finding = analyze_site_signals({"llms_txt_found": False})[0]
        self.assertIn("新興做法", finding["description"])

    def test_zero_nuclei_findings_is_not_proof_of_waf_blocking(self):
        ctx = SimpleNamespace(
            nuclei_findings=[], katana_tech=["Cloudflare"], page_urls=["https://example.tw/a"],
            scan_job_id=0,
        )
        from unittest import mock

        with mock.patch("apps.scans.tasks.append_log"):
            note = tasks._waf_blocked_nuclei_note(ctx)[0]
        self.assertNotIn("有效的入侵防護", note["description"])
        self.assertIn("不代表網站沒有弱點", note["description"])
        self.assertLess(note["confidence"], 0.9)
