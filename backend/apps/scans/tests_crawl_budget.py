"""爬取預算的可觀測性（roadmap「爬取」第 2 項）。

crawler._CrawlState.budget_summary 整理數字、tasks.crawl_budget_text 寫成一行說明。
"""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from urllib.robotparser import RobotFileParser

from django.test import SimpleTestCase

from apps.scans.crawler import _CrawlState, wait_for_render_ready
from apps.scans.tasks import crawl_budget_text

ORIGIN = "https://shop.example.tw"
CHROMIUM = os.environ.get("ARGUS_TEST_CHROMIUM_PATH", "")


def _allow_all() -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse([])
    return parser


class CrawlBudgetTests(SimpleTestCase):
    def test_counts_sources_skips_and_drops(self):
        state = _CrawlState(f"{ORIGIN}/", ORIGIN, max_depth=1, max_pages=3)
        self.assertEqual(state.seed([f"{ORIGIN}/a", f"{ORIGIN}/a", f"{ORIGIN}/b"]), 2)
        url, depth = state.next_target(_allow_all(), respect_robots=False)
        state.pages.append({"url": url})
        # 已有 1 頁、佇列 2 個 → 已達上限，新連結都不會排入
        state.enqueue_links([f"{ORIGIN}/c", f"{ORIGIN}/d"], depth)
        state.queue.append((f"{ORIGIN}/deep", 2))
        state.page_seconds += [(1.5, f"{ORIGIN}/"), (4.0, f"{ORIGIN}/a")]
        state.throttle_waits, state.throttle_wait_seconds = 2, 0.75
        while state.next_target(_allow_all(), respect_robots=False):
            pass

        budget = state.budget_summary("max_pages", 12.3)
        self.assertEqual(budget["seeds"], {"start": 1, "sitemap": 2})
        self.assertEqual(budget["links_queued"], 0)
        self.assertEqual(budget["links_dropped_limit"], 2)
        self.assertEqual(budget["skipped_depth"], 1)
        self.assertEqual(budget["throttle_wait_ms"], 750)
        self.assertEqual(budget["page_ms_avg"], 2750)
        self.assertEqual(budget["slowest_pages"][0], {"url": f"{ORIGIN}/a", "ms": 4000})
        self.assertEqual(budget["elapsed_ms"], 12300)

    def test_robots_skips_are_counted(self):
        state = _CrawlState(f"{ORIGIN}/", ORIGIN, max_depth=3, max_pages=5)
        robots = RobotFileParser()
        robots.parse(["User-agent: *", "Disallow: /"])
        self.assertIsNone(state.next_target(robots, respect_robots=True))
        self.assertEqual(state.budget_summary("queue_exhausted", 1)["skipped_robots"], 1)

    def test_log_line_explains_why_crawl_stopped(self):
        text = crawl_budget_text({
            "stop_reason": "max_pages", "pages": 50, "max_pages": 50, "elapsed_ms": 183000,
            "seeds": {"start": 1, "sitemap": 30}, "links_queued": 19,
            "links_dropped_limit": 120, "skipped_depth": 0, "skipped_robots": 1, "failed": 0,
            "throttle_waits": 49, "throttle_wait_ms": 24500, "page_ms_avg": 3200,
        })
        self.assertIn("爬取結束：達到頁數上限（50／50 頁，耗時 183 秒）", text)
        self.assertIn("來源：起始網址 1、sitemap 30、頁面連結 19", text)
        self.assertIn("略過：超過頁數上限未排入 120、robots.txt 禁止 1", text)
        self.assertNotIn("超過深度", text)
        self.assertIn("速率限制等待 49 次共 24 秒", text)
        self.assertIn("每頁平均 3.2 秒", text)

    def test_already_queued_links_do_not_take_page_slots(self):
        state = _CrawlState(f"{ORIGIN}/", ORIGIN, max_depth=3, max_pages=4)
        state.seed([f"{ORIGIN}/a", f"{ORIGIN}/b"])
        url, depth = state.next_target(_allow_all(), respect_robots=False)
        state.pages.append({"url": url})
        # 首頁連到 sitemap 已排入的 a、b，再加一個新頁 c：c 必須排得進去
        state.enqueue_links([f"{ORIGIN}/a", f"{ORIGIN}/b", f"{ORIGIN}/c", f"{ORIGIN}/c"], depth)
        self.assertEqual([u for u, _ in state.queue], [f"{ORIGIN}/a", f"{ORIGIN}/b", f"{ORIGIN}/c"])
        self.assertEqual(state.links_queued, 1)
        self.assertEqual(state.links_dropped_limit, 0)

    def test_render_readiness_summary_and_log(self):
        state = _CrawlState(f"{ORIGIN}/", ORIGIN, max_depth=1, max_pages=3)
        state.render_ready += [
            ("ready", 500, f"{ORIGIN}/"), ("timeout", 5000, f"{ORIGIN}/spa"),
            ("ready", 1000, f"{ORIGIN}/a"),
        ]
        ready = state.budget_summary("max_pages", 9)["render_readiness"]
        self.assertEqual(ready, {
            "ready": 2, "timeout": 1, "error": 0, "avg_ms": 2167,
            "timeout_urls": [f"{ORIGIN}/spa"],
        })
        self.assertIsNone(_CrawlState(f"{ORIGIN}/", ORIGIN, 1, 1).budget_summary("x", 0)[
            "render_readiness"
        ])
        text = crawl_budget_text({"stop_reason": "max_pages", "render_readiness": ready})
        self.assertIn("等內容穩定平均 2.2 秒，1 頁在上限內未穩定（照樣擷取，內容可能不完整）", text)


@unittest.skipUnless(
    CHROMIUM and Path(CHROMIUM).exists(), "需要 Chromium（ARGUS_TEST_CHROMIUM_PATH）"
)
class RenderReadinessRealBrowserTests(SimpleTestCase):
    # 1.2 秒後才把內容放進空的 root（模擬前端框架 hydration）
    HYDRATES_LATE = """<html><body><div id="root"></div><script>
      setTimeout(() => {
        const root = document.getElementById("root");
        root.innerHTML = "<h1>商品</h1>" + "<p>內容段落</p>".repeat(30);
      }, 1200);</script></body></html>"""
    # 輪播每 200ms 換一句長度差不多的文字：應視為穩定
    CAROUSEL = """<html><body><main><p>""" + "固定內容。" * 200 + """</p>
      <p id="slide">第 1 則公告</p></main><script>
      let n = 1;
      const slide = document.getElementById("slide");
      setInterval(() => { n += 1; slide.textContent = `第 ${n} 則公告`; }, 200);
      </script></body></html>"""
    # 每 200ms 一直新增段落：永遠不穩定，必須在上限內放棄
    NEVER_STABLE = """<html><body><main id="feed"></main><script>
      setInterval(() => {
        const p = document.createElement("p");
        p.textContent = "新的動態消息內容，持續增加中。".repeat(3);
        document.getElementById("feed").appendChild(p);
      }, 200);</script></body></html>"""

    def _ready(self, html: str, max_seconds: float = 5) -> tuple[dict, int]:
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path=CHROMIUM)
                page = await browser.new_page()
                await page.route(
                    "http://ready.test/",
                    lambda route: route.fulfill(body=html, content_type="text/html; charset=utf-8"),
                )
                await page.goto("http://ready.test/", wait_until="domcontentloaded")
                result = await wait_for_render_ready(page, max_seconds)
                text = await page.evaluate("document.body.innerText.length")
                await browser.close()
                return result, text

        return asyncio.run(run())

    def test_waits_for_late_hydration(self):
        result, text = self._ready(self.HYDRATES_LATE)
        self.assertEqual(result["status"], "ready")
        self.assertGreaterEqual(result["ms"], 1200)
        self.assertGreater(text, 100)

    def test_small_carousel_changes_count_as_stable(self):
        result, _ = self._ready(self.CAROUSEL)
        self.assertEqual(result["status"], "ready")
        self.assertLess(result["ms"], 1500)

    def test_never_stable_page_gives_up_at_the_limit(self):
        result, _ = self._ready(self.NEVER_STABLE, max_seconds=1.5)
        self.assertEqual(result["status"], "timeout")
        self.assertLess(result["ms"], 2500)
