"""GEO 內容衰退預測（geo_decay.py）。"""
from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from apps.scans.geo_decay import decay_findings

_PROSE = " ".join(
    f"Sentence number {i} explains a distinct idea about the subject in plain words here."
    for i in range(60)
)


def _page(body: str) -> str:
    return f"<html><body><main><article>{body}</article></main></body></html>"


class ContentDecayTests(SimpleTestCase):
    def _rules(self, html: str) -> set[str]:
        return {f["rule_id"] for f in decay_findings("https://example.com/post", html)}

    def test_thin_page_skipped(self):
        self.assertEqual(self._rules(_page("<p>Hello.</p>")), set())

    def test_single_category_not_flagged(self):
        # 只有一類（時效性措辭）不足以成立
        html = _page(f"<p>{_PROSE} This was recently updated.</p>")
        self.assertEqual(self._rules(html), set())

    def test_two_categories_flagged(self):
        old_year = date.today().year - 2
        lead = f"<p>In {old_year} we launched. The latest version is Python 3.11.</p>"
        html = _page(f"{lead}<p>{_PROSE}</p>")
        self.assertIn("geo-content-decay", self._rules(html))

    def test_finding_is_geo_info(self):
        old_year = date.today().year - 2
        lead = f"<p>In {old_year}, recently updated, running Django 4.2 here.</p>"
        html = _page(f"{lead}<p>{_PROSE}</p>")
        fs = decay_findings("https://example.com/post", html)
        self.assertTrue(fs)
        self.assertEqual(fs[0]["category"], "geo")
        self.assertEqual(fs[0]["severity"], "info")

    def test_future_or_current_year_alone_not_flagged(self):
        # 當年／未來年份不算過去年份
        y = date.today().year
        html = _page(f"<p>{_PROSE} Plans for {y} and {y + 1}.</p>")
        self.assertEqual(self._rules(html), set())

    def test_non_html_skipped(self):
        rss = "<rss><item>2020 recently</item></rss>"
        self.assertEqual(decay_findings("https://x/feed", rss), [])

    def test_rule_has_report_basis(self):
        from apps.scans.reports import RULE_BASIS

        self.assertIn("geo-content-decay", RULE_BASIS)
