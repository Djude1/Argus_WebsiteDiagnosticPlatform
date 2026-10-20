"""爬蟲登入態純函式測試（crawler_auth.py）。

瀏覽器操作（establish_login_state／_attempt_form_login）需真實 Chromium，不在單元測試範圍；
這裡鎖定候選網址、密碼欄位偵測與登入連結抽取的判定。
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.crawler_auth import (
    extract_login_links,
    html_has_password_field,
    login_candidate_urls,
)

ORIGIN = "https://site.example.test"


class PasswordFieldDetectionTests(SimpleTestCase):
    def test_password_in_form(self):
        html = '<form><input name="u" type="text"><input name="p" type="password"></form>'
        self.assertTrue(html_has_password_field(html))

    def test_password_loose_input_spa(self):
        # SPA 常把欄位放在 <form> 外
        self.assertTrue(html_has_password_field('<div><input type="password"></div>'))

    def test_no_password(self):
        self.assertFalse(html_has_password_field('<form><input type="text"></form>'))

    def test_empty(self):
        self.assertFalse(html_has_password_field(""))


class ExtractLoginLinksTests(SimpleTestCase):
    def test_picks_login_hinted_same_origin(self):
        html = (
            '<a href="/login">會員登入</a>'
            '<a href="/about">關於</a>'
            '<a href="https://other.test/login">外站</a>'
        )
        links = extract_login_links(html, ORIGIN + "/", ORIGIN)
        self.assertEqual(links, [ORIGIN + "/login"])

    def test_hint_in_attributes(self):
        html = '<a href="/x" id="signin-btn">進入</a>'
        self.assertEqual(extract_login_links(html, ORIGIN + "/", ORIGIN), [ORIGIN + "/x"])

    def test_skips_non_http_and_fragment(self):
        html = '<a href="javascript:void(0)">login</a><a href="#login">login</a>'
        self.assertEqual(extract_login_links(html, ORIGIN + "/", ORIGIN), [])


class LoginCandidateUrlsTests(SimpleTestCase):
    def test_start_first_then_links_then_common(self):
        html = '<a href="/members/login">登入</a>'
        urls = login_candidate_urls(ORIGIN + "/", ORIGIN, html)
        self.assertEqual(urls[0], ORIGIN + "/")
        self.assertIn(ORIGIN + "/members/login", urls)
        self.assertIn(ORIGIN + "/login", urls)  # 常見路徑

    def test_dedup_and_cap(self):
        urls = login_candidate_urls(ORIGIN + "/login", ORIGIN, "")
        self.assertEqual(len(urls), len(set(urls)))
        self.assertLessEqual(len(urls), 6)

    def test_same_origin_only(self):
        urls = login_candidate_urls(ORIGIN + "/", ORIGIN, "")
        self.assertTrue(all(u.startswith(ORIGIN) for u in urls))
