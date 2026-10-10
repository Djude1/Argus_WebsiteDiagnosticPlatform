"""GEO 可引用性（geo_citability.py）：Princeton 三種內容訊號的規則判定。"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.geo_citability import citability_findings

# 不重複的英文正文（過篇幅門檻），不含來源、數據、引言
_PROSE = " ".join(
    f"Sentence number {i} explains a distinct idea about the subject in plain words here."
    for i in range(60)
)


def _page(body_html: str) -> str:
    return f"<html><body><main><article>{body_html}</article></main></body></html>"


class CitabilityTests(SimpleTestCase):
    def _rules(self, html: str) -> set[str]:
        return {f["rule_id"] for f in citability_findings("https://example.com/post", html)}

    def test_thin_page_is_not_evaluated(self):
        # 篇幅不足（導覽頁、縮圖頁）不出題
        self.assertEqual(self._rules(_page("<p>Hello world.</p>")), set())

    def test_bare_prose_flags_all_three(self):
        rules = self._rules(_page(f"<p>{_PROSE}</p>"))
        self.assertEqual(
            rules,
            {
                "geo-citability-no-sources",
                "geo-citability-no-statistics",
                "geo-citability-no-quotations",
            },
        )

    def test_authoritative_sources_satisfy_cite(self):
        html = _page(
            f"<p>{_PROSE}</p>"
            '<p>See <a href="https://www.cdc.gov/x">CDC</a> and '
            '<a href="https://en.wikipedia.org/wiki/Y">Wikipedia</a>.</p>'
        )
        self.assertNotIn("geo-citability-no-sources", self._rules(html))

    def test_reference_section_satisfies_cite(self):
        html = _page(f"<p>{_PROSE}</p><h2>參考資料</h2><p>...</p>")
        self.assertNotIn("geo-citability-no-sources", self._rules(html))

    def test_statistics_satisfy(self):
        html = _page(f"<p>Figures: 34.2% share, NT$ 1,200 cost, up 15% YoY.</p><p>{_PROSE}</p>")
        self.assertNotIn("geo-citability-no-statistics", self._rules(html))

    def test_blockquote_satisfies_quotation(self):
        html = _page(f"<p>{_PROSE}</p><blockquote>An expert said something.</blockquote>")
        self.assertNotIn("geo-citability-no-quotations", self._rules(html))

    def test_non_html_document_skipped(self):
        self.assertEqual(citability_findings("https://x/feed", "<rss><item>x</item></rss>"), [])

    def test_all_findings_are_geo_soft(self):
        findings = citability_findings("https://example.com/post", _page(f"<p>{_PROSE}</p>"))
        for f in findings:
            self.assertEqual(f["category"], "geo")
            self.assertIn(f["severity"], ("low", "info"))

    def test_rules_have_report_basis(self):
        # 報告逐項「判定依據」要附研究出處（Princeton GEO），不只套用維度通用說明
        from apps.scans.reports import RULE_BASIS

        for rule in (
            "geo-citability-no-sources",
            "geo-citability-no-statistics",
            "geo-citability-no-quotations",
        ):
            self.assertIn(rule, RULE_BASIS)
