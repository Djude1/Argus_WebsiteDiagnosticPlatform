from django.core.management.base import BaseCommand, CommandError

from apps.scans.models import Finding, ScanJob
from apps.scans.scanners import (
    PageAnalysisInput,
    analyze_page,
    analyze_security_site_level,
    calculate_scores,
)


class Command(BaseCommand):
    """以 ScanJob 已儲存的頁面內容重跑掃描器（cache replay）。

    用途：修改 scanner 邏輯後，不必再向目標站發請求即可重新產生 findings。
    被阻擋的頁面（`blocked_reason` 非空）不參與頁面層級掃描，與正式爬蟲流程一致；
    但仍會被納入站台層級的 HTTPS/HSTS/CSP 等安全標頭檢查判斷（見
    analyze_security_site_level，會自行排除 blocked 頁面挑合適的代表頁）。
    站台層級的 GEO FAST 訊號（llms.txt、AI 爬蟲）目前未保存於資料庫，
    故 replay 不會重新產生這部分 finding。
    """

    help = "用 ScanJob 已儲存的頁面內容重跑掃描器（cache replay），不向目標站發請求。"

    def add_arguments(self, parser):
        parser.add_argument("scan_id", type=int, help="要重跑的 ScanJob ID")
        parser.add_argument(
            "--keep-findings",
            action="store_true",
            help="保留原 findings，僅追加新 findings（預設會先刪除原 findings）",
        )

    def handle(self, *args, **options):
        scan_id = options["scan_id"]
        try:
            scan_job = ScanJob.objects.get(id=scan_id)
        except ScanJob.DoesNotExist as exc:
            raise CommandError(f"找不到 ScanJob id={scan_id}") from exc

        if not options["keep_findings"]:
            removed, _ = scan_job.findings.all().delete()
            self.stdout.write(f"已刪除 {removed} 個既有 findings")

        all_findings: list[dict] = []
        pages_processed = 0
        for page in scan_job.pages.filter(blocked_reason="").iterator():
            page_findings = analyze_page(
                PageAnalysisInput(
                    url=page.url,
                    final_url=page.final_url,
                    title=page.title,
                    html=page.html,
                    headers=page.headers,
                    element_boxes=page.element_boxes,
                    html_only=page.html_only_text,
                )
            )
            for finding in page_findings:
                Finding.objects.create(scan_job=scan_job, page=page, **finding)
            all_findings.extend(page_findings)
            pages_processed += 1

        # HTTPS/HSTS/CSP/X-Frame-Options/X-Content-Type-Options 已從 analyze_page()
        # 搬到站台層級（只評估一次，見 scanners.py::analyze_security_site_level）。
        # replay 若漏呼叫，這批 finding 會在上面 --keep-findings 預設的刪除步驟後
        # 永久消失、不會重新產生。
        site_level_pages = [
            {
                "headers": page.headers,
                "final_url": page.final_url,
                "url": page.url,
                "blocked_reason": page.blocked_reason,
            }
            for page in scan_job.pages.all()
        ]
        site_level_findings = analyze_security_site_level(site_level_pages)
        for finding in site_level_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(site_level_findings)

        overall_score, category_scores, top_actions = calculate_scores(all_findings)
        scan_job.overall_score = overall_score
        scan_job.category_scores = category_scores
        scan_job.top_actions = top_actions
        scan_job.save(
            update_fields=[
                "overall_score",
                "category_scores",
                "top_actions",
                "updated_at",
            ]
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"已重新掃描 ScanJob {scan_id}："
                f"{pages_processed} 頁、{len(all_findings)} 個 findings"
            )
        )
