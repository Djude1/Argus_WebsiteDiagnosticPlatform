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
    run_agent_ux: bool
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

    # AI Agent 擬真使用者 UX 測試：只要是全網站掃描且勾選 UX 維度就跑，不需要
    # 主動授權（純 UX 測試不做破壞性操作）。是否可實際送出表單另由網域驗證決定，
    # 見 runner.run_agent_for_scan 的 may_submit_forms。單頁掃描不跑（一頁不足以
    # 測流程，且要省 LLM token）。
    run_agent_ux = scope == "site" and "ux" in scan_job.effective_categories

    return ScanExecutionPlan(
        scope=scope,
        active_authorized=active_authorized,
        run_nuclei=active_authorized,
        run_katana=site_active,
        run_exposure=site_active,
        run_agent=site_active,
        run_agent_ux=run_agent_ux,
        run_kali=active_authorized,
    )
