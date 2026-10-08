"""版面位移（CLS）與元素歸因（roadmap §4 第 3 項）。

crawler.collect_layout_shift 量測、scanners._ux_layout_shift 產生問題。

真實瀏覽器測試需要 Chromium：設 ARGUS_TEST_CHROMIUM_PATH 指向執行檔，沒有就略過。
"""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.scans.crawler import collect_layout_shift, scroll_to_bottom
from apps.scans.models import Finding
from apps.scans.reports import RULE_BASIS
from apps.scans.scanners import PageAnalysisInput, analyze_ux

CHROMIUM = os.environ.get("ARGUS_TEST_CHROMIUM_PATH", "")


def _page(layout_shift: dict | None) -> PageAnalysisInput:
    metrics = {"viewport_width": 375, "scroll_width": 375, "overflow_px": 0, "offenders": []}
    if layout_shift is not None:
        metrics["layout_shift"] = layout_shift
    return PageAnalysisInput(
        url="https://example.com/",
        final_url="https://example.com/",
        title="t",
        html="<html><body></body></html>",
        headers={},
        element_boxes={},
        layout_metrics=metrics,
    )


def _shift_findings(layout_shift):
    return [f for f in analyze_ux(_page(layout_shift)) if f["rule_id"] == "ux-layout-shift"]


class LayoutShiftFindingTests(SimpleTestCase):
    ELEMENTS = [{"selector": "main#content", "score": 0.3, "moved_px": 180, "shifts": 1}]

    def test_poor_cls_is_medium_and_names_elements(self):
        [finding] = _shift_findings(
            {"cls": 0.31, "shifts": 2, "elements": self.ELEMENTS, "unsized_media": 3}
        )
        self.assertEqual(finding["severity"], Finding.Severity.MEDIUM)
        self.assertIn("0.31", finding["description"])
        self.assertIn("不佳", finding["description"])
        self.assertIn("3 個圖片", finding["description"])
        self.assertIn("main#content（位移 180px）", finding["evidence"])
        self.assertEqual(finding["selector"], "main#content")

    def test_needs_improvement_is_low(self):
        [finding] = _shift_findings({"cls": 0.15, "elements": self.ELEMENTS, "unsized_media": 0})
        self.assertEqual(finding["severity"], Finding.Severity.LOW)
        self.assertIn("需改善", finding["description"])
        self.assertNotIn("沒有同時標", finding["description"])

    def test_good_or_not_measured_produces_nothing(self):
        self.assertEqual(_shift_findings({"cls": 0.1, "elements": self.ELEMENTS}), [])
        self.assertEqual(_shift_findings({}), [])
        self.assertEqual(_shift_findings(None), [])

    def test_rule_has_report_basis(self):
        self.assertIn("ux-layout-shift", RULE_BASIS)


@unittest.skipUnless(
    CHROMIUM and Path(CHROMIUM).exists(), "需要 Chromium（ARGUS_TEST_CHROMIUM_PATH）"
)
class LayoutShiftRealBrowserTests(SimpleTestCase):
    # 0.3 秒後在內容上方插入 300px 高的橫幅，把 #article 往下推
    SHIFTING = """<html><body style="margin:0">
      <div id="slot"></div>
      <div id="article" style="height:600px;background:#eee">文章內容</div>
      <script>setTimeout(() => {
        const ad = document.createElement("div");
        ad.style.height = "300px";
        document.getElementById("slot").appendChild(ad);
      }, 300);</script></body></html>"""
    STABLE = """<html><body><div style="height:300px"></div>
      <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="1" height="1"></body></html>"""

    # 捲回頂端時才插入橫幅（模擬捲動後縮小、回到頂端又展開的標頭）
    EXPANDS_AT_TOP = """<html><body style="margin:0"><div id="slot"></div>
      <div id="article" style="height:4000px">文章內容</div>
      <script>let scrolled = false;
      addEventListener("scroll", () => {
        if (scrollY > 0) scrolled = true;
        if (scrollY === 0 && scrolled) {
          const bar = document.createElement("div");
          bar.style.height = "300px";
          document.getElementById("slot").appendChild(bar);
        }
      });</script></body></html>"""

    def _measure(self, html: str, *, scroll: bool = False) -> dict:
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path=CHROMIUM)
                page = await browser.new_page(viewport={"width": 1440, "height": 1000})
                # 要真的導覽：set_content 之後的位移會被 Chromium 標成「使用者操作後」而不計
                await page.route(
                    "http://shift.test/",
                    lambda route: route.fulfill(body=html, content_type="text/html; charset=utf-8"),
                )
                await page.goto("http://shift.test/")
                await page.wait_for_timeout(800)
                if scroll:
                    await scroll_to_bottom(page)
                    await page.wait_for_timeout(300)
                result = await collect_layout_shift(page)
                await browser.close()
                return result

        return asyncio.run(run())

    def test_late_banner_shift_is_attributed_to_moved_element(self):
        result = self._measure(self.SHIFTING)
        self.assertGreater(result["cls"], 0.1)
        self.assertEqual(result["elements"][0]["selector"], "div#article")
        self.assertEqual(result["elements"][0]["moved_px"], 300)

    def test_stable_page_has_no_shift(self):
        result = self._measure(self.STABLE)
        self.assertEqual(result["cls"], 0)
        self.assertEqual(result["elements"], [])
        self.assertEqual(result["unsized_media"], 0)

    def test_shift_after_jump_back_to_top_is_not_counted(self):
        # 爬蟲捲到底後瞬間跳回頂端，之後的位移是量測動作造成的，不是讀者會遇到的
        result = self._measure(self.EXPANDS_AT_TOP, scroll=True)
        self.assertEqual(result["cls"], 0)
        self.assertEqual(result["shifts"], 0)
