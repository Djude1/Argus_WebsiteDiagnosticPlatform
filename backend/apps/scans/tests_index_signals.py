"""sitemap、robots.txt、noindex、canonical 一致性（seo/site_findings.index_signal_conflicts）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.ai_bots import robots_allows
from apps.scans.seo.site_findings import seo_site_findings
from apps.scans.tests_seo_analysis import FakePage

ORIGIN = "https://shop.example.tw"


def _page(path, *, canonical=None, noindex=False, status=200, final=None, blocked="", pid=1):
    url = f"{ORIGIN}{path}"
    head = f"<title>頁面 {path}｜晨光咖啡</title>"
    head += f"<link rel='canonical' href='{canonical or url}'>"
    if noindex:
        head += "<meta name='robots' content='noindex'>"
    page = FakePage(
        f"<html><head>{head}</head><body><h1>{path}</h1></body></html>",
        url=url, status=status, pid=pid,
    )
    page.final_url = final or url
    page.blocked_reason = blocked
    return page


def _conflicts(pages, sitemap, robots=None):
    found = seo_site_findings({"links": {}, "site_checks": []}, pages, f"{ORIGIN}/",
                              sitemap_urls=sitemap, robots_text=robots)
    finding = next((f for f in found if f["rule_id"] == "seo-index-signals-conflict"), None)
    if finding is None:
        return None
    return {row["kind"]: row["urls"] for row in finding["evidence_json"]["symptoms"]}


class IndexSignalConflictTests(SimpleTestCase):
    def test_consistent_site_has_no_conflict(self):
        pages = [_page("/", pid=1), _page("/about", pid=2)]
        robots = "User-agent: *\nDisallow: /admin/\n"
        self.assertIsNone(_conflicts(pages, [f"{ORIGIN}/", f"{ORIGIN}/about"], robots))

    def test_sitemap_lists_non_indexable_pages(self):
        pages = [
            _page("/a", noindex=True, pid=1),
            _page("/b", canonical=f"{ORIGIN}/b-main", pid=2),
            _page("/c", status=404, pid=3),
            _page("/d", final=f"{ORIGIN}/d-new", pid=4),
            _page("/e", pid=5),
        ]
        sitemap = [f"{ORIGIN}/{p}" for p in "abcde"]
        self.assertEqual(_conflicts(pages, sitemap), {
            "sitemap_noindex": [f"{ORIGIN}/a"],
            "sitemap_canonical": [f"{ORIGIN}/b → canonical {ORIGIN}/b-main"],
            "sitemap_error": [f"{ORIGIN}/c（HTTP 404）"],
            "sitemap_redirect": [f"{ORIGIN}/d → {ORIGIN}/d-new"],
        })

    def test_pages_not_in_sitemap_are_not_judged(self):
        pages = [_page("/a", noindex=True), _page("/b", status=404, pid=2)]
        self.assertIsNone(_conflicts(pages, [f"{ORIGIN}/"]))

    def test_sitemap_urls_blocked_for_googlebot(self):
        robots = (
            "User-agent: *\nDisallow: /\n\n"
            "User-agent: Googlebot\nDisallow: /private/\n"
        )
        sitemap = [f"{ORIGIN}/", f"{ORIGIN}/private/x?a=1"]
        # 有點名 Googlebot 的群組就只用該群組；/ 允許、/private/ 禁止
        self.assertEqual(_conflicts([], sitemap, robots),
                         {"sitemap_robots_blocked": [f"{ORIGIN}/private/x?a=1"]})

    def test_noindex_page_blocked_by_robots(self):
        pages = [_page("/members", noindex=True)]
        robots = "User-agent: *\nDisallow: /members\n"
        self.assertEqual(_conflicts(pages, [], robots),
                         {"noindex_robots_blocked": [f"{ORIGIN}/members"]})

    def test_waf_blocked_pages_are_skipped(self):
        pages = [_page("/a", status=403, blocked="waf")]
        self.assertIsNone(_conflicts(pages, [f"{ORIGIN}/a"]))

    def test_finding_shape(self):
        found = seo_site_findings({"links": {}, "site_checks": []}, [_page("/a", noindex=True)],
                                  f"{ORIGIN}/", sitemap_urls=[f"{ORIGIN}/a"])
        finding = next(f for f in found if f["rule_id"] == "seo-index-signals-conflict")
        self.assertEqual(finding["severity"], "low")
        self.assertIn("sitemap 列出設為 noindex 的頁面（1 個）", finding["evidence"])


class RobotsAllowsTests(SimpleTestCase):
    def test_rules(self):
        robots = "User-agent: *\nDisallow: /*.pdf$\nAllow: /admin/public\nDisallow: /admin\n"
        self.assertTrue(robots_allows(None, "googlebot", "/x"))
        self.assertFalse(robots_allows(robots, "googlebot", "/files/a.pdf"))
        self.assertTrue(robots_allows(robots, "googlebot", "/files/a.pdf?v=1"))
        self.assertTrue(robots_allows(robots, "googlebot", "/admin/public/a"))
        self.assertFalse(robots_allows(robots, "googlebot", "/admin/x"))
