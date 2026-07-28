"""依既有掃描範圍與主動授權產生單一執行計畫。"""

from dataclasses import dataclass
from typing import Literal

from apps.scans.models import ScanJob


@dataclass(frozen=True)
class ScanExecutionPlan:
    scope: Literal["single", "site"]
    active_authorized: bool
    run_nuclei: bool
    run_katana: bool
    run_exposure: bool
    run_agent: bool
    run_kali: bool


def build_scan_execution_plan(scan_job: ScanJob) -> ScanExecutionPlan:
    """集中決定各工具是否可執行，避免單頁或被動掃描越過使用者選擇。

    現有資料模型沒有獨立 scope 欄位；前端以 max_pages=1 表示單頁，
    其餘值表示全網站。主動工具必須同時具備 active 模式與額外授權。
    """
    scope: Literal["single", "site"] = "single" if scan_job.max_pages == 1 else "site"
    active_authorized = (
        scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
        and scan_job.active_testing_authorized
    )
    site_active = active_authorized and scope == "site"

    return ScanExecutionPlan(
        scope=scope,
        active_authorized=active_authorized,
        run_nuclei=active_authorized,
        run_katana=site_active,
        run_exposure=site_active,
        run_agent=site_active,
        run_kali=active_authorized,
    )
