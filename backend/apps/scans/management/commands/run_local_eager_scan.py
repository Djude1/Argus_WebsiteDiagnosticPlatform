from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.scans.tasks import run_scan_job


class Command(BaseCommand):
    """在獨立程序主執行緒執行本機 eager 掃描。"""

    help = "內部本機開發命令：在獨立程序執行一筆 eager 掃描。"

    def add_arguments(self, parser):
        parser.add_argument("scan_id", type=int)

    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.CELERY_TASK_ALWAYS_EAGER:
            raise CommandError("此命令只允許 DEBUG 的本機 eager 模式使用。")

        scan_id = options["scan_id"]
        run_scan_job.apply(args=(scan_id,), throw=True)
        self.stdout.write(self.style.SUCCESS(f"本機掃描 {scan_id} 已結束。"))
