"""補抓網站專案圖示：預設只處理還沒有圖示的未封存專案（新增專案時就會抓，這是給升級前的舊專案用）。

用法：
  manage.py refresh_project_favicons            # 只補沒有圖示的
  manage.py refresh_project_favicons --all      # 全部重抓（抓不到的保留舊圖示）
  manage.py refresh_project_favicons --dry-run  # 只列出會處理哪些
"""

from django.core.management.base import BaseCommand

from apps.scans.favicon import refresh_project_favicon_from_url
from apps.scans.models import SiteProject


class Command(BaseCommand):
    help = "補抓網站專案的網站圖示（favicon）"

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="已有圖示的專案也重抓")
        parser.add_argument("--dry-run", action="store_true", help="只列出，不連線")

    def handle(self, *args, **options):
        projects = SiteProject.objects.active().order_by("id")
        if not options["all"]:
            projects = projects.filter(favicon="")
        updated = 0
        for project in projects:
            if options["dry_run"]:
                self.stdout.write(f"#{project.id} {project.origin}")
                continue
            refresh_project_favicon_from_url(project)
            project.refresh_from_db(fields=["favicon"])
            ok = bool(project.favicon)
            updated += ok
            self.stdout.write(f"#{project.id} {project.origin}：{'已取得' if ok else '抓不到'}")
        if not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"完成，{updated} 個專案有圖示。"))
