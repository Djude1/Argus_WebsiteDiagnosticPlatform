"""清理逾期的頁面截圖。

`media/scans/<掃描id>/page-N.png` 是全頁擷取，體積遠大於報告，而且從專案開始就
沒有任何清理機制——這是 media volume 上真正無限成長的那一塊。

為什麼重要：磁碟寫滿時 crawler 存不了截圖。2026-08-31 修正前，截圖寫入失敗會讓
整頁被丟進 failed_urls，掃描變成「0 頁」、SEO/AEO 分析整個消失（見
apps/scans/tests_crawler_screenshot.py）。現在截圖失敗已經隔離，但磁碟仍該定期清。

刪掉截圖後，該次掃描的畫面佐證就沒有了（前端與報告都會略過），其餘結果不受影響。
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "刪除逾期掃描的頁面截圖目錄"

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=90,
            help="刪除超過這個天數未被更新的截圖目錄（預設 90）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只列出會被刪除的目錄，不實際刪除",
        )

    def handle(self, *args, **options):
        days = options["older_than_days"]
        dry_run = options["dry_run"]
        if days < 1:
            self.stderr.write("--older-than-days 必須至少為 1。")
            return

        root = Path(settings.MEDIA_ROOT) / "scans"
        if not root.exists():
            self.stdout.write("截圖目錄不存在，沒有需要清理的檔案。")
            return

        cutoff = time.time() - days * 86400
        removed = 0
        freed_bytes = 0
        for directory in sorted(p for p in root.iterdir() if p.is_dir()):
            try:
                # 以目錄內最新的檔案為準：目錄本身的 mtime 在某些檔案系統上不可靠
                files = [f for f in directory.rglob("*") if f.is_file()]
                newest = max((f.stat().st_mtime for f in files), default=None)
                size = sum(f.stat().st_size for f in files)
            except OSError:
                continue
            if newest is None or newest >= cutoff:
                continue
            removed += 1
            freed_bytes += size
            if dry_run:
                self.stdout.write(f"[dry-run] 會刪除 {directory.name}/（{len(files)} 個檔案）")
                continue
            try:
                shutil.rmtree(directory)
            except OSError as exc:
                self.stderr.write(f"刪除 {directory.name}/ 失敗：{exc.__class__.__name__}")

        verb = "會刪除" if dry_run else "已刪除"
        self.stdout.write(
            f"{verb} {removed} 個逾期掃描的截圖目錄（{freed_bytes / 1024 / 1024:.1f} MB），"
            f"保留期限 {days} 天。"
        )
