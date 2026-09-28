"""把既有掃描的發現套用目前的判定規則並重新計分（說明見 apps/scans/finding_normalization.py）。

用法：
  manage.py renormalize_findings --scan-id 70
  manage.py renormalize_findings --all
"""

from django.core.management.base import BaseCommand, CommandError

from apps.scans.finding_normalization import renormalize_scan
from apps.scans.models import ScanJob


class Command(BaseCommand):
    help = "既有掃描套用新版 PII／AI 觀察／Cookie 判定並重新計分（不重新爬取）"

    def add_arguments(self, parser):
        parser.add_argument("--scan-id", type=int, action="append", default=[])
        parser.add_argument("--all", action="store_true", help="處理所有已完成的掃描")

    def handle(self, *args, **options):
        if not options["scan_id"] and not options["all"]:
            raise CommandError("請指定 --scan-id 或 --all")
        scans = ScanJob.objects.filter(status=ScanJob.Status.COMPLETED)
        if options["scan_id"]:
            scans = scans.filter(pk__in=options["scan_id"])
        for scan in scans.order_by("pk"):
            before = scan.overall_score
            counts = renormalize_scan(scan)
            if any(counts.values()):
                scan.refresh_from_db(fields=["overall_score"])
                self.stdout.write(
                    f"scan {scan.pk}: PII {counts['pii']}、AI 觀察 {counts['agent']}、"
                    f"Cookie {counts['cookie']} 筆調整；分數 {before} → {scan.overall_score}"
                )
