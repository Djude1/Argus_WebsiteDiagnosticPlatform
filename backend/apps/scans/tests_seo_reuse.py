"""同一次掃描不重複請求同一網址（roadmap §11 第 1 項）：爬蟲已取得的 robots.txt、sitemap、
llms.txt 由 SEO 連結檢查與站台檢查沿用；轉址的不沿用。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from apps.scans import crawler
from apps.scans.seo import collect, link_check

ORIGIN = "https://example.com"


def _page(path: str, html: str):
    return SimpleNamespace(
        id=1, url=f"{ORIGIN}{path}", final_url=f"{ORIGIN}{path}", status_code=200, html=html,
        rendered_dom="", title="", headers={}, load_time_ms=100, blocked_reason="",
    )


def _ok(url):
    return link_check.known_result(url, 200)


class BuildLinkReportReuseTests(SimpleTestCase):
    def _build(self, site_signals):
        page = _page("/", (
            "<a href='/sitemap.xml'>sitemap</a><a href='/llms.txt'>llms</a>"
            "<a href='/moved'>moved</a><a href='/about'>about</a>"
        ))
        checked: list[str] = []

        def fake_check_links(urls, **_kwargs):
            return {url: _ok(url) for url in urls}, {"over_limit": 0, "budget_exhausted": 0}

        def fake_check_url(url, client=None):
            checked.append(url)
            return _ok(url)

        with (
            patch.object(collect, "check_links", side_effect=fake_check_links) as links,
            patch.object(link_check, "check_url", side_effect=fake_check_url),
            patch.object(collect, "fetch_robots", return_value=link_check.parse_robots(
                f"{ORIGIN}/robots.txt", 404, "")) as fetch_robots,
        ):
            report = collect.build_link_report(f"{ORIGIN}/", [page], site_signals=site_signals)
        return report, links.call_args[0][0], checked, fetch_robots

    def test_reuses_crawler_results_and_skips_redirects(self):
        signals = {
            "fetched": {
                f"{ORIGIN}/robots.txt": 200,
                f"{ORIGIN}/sitemap.xml": 200,
                f"{ORIGIN}/llms.txt": 404,
                f"{ORIGIN}/moved": 301,
            },
            "robots_text": f"User-agent: *\nDisallow: /admin\nSitemap: {ORIGIN}/sitemap.xml\n",
        }
        report, link_targets, checked, fetch_robots = self._build(signals)

        # 已取得且沒有轉址的不再檢查；轉址的照常檢查跳轉鏈
        self.assertEqual(sorted(link_targets), [f"{ORIGIN}/about", f"{ORIGIN}/moved"])
        self.assertEqual(report["links"][f"{ORIGIN}/llms.txt"]["verdict"], "broken")
        self.assertEqual(report["links"][f"{ORIGIN}/sitemap.xml"]["verdict"], "ok")
        # robots.txt 直接用爬蟲讀到的原文
        fetch_robots.assert_not_called()
        self.assertEqual(report["robots"]["sitemaps"], [f"{ORIGIN}/sitemap.xml"])
        self.assertEqual(report["robots"]["disallow"], ["/admin"])
        # 站台檢查的 sitemap 沿用，不再送請求
        self.assertNotIn(f"{ORIGIN}/sitemap.xml", checked)
        sitemap_check = next(c for c in report["site_checks"] if c["key"] == "sitemap")
        self.assertEqual(sitemap_check["level"], "pass")
        self.assertEqual(report["reused"], {"links": 2, "robots": True, "site_checks": 1})

    def test_without_crawler_signals_fetches_as_before(self):
        report, link_targets, checked, fetch_robots = self._build(None)
        fetch_robots.assert_called_once()
        self.assertEqual(len(link_targets), 4)
        # 連結檢查已查過 /sitemap.xml，站台檢查直接沿用
        self.assertNotIn(f"{ORIGIN}/sitemap.xml", checked)
        self.assertEqual(report["reused"], {"links": 0, "robots": False, "site_checks": 1})

    def test_redirected_robots_is_fetched_again(self):
        _report, _targets, _checked, fetch_robots = self._build(
            {"fetched": {f"{ORIGIN}/robots.txt": 301}, "robots_text": None}
        )
        fetch_robots.assert_called_once()


@patch("apps.scans.crawler.assert_public_http_url", side_effect=lambda url: url)
class CrawlerRecordsFetchedTests(SimpleTestCase):
    async def test_sitemap_status_recorded(self, _assert):
        responses = {f"{ORIGIN}/sitemap.xml": (200, "<urlset></urlset>")}
        context = MagicMock()

        async def get(url, **_kwargs):
            status, body = responses.get(url, (404, ""))
            response = MagicMock(ok=status == 200, status=status)
            response.body = AsyncMock(return_value=body.encode())
            return response

        context.request.get = AsyncMock(side_effect=get)
        fetched: dict = {}
        await crawler.discover_sitemap_urls(context, ORIGIN, [], 10, fetched)
        self.assertEqual(fetched, {f"{ORIGIN}/sitemap.xml": 200})


class CrawledBrokenPageTests(SimpleTestCase):
    """爬蟲已造訪、回 404 的頁面要算進失效連結（2026-10-17 實掃：導覽列連到的頁面漏報）。"""

    def test_crawled_404_page_is_broken_link_and_reported(self):
        from apps.scans.seo.site_findings import broken_internal_links

        home = _page("/", "<a href='/service/9'>服務</a><a href='/about'>關於</a>")
        about = _page("/about", "<a href='/service/9'>服務</a>")
        missing = _page("/service/9", "<h1>404</h1>")
        missing.status_code = 404

        def fake_check_links(urls, **_kwargs):
            return {url: _ok(url) for url in urls}, {"over_limit": 0, "budget_exhausted": 0}

        with (
            patch.object(collect, "check_links", side_effect=fake_check_links) as links,
            patch.object(link_check, "check_url", side_effect=_ok),
            patch.object(collect, "fetch_robots", return_value=link_check.parse_robots(
                f"{ORIGIN}/robots.txt", 404, "")),
        ):
            report = collect.build_link_report(f"{ORIGIN}/", [home, about, missing])

        target = f"{ORIGIN}/service/9"
        # 爬蟲已造訪，不再另外送請求，但狀態寫進連結結果
        self.assertNotIn(target, links.call_args[0][0])
        self.assertEqual(report["links"][target]["verdict"], "broken")
        audits = [collect.audit_page(p) for p in (home, about, missing)]
        finding = broken_internal_links(report, audits, "example.com")
        self.assertIsNotNone(finding)
        self.assertIn(target, finding["evidence"])


class OutboundLinkBudgetTests(SimpleTestCase):
    """站內連結很多時，子網域／站外仍保留部分檢查額度（2026-10-17 實掃：站外全部未檢查）。"""

    def test_outbound_gets_reserved_share(self):
        internal = [f"{ORIGIN}/p/{i}" for i in range(300)]
        outbound = [f"https://other{i}.org/" for i in range(30)]
        targets = {**dict.fromkeys(internal, "internal"), **dict.fromkeys(outbound, "external")}
        ordered = collect._reserve_outbound(internal + outbound, targets, 100)
        checked = ordered[:100]
        self.assertEqual(sum(1 for u in checked if targets[u] == "external"), 25)
        self.assertEqual(len(ordered), 330)

    def test_reserve_is_split_between_subdomain_and_external(self):
        # 2026-10-19 實掃：子網域 35 個把 25% 額度吃光，6 個站外一個都沒檢查
        internal = [f"{ORIGIN}/p/{i}" for i in range(242)]
        subdomain = [f"https://sub{i}.example.tw/" for i in range(35)]
        external = [f"https://other{i}.org/" for i in range(6)]
        targets = {
            **dict.fromkeys(internal, "internal"), **dict.fromkeys(subdomain, "subdomain"),
            **dict.fromkeys(external, "external"),
        }
        checked = collect._reserve_outbound(internal + subdomain + external, targets, 150)[:150]
        self.assertEqual(sum(1 for u in checked if targets[u] == "external"), 6)
        self.assertEqual(sum(1 for u in checked if targets[u] == "subdomain"), 31)
        self.assertEqual(sum(1 for u in checked if targets[u] == "internal"), 113)

    def test_few_outbound_leaves_rest_to_internal(self):
        internal = [f"{ORIGIN}/p/{i}" for i in range(300)]
        outbound = ["https://other.org/"]
        targets = {**dict.fromkeys(internal, "internal"), **dict.fromkeys(outbound, "external")}
        checked = collect._reserve_outbound(internal + outbound, targets, 100)[:100]
        self.assertIn("https://other.org/", checked)
        self.assertEqual(sum(1 for u in checked if targets[u] == "internal"), 99)


class UnconfirmedCaveatTests(SimpleTestCase):
    """站內連結多數無法確認＝WAF／速率限制擋檢查，報告與 SEO 頁要說明（2026-10-19 實掃）。"""

    def _rows(self, unconfirmed, ok, status=406):
        from apps.scans.seo.link_trend import unconfirmed_caveat

        rows = [{"type": "internal", "verdict": "restricted", "status": status}] * unconfirmed
        rows += [{"type": "internal", "verdict": "ok", "status": 200}] * ok
        rows += [{"type": "internal", "verdict": "unchecked", "status": None}] * 80
        rows += [{"type": "external", "verdict": "restricted", "status": 403}] * 20
        return unconfirmed_caveat(rows)

    def test_majority_unconfirmed_internal_links_get_caveat(self):
        text = self._rows(113, 47)
        self.assertIn("113 個（71%）無法確認", text)
        self.assertIn("HTTP 406 113 個", text)
        self.assertIn("WAF", text)

    def test_minority_or_too_few_is_silent(self):
        self.assertEqual(self._rows(20, 100), "")
        self.assertEqual(self._rows(5, 3), "")
