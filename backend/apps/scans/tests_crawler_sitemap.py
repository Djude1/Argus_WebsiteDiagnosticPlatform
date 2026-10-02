"""整站掃描以 sitemap 補爬取種子（只靠 <a> 連結時，連結稀疏的網站到不了頁數上限）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from apps.scans import crawler

ORIGIN = "https://example.com"


def _response(body: str, ok: bool = True):
    response = MagicMock(ok=ok)
    response.body = AsyncMock(return_value=body.encode())
    return response


def _context(pages: dict[str, str]):
    """依網址回傳內容的假 Playwright request context；沒列的網址回 404。"""
    context = MagicMock()

    async def get(url, **_kwargs):
        return _response(pages[url]) if url in pages else _response("", ok=False)

    context.request.get = AsyncMock(side_effect=get)
    return context


def _urlset(*paths: str) -> str:
    locs = "".join(f"<url><loc>{ORIGIN}{path}</loc></url>" for path in paths)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'


class SitemapParsingTests(SimpleTestCase):
    def test_robots_sitemap_declarations(self):
        text = "User-agent: *\nDisallow: /admin\nSitemap: https://example.com/a.xml\nsitemap:https://example.com/b.xml\n"
        self.assertEqual(
            crawler.parse_robots_sitemaps(text),
            ["https://example.com/a.xml", "https://example.com/b.xml"],
        )

    def test_page_urls_keep_same_origin_html_only(self):
        urls = crawler.sitemap_page_urls(
            [
                f"{ORIGIN}/about",
                f"{ORIGIN}/about#team",
                "https://other.example/x",
                f"{ORIGIN}/brochure.pdf",
                f"{ORIGIN}/search?q=a&amp;page=2",
            ],
            ORIGIN,
        )
        self.assertEqual(urls, [f"{ORIGIN}/about", f"{ORIGIN}/search?q=a&page=2"])


@patch("apps.scans.crawler.assert_public_http_url", side_effect=lambda url: url)
class SitemapDiscoveryTests(SimpleTestCase):
    async def test_default_sitemap_xml(self, _assert):
        context = _context({f"{ORIGIN}/sitemap.xml": _urlset("/a", "/b", "/c")})
        urls = await crawler.discover_sitemap_urls(context, ORIGIN, [], limit=2)
        self.assertEqual(urls, [f"{ORIGIN}/a", f"{ORIGIN}/b"])

    async def test_declared_sitemap_index_expands_children(self, _assert):
        index = (
            "<sitemapindex>"
            f"<sitemap><loc>{ORIGIN}/s1.xml</loc></sitemap>"
            f"<sitemap><loc>{ORIGIN}/s2.xml</loc></sitemap>"
            "</sitemapindex>"
        )
        context = _context(
            {
                f"{ORIGIN}/index.xml": index,
                f"{ORIGIN}/s1.xml": _urlset("/a"),
                f"{ORIGIN}/s2.xml": _urlset("/b", "/a"),
            }
        )
        urls = await crawler.discover_sitemap_urls(context, ORIGIN, [f"{ORIGIN}/index.xml"], 50)
        self.assertEqual(urls, [f"{ORIGIN}/a", f"{ORIGIN}/b"])

    async def test_cross_origin_and_missing_sitemaps_are_ignored(self, _assert):
        context = _context({})
        urls = await crawler.discover_sitemap_urls(
            context, ORIGIN, ["https://cdn.other.example/sitemap.xml"], 50
        )
        self.assertEqual(urls, [])
        requested = [call.args[0] for call in context.request.get.await_args_list]
        self.assertEqual(requested, [f"{ORIGIN}/sitemap.xml"])

    async def test_oversized_sitemap_is_skipped(self, _assert):
        huge = _urlset("/a") + " " * crawler._SITEMAP_MAX_BYTES
        context = _context({f"{ORIGIN}/sitemap.xml": huge})
        self.assertEqual(await crawler.discover_sitemap_urls(context, ORIGIN, [], 50), [])


class CrawlStateSeedTests(SimpleTestCase):
    def test_seed_respects_page_limit_and_skips_duplicates(self):
        state = crawler._CrawlState(f"{ORIGIN}/", ORIGIN, max_depth=6, max_pages=3)
        added = state.seed(
            [f"{ORIGIN}/", f"{ORIGIN}/a", f"{ORIGIN}/a", f"{ORIGIN}/b", f"{ORIGIN}/c"]
        )
        self.assertEqual(added, 2)
        self.assertEqual(
            list(state.queue), [(f"{ORIGIN}/", 0), (f"{ORIGIN}/a", 1), (f"{ORIGIN}/b", 1)]
        )
