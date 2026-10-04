"""SEO 分析頁：逐頁檢查、連結狀態判定、彙整 API、目標關鍵字、掃描階段與 Search Console 串接。"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.scans import tasks
from apps.scans.models import Page, ScanJob, SearchConsoleConnection, SiteProject
from apps.scans.seo import gsc, link_check
from apps.scans.seo.keywords import keyword_report, normalize_keywords
from apps.scans.seo.page_audit import audit_page, content_size, display_width
from apps.scans.seo.report import project_seo

User = get_user_model()
ORIGIN = "https://shop.example.tw"


def _html(
    title="晨光咖啡｜台北精品咖啡豆與手沖課程", h1="每天從一杯好咖啡開始", *, head="", body=""
):
    return (
        f"<html lang='zh-Hant'><head><title>{title}</title>"
        "<meta name='description' content='晨光咖啡烘焙所提供單品咖啡豆、綜合豆與濾掛禮盒，"
        "台北大安區門市每日新鮮烘焙，48 小時內出貨。'>"
        f"<link rel='canonical' href='{ORIGIN}/'>{head}</head><body><main>"
        f"<h1>{h1}</h1><h2>咖啡豆</h2><p>{'我們每天烘焙新鮮的咖啡豆，' * 30}</p>{body}"
        "</main></body></html>"
    )


class FakePage:
    def __init__(self, html, *, url=f"{ORIGIN}/", status=200, headers=None, load=900, pid=1):
        self.id = pid
        self.url = url
        self.final_url = url
        self.status_code = status
        self.title = ""
        self.html = html
        self.rendered_dom = ""
        self.headers = headers or {}
        self.load_time_ms = load
        self.blocked_reason = ""


def _levels(audit):
    return {check["key"]: check["level"] for check in audit["checks"]}


class PageAuditTests(SimpleTestCase):
    def test_cjk_width_counts_full_width_as_two(self):
        self.assertEqual(display_width("咖啡 shop"), 9)
        size = content_size("台北咖啡 coffee beans")
        self.assertEqual((size["cjk_chars"], size["latin_words"]), (4, 2))

    def test_chinese_title_uses_width_not_english_char_count(self):
        # 28 個中文字只有 28 個字元，用英文門檻（30–60 字元）會被判過短；以寬度計算是 56，合理
        audit = audit_page(FakePage(_html(title="晨" * 28)))
        self.assertEqual(_levels(audit)["title"], "pass")
        long_audit = audit_page(FakePage(_html(title="晨" * 40)))
        self.assertEqual(_levels(long_audit)["title"], "warning")

    def test_h1_need_not_match_title(self):
        audit = audit_page(FakePage(_html(title="晨光咖啡｜精品咖啡豆", h1="完全不同的主標題文字")))
        self.assertEqual(_levels(audit)["h1"], "pass")

    def test_noindex_header_and_foreign_canonical_make_page_not_indexable(self):
        audit = audit_page(FakePage(_html(), headers={"X-Robots-Tag": "noindex"}))
        self.assertFalse(audit["indexable"])
        self.assertIn("noindex（X-Robots-Tag）", audit["not_indexable_reasons"])

        other = audit_page(FakePage(_html(head="").replace(f"{ORIGIN}/'", f"{ORIGIN}/other'")))
        self.assertFalse(other["indexable"])
        self.assertIn("canonical 指向其他網址", other["not_indexable_reasons"])

    def test_images_links_and_heading_jumps(self):
        body = (
            "<img src='/a.jpg'><img src='/deco.png' alt=''>"
            "<h4>跳號標題</h4>"
            "<a href='/menu'>菜單</a><a href='mailto:a@b.tw'>信</a>"
            "<a href='javascript:void(0)'>x</a><a href='#top'>top</a>"
            "<a href='/cdn-cgi/l/email-protection#ab'>mail</a>"
            "<a href='https://blog.example.tw/post'><img src='/i.png' alt='部落格'></a>"
        )
        audit = audit_page(FakePage(_html(body=body)))
        levels = _levels(audit)
        self.assertEqual(levels["images"], "warning")  # 缺 alt 才算；空 alt 是裝飾圖
        self.assertEqual(levels["headings"], "notice")
        urls = [link["url"] for link in audit["links"]]
        self.assertEqual(urls, [f"{ORIGIN}/menu", "https://blog.example.tw/post"])
        self.assertEqual(audit["links"][1]["text"], "部落格")

    def test_thin_chinese_content_is_notice_not_failure(self):
        html = "<html><head><title>晨光咖啡門市資訊頁</title></head><body><main><h1>門市</h1>" \
               "<p>營業時間每天八點到晚上六點。</p></main></body></html>"
        self.assertEqual(_levels(audit_page(FakePage(html)))["content"], "notice")


def _mock_client(routes):
    """routes: {(method, url): (status, location)}；沒列到的 GET 照 HEAD 回應。"""
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        key = (request.method, str(request.url))
        status, location = routes.get(key) or routes.get(("HEAD", str(request.url)), (599, ""))
        headers = {"location": location} if location else {}
        return httpx.Response(status, headers=headers)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return client, calls


@mock.patch("apps.scans.seo.link_check.assert_public_http_url", side_effect=lambda url: url)
class LinkCheckTests(SimpleTestCase):
    def test_302_then_200_is_not_broken(self, _assert):
        client, _ = _mock_client({
            ("HEAD", "https://a.tw/old"): (302, "/new"),
            ("HEAD", "https://a.tw/new"): (200, ""),
        })
        result = link_check.check_url("https://a.tw/old", client)
        self.assertEqual(result["verdict"], "redirect")
        self.assertEqual([hop["status"] for hop in result["chain"]], [302, 200])

    def test_404_is_broken_and_403_is_restricted(self, _assert):
        client, _ = _mock_client({
            ("HEAD", "https://a.tw/gone"): (404, ""),
            ("HEAD", "https://x.com/p"): (403, ""), ("GET", "https://x.com/p"): (403, ""),
        })
        self.assertEqual(link_check.check_url("https://a.tw/gone", client)["verdict"], "broken")
        self.assertEqual(link_check.check_url("https://x.com/p", client)["verdict"], "restricted")

    def test_head_server_error_is_confirmed_with_get(self, _assert):
        # Cloudflare 對 HEAD 回 520、GET 才是真正狀態（2026-10-03 實測）
        client, _ = _mock_client({
            ("HEAD", "https://a.tw/s"): (520, ""), ("GET", "https://a.tw/s"): (200, ""),
        })
        self.assertEqual(link_check.check_url("https://a.tw/s", client)["verdict"], "ok")

    def test_head_not_allowed_falls_back_to_get(self, _assert):
        client, calls = _mock_client({
            ("HEAD", "https://a.tw/p"): (405, ""), ("GET", "https://a.tw/p"): (200, ""),
        })
        self.assertEqual(link_check.check_url("https://a.tw/p", client)["verdict"], "ok")
        self.assertEqual([c[0] for c in calls], ["HEAD", "GET"])

    def test_redirect_loop_stops(self, _assert):
        client, _ = _mock_client({("HEAD", "https://a.tw/loop"): (301, "/loop")})
        result = link_check.check_url("https://a.tw/loop", client)
        self.assertEqual(result["verdict"], "loop")
        self.assertEqual(len(result["chain"]), link_check.MAX_REDIRECTS + 1)

    def test_private_target_is_skipped_per_hop(self, _assert):
        _assert.side_effect = link_check.PublicScanTargetError("private")
        result = link_check.check_url("http://10.0.0.1/")
        self.assertEqual(result["verdict"], "skipped")

    def test_classification_and_robots_rules(self, _assert):
        site = "shop.example.tw"
        self.assertEqual(link_check.classify_link("https://www.shop.example.tw/a", site),
                         "internal")
        self.assertEqual(link_check.classify_link("https://blog.example.tw/", "shop.example.tw"),
                         "subdomain")
        self.assertEqual(link_check.classify_link("https://a.com.tw/", "b.com.tw"), "external")
        self.assertEqual(link_check.robots_blocks("/admin/x", ["/admin"]), "/admin")
        self.assertEqual(link_check.robots_blocks("/a.pdf", ["/*.pdf$"]), "/*.pdf$")
        self.assertEqual(link_check.robots_blocks("/public", ["/admin"]), "")


def _user(name="seo-owner"):
    return User.objects.create_user(username=name, email=f"{name}@example.com",
                                    password="safe-test-password")


class SeoReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _user()
        self.scan = ScanJob.objects.create(
            user=self.user, original_url=f"{ORIGIN}/", normalized_url=f"{ORIGIN}/",
            origin=ORIGIN, status=ScanJob.Status.COMPLETED, overall_score=70,
            completed_at=timezone.now(),
        )
        self.project = self.scan.project
        body = "<a href='/gone'>舊頁</a><a href='/moved'>搬家</a><a href='/menu'></a>"
        self.home = Page.objects.create(
            scan_job=self.scan, url=f"{ORIGIN}/", final_url=f"{ORIGIN}/", origin=ORIGIN,
            status_code=200, html=_html(body=body), load_time_ms=800,
        )
        self.admin = Page.objects.create(
            scan_job=self.scan, url=f"{ORIGIN}/admin/", final_url=f"{ORIGIN}/admin/",
            origin=ORIGIN, status_code=200, html=_html(title="後台", h1="後台").replace(
                f"href='{ORIGIN}/'", f"href='{ORIGIN}/admin/'"
            ), depth=1,
        )
        self.scan.seo_report = {
            "checked_at": timezone.now().isoformat(), "limit": 150, "unchecked": 0,
            "robots": {"disallow": ["/admin"]},
            "links": {
                f"{ORIGIN}/gone": {"verdict": "broken", "status": 404,
                                   "chain": [{"url": f"{ORIGIN}/gone", "status": 404}]},
                f"{ORIGIN}/moved": {"verdict": "redirect", "status": 200, "chain": [
                    {"url": f"{ORIGIN}/moved", "status": 302},
                    {"url": f"{ORIGIN}/new", "status": 200}]},
            },
            "site_checks": [{"key": "not_found", "label": "404 頁面", "level": "warning",
                             "value": "200", "advice": "回 404", "evidence": {
                                 "requested": f"{ORIGIN}/argus-404-check-x", "chain": []}}],
        }
        self.scan.save(update_fields=["seo_report"])

    def _issue(self, data, title):
        return next((issue for issue in data["issues"] if issue["title"] == title), None)

    def test_conclusions_carry_url_time_and_evidence(self):
        data = project_seo(self.project, self.scan)
        broken = self._issue(data, "站內失效連結")
        self.assertEqual(broken["level"], "critical")
        evidence = broken["pages"][0]
        self.assertEqual(evidence["url"], f"{ORIGIN}/")
        self.assertTrue(evidence["detected_at"])
        self.assertEqual(evidence["evidence"]["chain"][0]["status"], 404)

        # 302 → 200 不算失效，只是提示
        moved = self._issue(data, "站內連結經過轉址")
        self.assertEqual(moved["level"], "notice")
        self.assertEqual(data["overview"]["broken_links"], 1)

        site = self._issue(data, "404 頁面：需要處理")
        self.assertEqual(site["pages"][0]["url"], f"{ORIGIN}/argus-404-check-x")

        self.assertIsNotNone(self._issue(data, "連結沒有可讀文字"))

    def test_robots_disallow_affects_indexable_and_duplicate_titles(self):
        data = project_seo(self.project, self.scan)
        pages = {page["url"]: page for page in data["pages"]}
        self.assertTrue(pages[f"{ORIGIN}/"]["indexable"])
        self.assertFalse(pages[f"{ORIGIN}/admin/"]["indexable"])
        reasons = pages[f"{ORIGIN}/admin/"]["not_indexable_reasons"]
        self.assertIn("robots.txt Disallow: /admin", reasons)
        self.assertEqual(data["overview"]["indexable"], 1)

    def test_api_requires_owner_and_returns_page_detail(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get(f"/api/projects/{self.project.id}/seo/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scan"]["id"], self.scan.id)
        self.assertFalse(response.data["gsc"]["connected"])

        detail = client.get(f"/api/projects/{self.project.id}/seo/pages/{self.home.id}/")
        self.assertEqual(detail.status_code, 200)
        statuses = {link["url"]: link["verdict"] for link in detail.data["links"]}
        self.assertEqual(statuses[f"{ORIGIN}/gone"], "broken")

        stranger = APIClient()
        stranger.force_authenticate(_user("stranger"))
        self.assertEqual(stranger.get(f"/api/projects/{self.project.id}/seo/").status_code, 404)

    def test_keywords_are_validated_and_matched(self):
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/projects/{self.project.id}/seo/keywords/"
        response = client.post(url, {"keywords": [" 咖啡豆 ", "咖啡豆", "手沖課程", "外送"]},
                               format="json")
        self.assertEqual(response.data["keywords"], ["咖啡豆", "手沖課程", "外送"])
        self.assertEqual(client.post(url, {"keywords": "x"}, format="json").status_code, 400)
        self.assertEqual(
            client.post(url, {"keywords": [f"k{i}" for i in range(21)]}, format="json").status_code,
            400,
        )
        report = {row["keyword"]: row for row in client.get(
            f"/api/projects/{self.project.id}/seo/").data["keyword_report"]}
        self.assertIn("Title", report["手沖課程"]["best_page"]["places"])
        self.assertEqual(report["外送"]["pages_found"], 0)

    def test_normalize_keywords_rejects_long_items(self):
        with self.assertRaises(ValueError):
            normalize_keywords(["咖" * 61])
        self.assertEqual(keyword_report([], []), [])


class SeoStageTests(TestCase):
    def _ctx(self, categories):
        user = _user("stage-user")
        scan = ScanJob.objects.create(
            user=user, original_url=f"{ORIGIN}/", normalized_url=f"{ORIGIN}/", origin=ORIGIN,
            categories=categories,
        )
        page = Page.objects.create(scan_job=scan, url=f"{ORIGIN}/", final_url=f"{ORIGIN}/",
                                   origin=ORIGIN, status_code=200, html=_html())
        ctx = mock.Mock(scan_job=scan, scan_job_id=scan.id, pages=[(page, {})], deep_scan_total=1)
        return ctx, scan

    def test_skipped_without_seo_category(self):
        ctx, scan = self._ctx(["security"])
        with mock.patch("apps.scans.tasks.build_link_report") as build:
            tasks.stage_seo_links(ctx)
        build.assert_not_called()

    def test_writes_report_and_failure_does_not_raise(self):
        ctx, scan = self._ctx(["seo"])
        with mock.patch("apps.scans.tasks.build_link_report",
                        return_value={"checked_at": "t", "links": {}, "unchecked": 0}):
            tasks.stage_seo_links(ctx)
        scan.refresh_from_db()
        self.assertEqual(scan.seo_report["checked_at"], "t")
        with mock.patch("apps.scans.tasks.build_link_report", side_effect=RuntimeError("x")):
            tasks.stage_seo_links(ctx)  # 不應拋出


GSC_ENABLED = {"GOOGLE_OAUTH_CLIENT_ID": "cid.apps.googleusercontent.com",
               "GOOGLE_OAUTH_CLIENT_SECRET": "test-client-secret"}


class SearchConsolePropertyTests(SimpleTestCase):
    def test_unicode_url_prefix_matches_punycode_origin(self):
        self.assertTrue(gsc.property_matches("https://巧.tw/", "https://xn--gst.tw"))
        self.assertFalse(gsc.property_matches("http://巧.tw/", "https://xn--gst.tw"))

    def test_unicode_domain_matches_punycode_origin_and_subdomain(self):
        self.assertTrue(gsc.property_matches("sc-domain:巧.tw", "https://xn--gst.tw"))
        self.assertTrue(gsc.property_matches("sc-domain:巧.tw", "https://www.xn--gst.tw"))
        self.assertFalse(gsc.property_matches("sc-domain:巧.tw", "https://example.test"))


@override_settings(**GSC_ENABLED)
class SearchConsoleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _user("gsc-owner")
        self.project = SiteProject.objects.create(
            user=self.user, name="Shop", origin=ORIGIN, start_url=f"{ORIGIN}/"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = f"/api/projects/{self.project.id}/gsc"

    def _connect(self):
        response = self.client.post(f"{self.base}/connect/")
        self.assertEqual(response.status_code, 200)
        cookie = response.cookies[gsc.NONCE_COOKIE]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], gsc.CALLBACK_PATH)
        params = parse_qs(urlsplit(response.data["authorization_url"]).query)
        self.assertEqual(params["scope"], [gsc.SCOPE])
        self.assertEqual(params["access_type"], ["offline"])
        return params["state"][0], cookie.value

    def _callback(self, state, nonce, **extra):
        browser = APIClient()  # Google 導回時沒有 JWT
        if nonce:
            browser.cookies[gsc.NONCE_COOKIE] = nonce
        return browser.get("/api/gsc/callback/", {"state": state, "code": "auth-code", **extra})

    def test_full_oauth_flow_stores_encrypted_refresh_token(self):
        state, nonce = self._connect()
        token_response = {"refresh_token": "1//refresh-secret", "access_token": "a",
                          "scope": gsc.SCOPE}
        with mock.patch("apps.scans.seo.gsc._post_token", return_value=token_response):
            response = self._callback(state, nonce)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/projects/{self.project.id}/seo?gsc=connected")
        connection = SearchConsoleConnection.objects.get(project=self.project)
        self.assertNotIn("refresh-secret", connection.refresh_token_encrypted)
        self.assertEqual(gsc.decrypt_token(connection.refresh_token_encrypted), "1//refresh-secret")
        status = self.client.get(f"{self.base}/").data
        self.assertTrue(status["connected"])
        self.assertNotIn("refresh", str(status).lower().replace("needs_reconnect", ""))

    def test_callback_without_matching_browser_nonce_is_rejected(self):
        state, _nonce = self._connect()
        with mock.patch("apps.scans.seo.gsc._post_token") as post:
            response = self._callback(state, "attacker-nonce")
        self.assertIn("gsc=error", response["Location"])
        post.assert_not_called()
        self.assertFalse(SearchConsoleConnection.objects.exists())

    def test_missing_scope_is_rejected(self):
        state, nonce = self._connect()
        with mock.patch("apps.scans.seo.gsc._post_token",
                        return_value={"refresh_token": "r", "scope": "openid"}):
            response = self._callback(state, nonce)
        self.assertIn("gsc=error", response["Location"])
        self.assertFalse(SearchConsoleConnection.objects.exists())

    def _connected(self, prop=""):
        return SearchConsoleConnection.objects.create(
            project=self.project, user=self.user,
            refresh_token_encrypted=gsc.encrypt_token("r"), property_url=prop,
        )

    def test_property_must_belong_to_the_google_account(self):
        self._connected()
        sites = [{"site_url": "sc-domain:example.tw", "permission": "siteOwner"}]
        with mock.patch("apps.scans.seo.gsc.list_sites", return_value=sites):
            bad = self.client.patch(f"{self.base}/", {"property": "sc-domain:evil.tw"},
                                    format="json")
            good = self.client.patch(f"{self.base}/", {"property": "sc-domain:example.tw"},
                                     format="json")
            listed = self.client.get(f"{self.base}/properties/")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(good.data["property"], "sc-domain:example.tw")
        self.assertTrue(good.data["property_matches"])
        self.assertTrue(listed.data["properties"][0]["matches"])

    def test_performance_maps_queries_to_pages_and_compares_periods(self):
        self._connected("sc-domain:example.tw")

        def fake_query(_conn, _token, start, end, dimensions, _limit):
            current = start > timezone.now().date() - timedelta(days=40)
            if dimensions == ["query"]:
                return [{"keys": ["咖啡豆"], "clicks": 10 if current else 4, "impressions": 200,
                         "ctr": 0.05, "position": 4.2 if current else 6.0}]
            if dimensions == ["page"]:
                return [{"keys": [f"{ORIGIN}/"], "clicks": 10, "impressions": 200, "ctr": 0.05,
                         "position": 4.2}]
            if dimensions == ["date"]:
                return [{"keys": ["2026-09-01"], "clicks": 10, "impressions": 200, "ctr": 0.05,
                         "position": 4.2}]
            return [{"keys": ["咖啡豆", f"{ORIGIN}/"], "clicks": 10, "impressions": 200,
                     "ctr": 0.05, "position": 4.2}]

        with mock.patch("apps.scans.seo.gsc._access_token", return_value="a"), \
                mock.patch("apps.scans.seo.gsc._query", side_effect=fake_query):
            data = self.client.get(f"{self.base}/performance/", {"days": "28"}).data
        row = data["queries"][0]
        self.assertEqual(row["page"], f"{ORIGIN}/")
        self.assertEqual(row["clicks_change"], 6)
        self.assertEqual(row["position_change"], 1.8)
        self.assertEqual(data["totals"]["ctr"], 0.05)

    def test_inspect_only_accepts_this_site(self):
        self._connected("sc-domain:example.tw")
        response = self.client.post(f"{self.base}/inspect/", {"url": "https://evil.tw/"},
                                    format="json")
        self.assertEqual(response.status_code, 400)
        with mock.patch("apps.scans.seo.gsc._api", return_value={"inspectionResult": {
                "indexStatusResult": {"verdict": "PASS", "coverageState": "已提交並建立索引"}}}):
            response = self.client.post(f"{self.base}/inspect/", {"url": f"{ORIGIN}/"},
                                        format="json")
        self.assertEqual(response.data["verdict"], "PASS")

    def test_disconnect_revokes_and_deletes(self):
        self._connected()
        with mock.patch("apps.scans.seo.gsc.httpx.post") as post:
            self.assertEqual(self.client.delete(f"{self.base}/").status_code, 204)
        post.assert_called_once()
        self.assertFalse(SearchConsoleConnection.objects.exists())

    def test_expired_grant_asks_to_reconnect(self):
        connection = self._connected("sc-domain:example.tw")
        with mock.patch("apps.scans.seo.gsc._post_token",
                        side_effect=gsc.GscError("授權已失效", reconnect=True)):
            response = self.client.get(f"{self.base}/performance/")
        self.assertTrue(response.data["reconnect"])
        connection.refresh_from_db()
        self.assertTrue(connection.last_error)

    @override_settings(GOOGLE_OAUTH_CLIENT_SECRET="")
    def test_connect_requires_configuration_and_rejects_demo(self):
        self.assertEqual(self.client.post(f"{self.base}/connect/").status_code, 400)
        with override_settings(**GSC_ENABLED):
            SiteProject.objects.filter(id=self.project.id).update(is_demo=True)
            self.assertEqual(self.client.post(f"{self.base}/connect/").status_code, 400)
