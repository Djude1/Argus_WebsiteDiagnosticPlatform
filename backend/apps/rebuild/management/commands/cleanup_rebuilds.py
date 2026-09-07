"""清理逾期的網頁複刻產出。

`media/rebuilds/scan-<id>/page-<id>/{original,optimized}.html` 每次複刻都會寫兩份
完整網頁。單份不大，但這是使用者可以重複觸發的操作——沒有清理機制的話，media
volume（正式站是 5Gi 的 RWX PVC）會被慢慢吃光。

磁碟寫滿的後果不只是這個功能壞掉：同一個 volume 上還有截圖與報告，截圖寫入失敗
曾經導致整頁被丟進 failed_urls（見 apps/scans/tests_crawler_screenshot.py）。

刪掉檔案後 SiteRebuild 紀錄仍保留（狀態與錯誤訊息是稽核資訊），只是下載會回 404，
使用者可以重新產生。
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "刪除逾期的網頁複刻產出檔案"

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=30,
            help="刪除超過這個天數未被更新的複刻目錄（預設 30）",
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

        root = Path(settings.MEDIA_ROOT) / "rebuilds"
        if not root.exists():
            self.stdout.write("複刻目錄不存在，沒有需要清理的檔案。")
            return

        cutoff = time.time() - days * 86400
        removed = 0
        freed_bytes = 0
        # 逐頁目錄判斷，不是逐掃描：同一次掃描的不同頁面可能在不同時間產生，
        # 用掃描層目錄的時間會讓舊頁面被新頁面「續命」而永遠刪不掉。
        for scan_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for page_dir in sorted(p for p in scan_dir.iterdir() if p.is_dir()):
                try:
                    files = [f for f in page_dir.rglob("*") if f.is_file()]
                    newest = max((f.stat().st_mtime for f in files), default=None)
                    size = sum(f.stat().st_size for f in files)
                except OSError:
                    continue
                if newest is None or newest >= cutoff:
                    continue
                removed += 1
                freed_bytes += size
                if dry_run:
                    self.stdout.write(
                        f"[dry-run] 會刪除 {scan_dir.name}/{page_dir.name}/"
                        f"（{len(files)} 個檔案）"
                    )
                    continue
                try:
                    shutil.rmtree(page_dir)
                except OSError as exc:
                    self.stderr.write(
                        f"刪除 {scan_dir.name}/{page_dir.name}/ 失敗："
                        f"{exc.__class__.__name__}"
                    )
            # 掃描層目錄清空後一併移除，避免留下大量空目錄拖慢後續走訪
            if not dry_run:
                try:
                    if not any(scan_dir.iterdir()):
                        scan_dir.rmdir()
                except OSError:
                    pass

        verb = "會刪除" if dry_run else "已刪除"
        self.stdout.write(
            f"{verb} {removed} 個逾期複刻產出目錄（{freed_bytes / 1024 / 1024:.1f} MB），"
            f"保留期限 {days} 天。SiteRebuild 紀錄未受影響。"
        )
