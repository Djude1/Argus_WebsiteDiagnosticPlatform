"""截圖失敗不得讓整頁分析作廢（正式站事故回歸測試）。

事故現象（2026-08-31）：掃描完成，但畫面上截圖空白、SEO 分析整個不見。

根因：`page.screenshot()` 在 `pages.append()` **之前**執行，而它的例外會被外層
的 `except Exception` 接住，把整頁丟進 `failed_urls`。截圖只是輔助資料，卻能讓
整頁的 SEO/AEO 分析與 Page 紀錄一起消失——磁碟寫滿或權限問題時，整次掃描會變成
「0 頁」，只剩站台層級檢查。

SEO/AEO finding 只由 analyze_page() 逐頁產生，所以 0 頁＝這兩類完全沒有結果。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from apps.scans.crawler import _capture_screenshot, _prepare_screenshot_dir


class FakePage:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = 0

    async def screenshot(self, *, path: str, full_page: bool):
        self.calls += 1
        if self.error is not None:
            raise self.error
        Path(path).write_bytes(b"fake-png")


class CaptureScreenshotTests(SimpleTestCase):
    def setUp(self):
        self.warnings: dict = {"blocked_urls": [], "failed_urls": []}

    def _run(self, page, target: Path):
        return asyncio.run(
            _capture_screenshot(page, target, "https://example.com/a", self.warnings)
        )

    def test_successful_capture_returns_the_path(self):
        with mock.patch("pathlib.Path.write_bytes"):
            result = self._run(FakePage(), Path("/tmp/argus-test-shot.png"))

        self.assertEqual(result, Path("/tmp/argus-test-shot.png"))
        self.assertEqual(self.warnings["failed_urls"], [])

    def test_disk_error_does_not_raise(self):
        """磁碟寫滿時例外不能往上冒——冒出去整頁就被丟掉了。"""
        result = self._run(
            FakePage(OSError(28, "No space left on device")),
            Path("/tmp/argus-test-shot.png"),
        )

        self.assertIsNone(result)

    def test_failure_is_recorded_as_a_screenshot_warning_not_a_failed_page(self):
        """要記錄，但不能記進 failed_urls——那會讓報告誤報成「頁面擷取失敗」。"""
        self._run(FakePage(OSError("boom")), Path("/tmp/argus-test-shot.png"))

        self.assertEqual(self.warnings["failed_urls"], [])
        self.assertEqual(len(self.warnings["screenshot_failures"]), 1)
        self.assertEqual(
            self.warnings["screenshot_failures"][0]["url"], "https://example.com/a"
        )

    def test_timeout_is_also_survivable(self):
        result = self._run(FakePage(TimeoutError()), Path("/tmp/argus-test-shot.png"))

        self.assertIsNone(result)


class PrepareScreenshotDirTests(SimpleTestCase):
    def test_unwritable_directory_returns_none_instead_of_raising(self):
        """建目錄失敗（磁碟滿、唯讀掛載）不能讓整次掃描還沒開始就炸掉。"""
        warnings: dict = {"blocked_urls": [], "failed_urls": []}
        with mock.patch(
            "pathlib.Path.mkdir", side_effect=OSError(28, "No space left on device")
        ):
            result = _prepare_screenshot_dir(Path("/tmp/argus-nope"), warnings)

        self.assertIsNone(result)
        self.assertIn("screenshot_failures", warnings)

    def test_writable_directory_is_returned(self):
        warnings: dict = {"blocked_urls": [], "failed_urls": []}
        with mock.patch("pathlib.Path.mkdir"):
            result = _prepare_screenshot_dir(Path("/tmp/argus-ok"), warnings)

        self.assertEqual(result, Path("/tmp/argus-ok"))
        self.assertEqual(warnings.get("screenshot_failures", []), [])
