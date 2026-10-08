"""安全標頭等第（security/observatory.py，依 Mozilla HTTP Observatory 規則離線計算）。"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.scans.security.observatory import evaluate, grade_for, summary_line

URL = "https://example.com/"
STRONG = {
    "content-security-policy": "default-src 'none'; script-src 'self'; frame-ancestors 'none'",
    "strict-transport-security": "max-age=63072000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "set-cookie": "sessionid=abc; Path=/; Secure; HttpOnly; SameSite=Lax",
}
SEO_OK = {"site_checks": [{"key": "http_to_https", "verdict": "pass"}]}


def _page(headers, html="<html><body>ok</body></html>", url=URL, status=200):
    headers = {"content-type": "text/html", **headers}
    return [{"url": url, "final_url": url, "status_code": status, "headers": headers,
             "html": html, "blocked_reason": ""}]


def _tests(result):
    return {t["key"]: t for t in result["tests"]}


class ObservatoryTests(SimpleTestCase):
    def test_strong_site_gets_bonus(self):
        result = evaluate(_page(STRONG), SEO_OK)
        tests = _tests(result)
        self.assertEqual(tests["csp"]["modifier"], 10)
        self.assertEqual(tests["x-frame-options"]["modifier"], 5)
        self.assertEqual(tests["referrer"]["modifier"], 5)
        self.assertEqual(tests["cookies"]["modifier"], 5)
        self.assertEqual(result["score"], 125)
        self.assertEqual(result["grade"], "A+")
        self.assertTrue(result["bonus_applied"])

    def test_bare_site(self):
        result = evaluate(_page({"content-type": "text/html"}), SEO_OK)
        tests = _tests(result)
        # CSP -25、HSTS -20、nosniff -5、XFO -20
        self.assertEqual(result["score"], 30)
        self.assertEqual(result["grade"], "D")
        self.assertEqual(tests["csp"]["result"], "沒有設定 CSP")

    def test_bonus_only_when_base_at_least_90(self):
        headers = {**STRONG, "x-content-type-options": "", "strict-transport-security":
                   "max-age=86400"}  # -5、-10 → base 85，加分不算
        result = evaluate(_page(headers), SEO_OK)
        self.assertEqual(result["score"], 85)
        self.assertFalse(result["bonus_applied"])

    def test_csp_variants(self):
        cases = {
            "default-src 'self'; script-src 'self' 'unsafe-inline'": -20,
            "script-src 'self' 'unsafe-inline' 'nonce-abc'": 5,  # 有 nonce 時 unsafe-inline 被忽略
            "script-src 'self' 'unsafe-eval'": -10,
            "script-src https: http:": -20,
            "img-src *": -20,  # 沒限制腳本
            "default-src 'self'; img-src http://cdn.test": -10,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                tests = _tests(evaluate(_page({"content-security-policy": value}), SEO_OK))
                self.assertEqual(tests["csp"]["modifier"], expected)

    def test_cookies(self):
        cases = {
            "sessionid=a; Path=/": -40,
            "theme=dark; Path=/": -20,
            "sessionid=a; Secure": -30,  # 有 Secure 沒 HttpOnly
            "theme=dark; Secure; SameSite=Lax": 5,
        }
        for cookie, expected in cases.items():
            with self.subTest(cookie=cookie):
                tests = _tests(evaluate(_page({"set-cookie": cookie}), SEO_OK))
                self.assertEqual(tests["cookies"]["modifier"], expected)
        with_hsts = _tests(evaluate(_page({"set-cookie": "sessionid=a; HttpOnly",
                                           "strict-transport-security": "max-age=31536000"})))
        self.assertEqual(with_hsts["cookies"]["modifier"], -10)

    def test_sri(self):
        cases = {
            '<script src="/app.js"></script>': 0,
            '<script src="https://cdn.test/a.js" integrity="sha384-x"></script>': 5,
            '<script src="https://cdn.test/a.js"></script>': -5,
            '<script src="http://cdn.test/a.js"></script>': -50,
        }
        for html, expected in cases.items():
            with self.subTest(html=html):
                tests = _tests(evaluate(_page({}, html=html), SEO_OK))
                self.assertEqual(tests["sri"]["modifier"], expected)

    def test_redirection_not_evaluated_without_seo_check(self):
        tests = _tests(evaluate(_page(STRONG), {}))
        self.assertFalse(tests["redirection"]["evaluated"])
        self.assertEqual(tests["redirection"]["modifier"], 0)
        failing = {"site_checks": [{"key": "http_to_https", "verdict": "warning"}]}
        self.assertEqual(_tests(evaluate(_page(STRONG), failing))["redirection"]["modifier"], -20)

    def test_http_site(self):
        tests = _tests(evaluate(_page({}, url="http://example.com/"), {}))
        self.assertEqual(tests["hsts"]["modifier"], -20)
        self.assertEqual(tests["redirection"]["modifier"], -20)

    def test_grades_and_summary(self):
        self.assertEqual([grade_for(s) for s in (100, 90, 85, 70, 45, 24, 0)],
                         ["A+", "A", "A-", "B", "C-", "F", "F"])
        line = summary_line(evaluate(_page({}), {}))
        self.assertIn("非官方結果，不計入 Argus 分數", line)
        self.assertIn("未評估：HTTP 轉址到 HTTPS", line)
        self.assertEqual(summary_line({}), "")

    def test_no_usable_page(self):
        self.assertEqual(evaluate(_page({}, status=403)), {})

    def test_no_network(self):
        with mock.patch("socket.socket.connect", side_effect=AssertionError("不得連線")):
            evaluate(_page(STRONG), SEO_OK)
