"""回收卡住的掃描。

worker pod 被 rollout／OOM／節點驅逐砍掉時是 SIGKILL，run_scan_job 的任何 except
都跑不到，ScanJob 會永遠停在 crawling／scanning，預扣的 coin 永遠不退。使用者實際
遇過一次（卡 95 分鐘），而每次部署都會重新觸發。

設計成 management command 而不是 Celery beat 任務：專案目前沒有 beat，為了一支
維護作業多開一個常駐程序不划算；K8s CronJob 呼叫這支即可，且 worker 全掛時
CronJob 仍跑得動——正好是最需要它的時候。
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.scans.tasks import reap_stale_scans


class Command(BaseCommand):
    help = "把超過執行上限仍停在非終態的掃描收斂成 failed 並冪等退款"

    def handle(self, *args, **options):
        reaped = reap_stale_scans()
        if reaped:
            self.stdout.write(f"已回收 {reaped} 筆卡住的掃描，預扣點數已退回。")
        else:
            self.stdout.write("沒有卡住的掃描。")
