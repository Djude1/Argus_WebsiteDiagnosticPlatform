"""把一個網站專案的已完成掃描匯出成示範專案資料（apps/scans/demo/）。

只在重新產生示範資料時使用（步驟見 apps/scans/demo/README.md）：先用
scripts/demo_site/server.py 的三個版本各跑一次真實掃描，再執行本命令。
截圖會轉成 128 色 PNG 存到 demo/screenshots/（約為原始大小的四分之一）。
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

from apps.scans.demo.seed import (
    DATASET_PATH,
    FINDING_FIELDS,
    PAGE_FIELDS,
    SCAN_FIELDS,
    SCREENSHOT_DIR,
)
from apps.scans.models import FixOutput, ScanJob, SiteProject


def _iso(value):
    return value.isoformat() if value else None


class Command(BaseCommand):
    help = "把網站專案的已完成掃描匯出為示範專案資料（開發用）"

    def add_arguments(self, parser):
        parser.add_argument("project_id", type=int)

    def handle(self, *args, **options):
        project = SiteProject.objects.filter(id=options["project_id"]).first()
        if project is None:
            raise CommandError("找不到這個專案。")
        scans = list(
            ScanJob.objects.filter(project=project, status=ScanJob.Status.COMPLETED).order_by(
                "completed_at"
            )
        )
        if not scans:
            raise CommandError("這個專案沒有已完成的掃描。")

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        for old in SCREENSHOT_DIR.glob("*.png"):
            old.unlink()

        exported = []
        for number, scan in enumerate(scans, start=1):
            pages = list(scan.pages.order_by("depth", "id"))
            index = {page.id: i for i, page in enumerate(pages)}
            page_rows = []
            for i, page in enumerate(pages):
                row = {field: getattr(page, field) for field in PAGE_FIELDS}
                row["screenshot_path"] = self._export_screenshot(
                    page.screenshot_path, f"scan{number}-page{i + 1}.png"
                )
                page_rows.append(row)
            finding_rows = []
            for finding in scan.findings.order_by("id"):
                row = {field: getattr(finding, field) for field in FINDING_FIELDS}
                row["page_index"] = index.get(finding.page_id)
                finding_rows.append(row)
            scan_row = {field: getattr(scan, field) for field in SCAN_FIELDS}
            # 產生資料的開發機沒有安裝 Nuclei／Katana；這行只反映開發環境，正式環境不會出現
            scan_row["scan_log"] = [
                entry
                for entry in scan_row["scan_log"]
                if "binary 未安裝" not in str(entry.get("msg", ""))
            ]
            for field in ("created_at", "started_at", "completed_at"):
                scan_row[field] = _iso(getattr(scan, field))
            fix_output = FixOutput.objects.filter(
                scan_job=scan, status=FixOutput.Status.READY
            ).first()
            scan_row["fix_output"] = (
                {
                    "artifacts": fix_output.artifacts,
                    "provider": fix_output.provider,
                    "model_id": fix_output.model_id,
                }
                if fix_output
                else None
            )
            exported.append({"scan": scan_row, "pages": page_rows, "findings": finding_rows})

        dataset = {
            "format": 1,
            "project": {
                "name": project.name,
                "origin": project.origin,
                "start_url": project.start_url,
                "default_scope": project.default_scope,
                "default_categories": project.default_categories,
                "favicon": project.favicon,
            },
            "scans": exported,
        }
        raw = json.dumps(dataset, ensure_ascii=False, default=str).encode("utf-8")
        DATASET_PATH.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
        size = DATASET_PATH.stat().st_size // 1024
        shots = sum(p.stat().st_size for p in SCREENSHOT_DIR.glob("*.png")) // 1024
        self.stdout.write(
            self.style.SUCCESS(f"已匯出 {len(scans)} 次掃描：資料 {size} KB、截圖 {shots} KB")
        )

    def _export_screenshot(self, relative: str, name: str) -> str:
        if not relative:
            return ""
        source = Path(settings.BASE_DIR) / relative
        if not source.exists():
            return ""
        image = (
            Image.open(source).convert("RGB").quantize(colors=128, method=Image.Quantize.FASTOCTREE)
        )
        buffer = io.BytesIO()
        image.save(buffer, "PNG", optimize=True)
        (SCREENSHOT_DIR / name).write_bytes(buffer.getvalue())
        return str((SCREENSHOT_DIR / name).relative_to(settings.BASE_DIR))
