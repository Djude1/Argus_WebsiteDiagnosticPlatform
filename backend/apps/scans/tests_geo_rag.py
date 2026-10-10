"""GEO RAG 分塊就緒（geo_rag.py）。"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.geo_rag import rag_findings

# 60 段各自獨立的短句（正文約 780 字），足以讓「2 個小標題」時平均每段超過 250 字門檻
_PARAS = [
    f"<p>Distinct paragraph {i} conveys one clear self contained factual statement here.</p>"
    for i in range(60)
]
_SHORT = "A concise self-contained paragraph that stays well under the limit here."


def _page(body: str) -> str:
    return f"<html><body><main><article>{body}</article></main></body></html>"


class RagChunkingTests(SimpleTestCase):
    def _rules(self, html: str) -> set[str]:
        return {f["rule_id"] for f in rag_findings("https://example.com/post", html)}

    def test_no_headings_skipped(self):
        # 沒有小標題屬 geo_structure 的職責，這裡不報
        self.assertEqual(self._rules(_page("".join(_PARAS))), set())

    def test_well_chunked_not_flagged(self):
        # 同樣的正文，但切成 10 個小標題 → 平均每段短，不報
        body = "".join(
            f"<h2>Section {i}</h2>" + "".join(_PARAS[i * 6:(i + 1) * 6])
            for i in range(10)
        )
        self.assertEqual(self._rules(_page(body)), set())

    def test_oversized_sections_flagged(self):
        # 只有 2 個小標題切這麼長的正文 → 平均每段過長
        half = len(_PARAS) // 2
        body = (
            "<h2>Part 1</h2>" + "".join(_PARAS[:half])
            + "<h2>Part 2</h2>" + "".join(_PARAS[half:])
        )
        self.assertIn("geo-rag-chunking", self._rules(_page(body)))

    def test_finding_is_geo_info(self):
        half = len(_PARAS) // 2
        body = (
            "<h2>Part 1</h2>" + "".join(_PARAS[:half])
            + "<h2>Part 2</h2>" + "".join(_PARAS[half:])
        )
        fs = rag_findings("https://example.com/post", _page(body))
        self.assertTrue(fs)
        self.assertEqual(fs[0]["category"], "geo")
        self.assertEqual(fs[0]["severity"], "info")

    def test_short_page_skipped(self):
        self.assertEqual(self._rules(_page(f"<h2>A</h2><p>{_SHORT}</p>")), set())

    def test_rule_has_report_basis(self):
        from apps.scans.reports import RULE_BASIS

        self.assertIn("geo-rag-chunking", RULE_BASIS)

    def test_non_html_skipped(self):
        self.assertEqual(rag_findings("https://x/feed", "<rss><item>x</item></rss>"), [])
