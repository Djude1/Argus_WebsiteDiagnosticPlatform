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
