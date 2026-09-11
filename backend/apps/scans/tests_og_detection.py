"""Open Graph 社交分享標籤偵測（SEO 分類的 metadata 檢查）。

OG 標籤（og:title / og:description / og:image / og:url）決定頁面被分享到
社群與通訊軟體時的預覽呈現。在此規則之前 scanner 對 OG 完全零覆蓋——
使用者不知道社群分享目前的呈現缺口；修正產出功能的 OG＋meta 產物
也以此偵測為報告端的對應 finding。
"""

from __future__ import annotations

from django.test import TestCase

from apps.scans.models import Finding
from apps.scans.scanners import PageAnalysisInput, analyze_page

OG_FINDING_TITLE = "缺少 Open Graph 社交分享標籤"


def _input(html: str) -> PageAnalysisInput:
    return PageAnalysisInput(
        url="https://example.com/",
        final_url="https://example.com/",
        title="示範頁面標題足夠長",
        html=html,
        headers={},
        element_boxes={},
    )


def _og_findings(html: str) -> list[dict]:
    return [
        f for f in analyze_page(_input(html)) if f["title"] == OG_FINDING_TITLE
    ]


class OpenGraphDetectionTests(TestCase):
    def test_page_without_og_tags_produces_one_seo_finding(self):
        findings = _og_findings(
            "<html><head><title>標題</title></head><body><h1>主標</h1></body></html>"
        )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["category"], Finding.Category.SEO)
        self.assertEqual(finding["severity"], Finding.Severity.LOW)
        for tag in ("og:title", "og:description", "og:image", "og:url"):
            self.assertIn(tag, finding["evidence"])

    def test_page_with_all_og_tags_produces_no_finding(self):
        html = (
            "<html><head>"
            '<meta property="og:title" content="示範頁">'
            '<meta property="og:description" content="這是示範頁的描述文字">'
            '<meta property="og:image" content="https://example.com/cover.png">'
            '<meta property="og:url" content="https://example.com/">'
            "</head><body><h1>主標</h1></body></html>"
        )

        self.assertEqual(_og_findings(html), [])

    def test_partial_og_tags_only_list_missing_ones(self):
        html = (
            "<html><head>"
            '<meta property="og:title" content="示範頁">'
            '<meta property="og:image" content="https://example.com/cover.png">'
            "</head><body><h1>主標</h1></body></html>"
        )

        findings = _og_findings(html)
        self.assertEqual(len(findings), 1)
        self.assertIn("og:description", findings[0]["evidence"])
        self.assertIn("og:url", findings[0]["evidence"])
        self.assertNotIn("og:title=", findings[0]["evidence"])
        self.assertNotIn("og:image=", findings[0]["evidence"])

    def test_empty_og_content_counts_as_missing(self):
        html = (
            "<html><head>"
            '<meta property="og:title" content="">'
            '<meta property="og:description" content="   ">'
            '<meta property="og:image" content="https://example.com/cover.png">'
            '<meta property="og:url" content="https://example.com/">'
            "</head><body><h1>主標</h1></body></html>"
        )

        findings = _og_findings(html)
        self.assertEqual(len(findings), 1)
        self.assertIn("og:title", findings[0]["evidence"])
        self.assertIn("og:description", findings[0]["evidence"])

    def test_og_tags_via_name_attribute_also_recognized(self):
        """少數網站用 name= 而非標準的 property= 放 OG 標籤，兩種都要認。"""
        html = (
            "<html><head>"
            '<meta name="og:title" content="示範頁">'
            '<meta name="og:description" content="這是示範頁的描述文字">'
            '<meta name="og:image" content="https://example.com/cover.png">'
            '<meta name="og:url" content="https://example.com/">'
            "</head><body><h1>主標</h1></body></html>"
        )

        self.assertEqual(_og_findings(html), [])
