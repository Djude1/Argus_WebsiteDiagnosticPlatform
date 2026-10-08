"""爬取預算的可觀測性（roadmap「爬取」第 2 項）。

crawler._CrawlState.budget_summary 整理數字、tasks.crawl_budget_text 寫成一行說明。
"""

from __future__ import annotations

from urllib.robotparser import RobotFileParser

from django.test import SimpleTestCase

from apps.scans.crawler import _CrawlState
from apps.scans.tasks import crawl_budget_text

ORIGIN = "https://shop.example.tw"


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
