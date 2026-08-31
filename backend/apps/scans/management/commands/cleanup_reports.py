"""清理逾期的 Word 報告檔案。

報告寫進 MEDIA_ROOT/reports/ 後永久堆積，加上下載改走快取（不再每次重產），
檔案只會越積越多。這支命令依檔案修改時間刪除逾期的 .docx。

**不刪 ReportVerification 資料列**：收件者手上的那份報告不會因為伺服器清檔就
失效，查驗頁要能繼續回答「這個編號確實是 Argus 為這個網站出具的」。

代價要講清楚：報告被清掉後若有人重新下載，會產生新的一版，內容指紋隨之更新，
先前流出的副本就無法再用指紋比對（報告編號仍然有效）。所以保留期限應該設得比
「使用者還可能拿舊報告來對」的時間長。
"""

from __future__ import annotations

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "刪除逾期的報告檔案（不影響報告編號的查驗）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=180,
            help="刪除超過這個天數未被更新的報告檔案（預設 180）",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只列出會被刪除的檔案，不實際刪除",
        )

    def handle(self, *args, **options):
        days = options["older_than_days"]
        dry_run = options["dry_run"]
        if days < 1:
            self.stderr.write("--older-than-days 必須至少為 1。")
            return

        report_dir = Path(settings.MEDIA_ROOT) / "reports"
        if not report_dir.exists():
            self.stdout.write("報告目錄不存在，沒有需要清理的檔案。")
            return

        cutoff = time.time() - days * 86400
        removed = 0
        freed_bytes = 0
        for path in sorted(report_dir.glob("*.docx")):
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime >= cutoff:
                continue
            removed += 1
            freed_bytes += stat.st_size
            if dry_run:
                self.stdout.write(f"[dry-run] 會刪除 {path.name}")
                continue
            try:
                path.unlink()
            except OSError as exc:
                self.stderr.write(f"刪除 {path.name} 失敗：{exc.__class__.__name__}")

        verb = "會刪除" if dry_run else "已刪除"
        self.stdout.write(
            f"{verb} {removed} 個逾期報告檔案（{freed_bytes / 1024:.1f} KB），"
            f"保留期限 {days} 天。報告編號的查驗紀錄未受影響。"
        )
