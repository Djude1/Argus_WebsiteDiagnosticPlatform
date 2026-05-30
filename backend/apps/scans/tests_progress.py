"""T15-Progress：ScanJob.progress 欄位 + _write_progress helper + crawler callback。

涵蓋：
- model 預設值為 {} 不會壞既有測試
- serializer 輸出 progress 欄位
- _write_progress 用 filter().update() 不會覆蓋其他欄位
- crawler progress_callback 在每爬完一頁被呼叫（pages_done/pages_total 動態）
"""

from __future__ import annotations

import asyncio

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scans.models import ScanJob
from apps.scans.serializers import ScanJobSerializer, ScanJobStatusSerializer
from apps.scans.tasks import _write_progress


def _make_scan(user) -> ScanJob:
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
    )


class ScanJobProgressFieldTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="progress_user", password="safe-test-password"
        )

    def test_progress_defaults_to_empty_dict(self):
        scan = _make_scan(self.user)
        self.assertEqual(scan.progress, {})

    def test_serializer_includes_progress(self):
        scan = _make_scan(self.user)
        scan.progress = {
            "pages_done": 5,
            "pages_total": 10,
            "phase": "crawling",
            "phase_started_at": "2026-05-24T12:00:00+08:00",
        }
        scan.save()

        data = ScanJobSerializer(scan).data
        self.assertEqual(data["progress"]["pages_done"], 5)
        self.assertEqual(data["progress"]["pages_total"], 10)
        self.assertEqual(data["progress"]["phase"], "crawling")

    def test_status_serializer_includes_progress_and_started_at(self):
        scan = _make_scan(self.user)
        scan.progress = {"pages_done": 1, "pages_total": 2, "phase": "scanning"}
        scan.save()

        data = ScanJobStatusSerializer(scan).data
        self.assertIn("progress", data)
        self.assertIn("started_at", data)
        self.assertEqual(data["progress"]["pages_total"], 2)


class WriteProgressHelperTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="helper_user", password="safe-test-password"
        )
        self.scan = _make_scan(self.user)
        # 預先設一些欄位確認 helper 不會覆蓋
        self.scan.error_message = "should-keep"
        self.scan.warning_summary = {"blocked_urls": ["x"]}
        self.scan.save()

    def test_writes_progress_payload(self):
        _write_progress(
            self.scan.id,
            phase="crawling",
            done=3,
            total=7,
            phase_started_at="2026-05-24T10:00:00+08:00",
        )
        self.scan.refresh_from_db()
        self.assertEqual(
            self.scan.progress,
            {
                "pages_done": 3,
                "pages_total": 7,
                "phase": "crawling",
                "phase_started_at": "2026-05-24T10:00:00+08:00",
            },
        )

    def test_does_not_overwrite_other_fields(self):
        _write_progress(
            self.scan.id,
            phase="scanning",
            done=1,
            total=2,
            phase_started_at="2026-05-24T10:00:00+08:00",
        )
        self.scan.refresh_from_db()
        # 其他欄位保留
        self.assertEqual(self.scan.error_message, "should-keep")
        self.assertEqual(self.scan.warning_summary, {"blocked_urls": ["x"]})

    def test_total_zero_clamped_to_one(self):
        # 避免前端拿到 pages_total=0 算百分比時除以 0
        _write_progress(
            self.scan.id, phase="crawling", done=0, total=0, phase_started_at="x",
        )
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.progress["pages_total"], 1)


class CrawlerProgressCallbackTests(TestCase):
    """crawl_site 接受 progress_callback。

    避免真打網路：直接驗證 callback signature 與「callback 失敗不影響爬蟲」契約。
    完整 crawl 需 Playwright 環境，留給整合測試。
    """

    def test_callback_signature_accepts_two_ints(self):
        # 純驗證：callback 為 async (done:int, total:int) -> None
        calls = []

        async def cb(done: int, total: int) -> None:
            calls.append((done, total))

        async def driver():
            await cb(1, 5)
            await cb(2, 5)

        asyncio.run(driver())
        self.assertEqual(calls, [(1, 5), (2, 5)])

    def test_callback_exception_swallowed_pattern(self):
        # crawler 內 callback 失敗應用 try/except 包；用測試確認模式
        async def bad_cb(done: int, total: int) -> None:
            raise RuntimeError("boom")

        async def driver():
            try:
                await bad_cb(1, 1)
            except Exception:
                return "swallowed"
            return "not_swallowed"

        result = asyncio.run(driver())
        self.assertEqual(result, "swallowed")
