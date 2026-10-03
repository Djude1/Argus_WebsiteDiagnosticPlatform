"""為既有帳號建立示範專案（新帳號在註冊時已自動建立）。

  manage.py seed_demo_project --email someone@example.com
  manage.py seed_demo_project --without-projects        # 所有還沒有任何網站專案的帳號
  manage.py seed_demo_project --without-projects --dry-run

已有示範專案（含已封存）的帳號不會重複建立；封存＝使用者不想看，也不會被補回來。
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.scans.demo.seed import DATASET_PATH, create_demo_project


class Command(BaseCommand):
    help = "為既有帳號建立示範專案"

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--email", help="只為這個帳號建立")
        target.add_argument(
            "--without-projects",
            action="store_true",
            help="為所有還沒有任何網站專案（含已封存）的帳號建立",
        )
        parser.add_argument("--dry-run", action="store_true", help="只列出會建立的帳號數")

    def handle(self, *args, **options):
        if not DATASET_PATH.exists():
            raise CommandError("找不到示範資料 apps/scans/demo/dataset.json.gz。")
        users = get_user_model().objects.filter(is_active=True)
        if options["email"]:
            users = users.filter(email__iexact=options["email"])
            if not users.exists():
                raise CommandError("找不到這個帳號。")
        else:
            users = users.filter(site_projects__isnull=True)
        users = users.distinct().order_by("id")

        if options["dry_run"]:
            self.stdout.write(f"[dry-run] 會為 {users.count()} 個帳號建立示範專案")
            return
        created = 0
        for user in users.iterator():
            if create_demo_project(user) is not None:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"已建立 {created} 個示範專案"))
