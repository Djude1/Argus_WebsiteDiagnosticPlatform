"""複刻產出的清理命令。

清理作業的危險在於「刪太多」與「刪不掉」都不會有人立刻發現：
刪太多是使用者的檔案憑空消失，刪不掉是 PVC 靜靜長到寫滿。
"""

from __future__ import annotations

import os
import tempfile
import time
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings


class CleanupRebuildsCommandTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.media = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _make(self, scan: int, page: int, age_days: float) -> Path:
        directory = self.media / "rebuilds" / f"scan-{scan}" / f"page-{page}"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "optimized.html"
        target.write_text("<html></html>", encoding="utf-8")
        stamp = time.time() - age_days * 86400
        os.utime(target, (stamp, stamp))
        return directory

    def _run(self, **kwargs) -> str:
        out = StringIO()
        with override_settings(MEDIA_ROOT=self.media):
            call_command("cleanup_rebuilds", stdout=out, **kwargs)
        return out.getvalue()

    def test_removes_only_expired_directories(self):
        old = self._make(1, 1, age_days=40)
        fresh = self._make(1, 2, age_days=1)
        self._run(older_than_days=30)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists(), "未逾期的產出不得被刪")

    def test_dry_run_deletes_nothing(self):
        old = self._make(2, 1, age_days=99)
        output = self._run(older_than_days=30, dry_run=True)
        self.assertTrue(old.exists())
        self.assertIn("dry-run", output)

    def test_page_directories_are_judged_independently(self):
        """用掃描層目錄的時間判斷，會讓新頁面替同掃描的舊頁面續命，永遠刪不掉。"""
        old = self._make(3, 1, age_days=99)
        fresh = self._make(3, 2, age_days=0)
        self._run(older_than_days=30)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_missing_directory_is_not_an_error(self):
        output = self._run(older_than_days=30)
        self.assertIn("不存在", output)

    def test_rejects_zero_days(self):
        """--older-than-days 0 會刪光全部，必須擋下來。"""
        recent = self._make(4, 1, age_days=0)
        self._run(older_than_days=0)
        self.assertTrue(recent.exists())
