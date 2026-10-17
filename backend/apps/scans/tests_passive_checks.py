"""自家被動檢查測試（ADR-0005 §2，移植自 ZAP 被動）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.security.header_scanner import analyze_headers
from apps.scans.security.passive_checks import (
    analyze_error_disclosure,
    analyze_mixed_content,
    analyze_sensitive_url_params,
)

_HTTPS = "https://site.example.test/"


def _page(html="", url=_HTTPS, headers=None):
    return {"url": url, "final_url": url, "html": html, "headers": headers or {}}


class MixedContentTests(SimpleTestCase):
    def test_active_mixed_content_is_medium(self):
        html = '<script src="http://cdn.example.test/a.js"></script>'
        findings = analyze_mixed_content([_page(html)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "medium")
        self.assertEqual(findings[0]["rule_id"], "security-mixed-content")

    def test_passive_only_is_low(self):
        html = '<img src="http://cdn.example.test/p.png">'
        findings = analyze_mixed_content([_page(html)])
        self.assertEqual(findings[0]["severity"], "low")

    def test_https_resources_clean(self):
        html = '<script src="https://cdn.example.test/a.js"></script><img src="/x.png">'
        self.assertEqual(analyze_mixed_content([_page(html)]), [])

    def test_http_page_not_checked(self):
        # 非 HTTPS 頁面不算混合內容
        html = '<script src="http://cdn.example.test/a.js"></script>'
        page = _page(html, url="http://site.example.test/")
        self.assertEqual(analyze_mixed_content([page]), [])


class SensitiveUrlParamTests(SimpleTestCase):
    def test_token_in_page_url_flagged(self):
        page = _page(url="https://site.example.test/cb?access_token=abc123&x=1")
        findings = analyze_sensitive_url_params([page])
        self.assertEqual(findings[0]["rule_id"], "security-sensitive-url-param")
        self.assertIn("access_token", findings[0]["evidence"])

    def test_token_in_link_flagged(self):
        html = '<a href="/reset?token=zzz">reset</a>'
        findings = analyze_sensitive_url_params([_page(html)])
        self.assertEqual(len(findings), 1)

    def test_ordinary_params_clean(self):
        page = _page(url="https://site.example.test/list?page=2&sort=name")
        self.assertEqual(analyze_sensitive_url_params([page]), [])


class ErrorDisclosureTests(SimpleTestCase):
    def test_python_traceback_flagged(self):
        html = "<pre>Traceback (most recent call last):\n  File x</pre>"
        findings = analyze_error_disclosure([_page(html)])
        self.assertEqual(findings[0]["rule_id"], "security-error-disclosure")
        self.assertIn("Python", findings[0]["evidence"])

    def test_clean_page(self):
        self.assertEqual(analyze_error_disclosure([_page("<p>hello</p>")]), [])


class PermissionsPolicyHeaderTests(SimpleTestCase):
    def test_missing_permissions_policy_flagged(self):
        findings = analyze_headers([_page(headers={"content-type": "text/html"})])
        self.assertIn("header-permissions-policy", {f["rule_id"] for f in findings})

    def test_present_permissions_policy_not_flagged(self):
        findings = analyze_headers([_page(headers={"permissions-policy": "camera=()"})])
        self.assertNotIn("header-permissions-policy", {f["rule_id"] for f in findings})
