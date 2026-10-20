"""觸控目標過小：句子中的文字連結是 WCAG 2.5.8 的例外（2026-10-12）。

真實瀏覽器測試需要 Chromium：設 ARGUS_TEST_CHROMIUM_PATH 指向執行檔，沒有就略過。
"""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.scans.crawler import collect_ux_signals

CHROMIUM = os.environ.get("ARGUS_TEST_CHROMIUM_PATH", "")

HTML = """<html><body style="margin:0;font-size:14px">
  <p>對掃描流量有疑問，請透過<a id="inline" href="/partners">聯絡我們</a>頁面與我們聯繫。</p>
  <ul><li><a id="alone" href="/terms">服務條款</a></li></ul>
  <label style="display:flex;min-height:44px;width:300px">
    <input type="checkbox" name="ok">我同意</label>
  <input type="checkbox" name="bare">
  <a id="bar" href="/bar" style="display:block;width:300px;height:39px">寬橫條</a>
  <a id="tiny" href="/tiny" style="display:inline-block;width:30px;height:30px">小</a>
</body></html>"""


@unittest.skipUnless(
    CHROMIUM and Path(CHROMIUM).exists(), "需要 Chromium（ARGUS_TEST_CHROMIUM_PATH）"
)
class InlineLinkTapTargetTests(SimpleTestCase):
    def _signals(self) -> dict:
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path=CHROMIUM)
                page = await browser.new_page(viewport={"width": 375, "height": 800})
                await page.set_content(HTML)
                result = await collect_ux_signals(page)
                await browser.close()
                return result

        return asyncio.run(run())

    def test_link_inside_sentence_is_exempt_but_standalone_link_is_not(self):
        labels = [t["label"] for t in self._signals().get("small_tap_targets", [])]
        self.assertNotIn("聯絡我們", labels)
        self.assertIn("服務條款", labels)

    def test_wide_bar_is_not_small_but_square_under_40_is(self):
        # 短邊 39 ≥ 24 且長邊 300 ≥ 40 的橫條點得到；30×30 兩邊都不到 40 仍列
        labels = [t["label"] for t in self._signals().get("small_tap_targets", [])]
        self.assertNotIn("寬橫條", labels)
        self.assertIn("小", labels)

    def test_checkbox_wrapped_in_large_label_is_exempt(self):
        selectors = [t["selector"] for t in self._signals().get("small_tap_targets", [])]
        self.assertEqual(sum(1 for s in selectors if s.startswith("input")), 1)
