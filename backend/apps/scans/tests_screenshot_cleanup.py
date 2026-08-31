"""截圖保留期限（2026-08-31 事故的後續防護）。

`media/scans/<掃描id>/page-N.png` 從專案開始就沒有任何清理機制。截圖是全頁擷取、
體積遠大於報告，是 media volume 上真正無限成長的那一塊——磁碟寫滿會讓 crawler
存不了截圖，而修正前那會讓整頁分析一起消失。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


class CleanupScreenshotsCommandTests(SimpleTestCase):
    """用暫存 MEDIA_ROOT，不碰開發用的 backend/media/。"""

    def setUp(self):
        self.media_root = Path(tempfile.mkdtemp(prefix="argus-shots-"))
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.root = self.media_root / "scans"
        self.root.mkdir(parents=True, exist_ok=True)
        patcher = override_settings(MEDIA_ROOT=str(self.media_root))
        patcher.enable()
        self.addCleanup(patcher.disable)

    def _scan_dir(self, scan_id: int, *, age_days: int) -> Path:
        directory = self.root / str(scan_id)
        directory.mkdir(parents=True, exist_ok=True)
        shot = directory / "page-1.png"
        shot.write_bytes(b"fake-png")
        stamp = time.time() - age_days * 86400
        os.utime(shot, (stamp, stamp))
        os.utime(directory, (stamp, stamp))
        return directory

    def test_old_screenshot_directories_are_removed(self):
        stale = self._scan_dir(9001, age_days=120)

        call_command("cleanup_screenshots", "--older-than-days", "90")

        self.assertFalse(stale.exists())

    def test_recent_screenshots_are_kept(self):
        fresh = self._scan_dir(9002, age_days=2)

        call_command("cleanup_screenshots", "--older-than-days", "90")

        self.assertTrue((fresh / "page-1.png").exists())

    def test_dry_run_does_not_delete(self):
        stale = self._scan_dir(9003, age_days=120)

        call_command("cleanup_screenshots", "--older-than-days", "90", "--dry-run")

        self.assertTrue((stale / "page-1.png").exists())
