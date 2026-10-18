import asyncio
import logging
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from asgiref.sync import sync_to_async
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.billing.services import (
    grant_fixgen_entitlement,
    refund_full_for_scan,
    settle_scan_actual,
)
from apps.scans.aeo.evaluate import SitePage, evaluate_site
from apps.scans.cancellation import ScanCancelled, is_cancelled, raise_if_cancelled
from apps.scans.coverage import (
    COMPLETED,
    FAILED,
    PARTIAL,
    SKIPPED,
    ScanCoverage,
    category_status,
)
from apps.scans.crawler import crawl_site
from apps.scans.favicon import needs_refresh, refresh_project_favicon
from apps.scans.fingerprint import fingerprint_snapshot
from apps.scans.geo_entity import analyze_entity, entity_findings, freshness_findings
from apps.scans.katana_scanner import run_katana
from apps.scans.models import Finding, Page, ScanJob
from apps.scans.nuclei_scanner import NucleiUnavailable, run_nuclei
from apps.scans.pagespeed import PageSpeedError
from apps.scans.pagespeed import enabled as pagespeed_enabled
from apps.scans.pagespeed import fetch as fetch_pagespeed
from apps.scans.scan_logger import append_log
from apps.scans.scan_plan import ScanExecutionPlan, build_scan_execution_plan
from apps.scans.scanners import (
    PageAnalysisInput,
    analyze_page,
    analyze_security_site_level,
    analyze_site_signals,
    calculate_scores,
)
from apps.scans.security import exposure_scanner, owasp_mapper
from apps.scans.security.api_scanner import MAX_SURFACE_ENDPOINTS, analyze_api
from apps.scans.security.authz_probe import (
    analyze_unauthorized_results,
    probe_unauthorized_endpoints,
)
from apps.scans.security.content_injection import (
    build_injection_finding,
    detect_content_injection,
)
from apps.scans.security.cookie_scanner import analyze_cookies
from apps.scans.security.cross_layer import consolidate_cross_layer
from apps.scans.security.dns_scanner import analyze_dns
from apps.scans.security.form_scanner import analyze_password_fields
from apps.scans.security.header_scanner import analyze_headers
from apps.scans.security.js_library_scanner import analyze_js_libraries
from apps.scans.security.kali_tools import validate_findings_with_kali
from apps.scans.security.passive_checks import analyze_passive_html
from apps.scans.security.redaction import (
    redact_pii_in_text,
    redact_url_query_values,
    redact_warning_summary,
)
from apps.scans.security.secret_scanner import (
    build_browser_key_finding,
    build_secret_finding,
    detect_secrets_in_text,
)
from apps.scans.security.service_cve_scanner import analyze_services
from apps.scans.security.sri_scanner import analyze_sri
from apps.scans.security.ssl_scanner import analyze_ssl
from apps.scans.security.vuln_intel import enrich_findings as enrich_vuln_intel
from apps.scans.security.waf_scanner import detect_waf_block
from apps.scans.security.zap_active import active_enabled as zap_active_enabled
from apps.scans.security.zap_active import run_active as run_zap_active
from apps.scans.security.zap_passive import ZapBusy, ZapError, alerts_to_findings
from apps.scans.security.zap_passive import enabled as zap_enabled
from apps.scans.seo.collect import build_link_report
from apps.scans.seo.link_trend import (
    coverage_text,
    crawled_verdicts,
    effective_verdicts,
    link_coverage,
    link_trend,
)
from apps.scans.seo.site_findings import seo_site_findings
from apps.scans.services import assert_public_http_url
from apps.scans.site_profile import build_site_profile
from apps.scans.versions import RULESET_VERSION, SCORING_VERSION

logger = logging.getLogger(__name__)



def _new_event_loop_with_retry():
    """Windows 偶發 WinError 10013 時，只重試尚未開始工作的 event loop 建立。"""
    max_attempts = 3 if sys.platform == "win32" else 1
    for attempt in range(max_attempts):
        try:
            return asyncio.new_event_loop()
        except PermissionError as exc:
            is_windows_socketpair_error = (
                sys.platform == "win32"
                and getattr(exc, "winerror", None) == 10013
            )
            if not is_windows_socketpair_error or attempt + 1 >= max_attempts:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise RuntimeError("無法建立非同步事件迴圈。")


def _run_async(coroutine_factory):
    """用可重試的 loop factory 執行 async 工作，且延後建立 coroutine 避免未 await。"""
    with asyncio.Runner(loop_factory=_new_event_loop_with_retry) as runner:
        return runner.run(coroutine_factory())


# 細分階段（progress.step）：讓前端顯示「現在在分析什麼」。phase 仍只有
# crawling/scanning/agent_testing 三值（既有契約），step 是其下更細的子步驟，
# steps 是本次掃描實際會跑的子步驟清單（依維度與範圍／授權決定）。
ANALYZE_STEP_ORDER = ["seo", "aeo", "geo", "ux", "security"]
CATEGORY_LOG_LABELS = {"seo": "SEO", "aeo": "AEO", "geo": "GEO", "ux": "UX", "security": "資安"}


def planned_scan_steps(scan_job, execution_plan) -> list[str]:
    """本次掃描會經過的子步驟（順序即執行順序）。"""
    cats = scan_job.effective_categories
    steps = ["crawl"]
    steps += [f"analyze_{c}" for c in ANALYZE_STEP_ORDER if c in cats]
    if "aeo" in cats:
        steps.append("aeo_answers")
    if execution_plan.run_nuclei:
        steps.append("active_probe")
    steps.append("deep_security")
    if _runs_zap_active(scan_job):
        steps.append("zap_active")
    if execution_plan.run_exposure:
        steps.append("exposure_probe")
    if "geo" in cats:
        steps.append("geo_site")
    if "seo" in cats:
        steps.append("seo_links")
    if "ux" in cats and pagespeed_enabled():
        steps.append("pagespeed")
    if settings.ARGUS_AGENT_ENABLED and (execution_plan.run_agent or execution_plan.run_agent_ux):
        steps.append("agent")
    steps.append("scoring")
    return steps


def _first_step(steps: list[str], *candidates: str) -> str:
    """回傳 candidates 中第一個會在本次掃描執行的子步驟。"""
    return next((c for c in candidates if c in steps), candidates[-1])


def _write_progress(
    scan_job_id: int,
    *,
    phase: str,
    done: int,
    total: int,
    phase_started_at: str,
    step: str = "",
    steps: list[str] | None = None,
    step_done: int | None = None,
    step_total: int | None = None,
    detail: str = "",
) -> None:
    """寫 ScanJob.progress；用 filter().update() 避免覆蓋其他欄位且 race-safe。

    step_done／step_total 是「目前這一步」自己的進度（例如 GEO 分析到第幾頁），前端用它和
    steps 一起算整體進度，讓進度條與階段一致；無法計數的步驟給 0／0（前端顯示進行中）。
    未指定時，爬取與 Agent 這類一步就是一整個 phase 的步驟沿用 done／total。
    """
    progress = {
        "pages_done": done,
        "pages_total": max(total, 1),  # 避免除以 0
        "phase": phase,
        "phase_started_at": phase_started_at,
    }
    if step:
        if step_done is None:
            step_done, step_total = (done, total) if step in ("crawl", "agent") else (0, 0)
        progress["step"] = step
        progress["step_done"] = max(step_done, 0)
        progress["step_total"] = max(step_total or 0, 0)
        # 同一步驟沿用第一次寫入的開始時間（前端據此估算本步驟剩餘時間）
        previous = (
            ScanJob.objects.filter(id=scan_job_id).values_list("progress", flat=True).first()
        )
        same_step = isinstance(previous, dict) and previous.get("step") == step
        if same_step and previous.get("step_started_at"):
            progress["step_started_at"] = previous["step_started_at"]
        else:
            progress["step_started_at"] = timezone.now().isoformat()
    if steps:
        progress["steps"] = steps
    if detail:
        progress["step_detail"] = detail  # 前端在 agent 階段顯示「目前在跑哪個專家」
    ScanJob.objects.filter(id=scan_job_id).update(progress=progress)


@transaction.atomic
def fail_scan_job_before_start(scan_job_id: int) -> bool:
    """排程尚未交給 worker 就失敗時，結束任務並退回預扣 coin。"""
    now = timezone.now()
    updated = ScanJob.objects.filter(
        id=scan_job_id,
        status=ScanJob.Status.QUEUED,
    ).update(
        status=ScanJob.Status.FAILED,
        completed_at=now,
        progress={},
        error_message="掃描任務排程失敗。",
        updated_at=now,
    )
    if not updated:
        return False

    scan_job = ScanJob.objects.select_related("user").get(id=scan_job_id)
    append_log(scan_job_id, "掃描任務排程失敗", level="error")
    refund_full_for_scan(scan_job.user, scan_job, reason="排程失敗")
    return True


@transaction.atomic
def reconcile_local_scan_process_exit(scan_job_id: int) -> bool:
    """本機子程序異常退出時，收斂所有非終態工作並冪等退款。"""
    now = timezone.now()
    updated = ScanJob.objects.filter(
        id=scan_job_id,
        status__in=[
            ScanJob.Status.QUEUED,
            ScanJob.Status.CRAWLING,
            ScanJob.Status.SCANNING,
            ScanJob.Status.AGENT_TESTING,
        ],
    ).update(
        status=ScanJob.Status.FAILED,
        completed_at=now,
        progress={},
        error_message="本機掃描程序異常結束。",
        updated_at=now,
    )
    if not updated:
        return False

    scan_job = ScanJob.objects.select_related("user").get(id=scan_job_id)
    append_log(scan_job_id, "本機掃描程序異常結束", level="error")
    refund_full_for_scan(scan_job.user, scan_job, reason="本機程序異常")
    return True


IN_PROGRESS_STATUSES = (
    ScanJob.Status.QUEUED,
    ScanJob.Status.CRAWLING,
    ScanJob.Status.SCANNING,
    ScanJob.Status.AGENT_TESTING,
)


def request_scan_cancel(scan_job: ScanJob) -> bool:
    """使用者主動終止掃描（網頁 API 與 MCP 共用）。

    合作式 cancel：只把狀態設為 cancelled，worker 在下一個檢查點停下；同時立即退回
    預扣的 coin（worker 端也會再退一次，refund_full_for_scan 冪等）。
    已結束（完成／失敗／已取消）的掃描回傳 False，不做任何事。
    """
    if scan_job.status not in IN_PROGRESS_STATUSES:
        return False
    scan_job.status = ScanJob.Status.CANCELLED
    scan_job.save(update_fields=["status", "updated_at"])
    refund_full_for_scan(scan_job.user, scan_job, reason="取消")
    return True


def reap_stale_scans() -> int:
    """把「worker 已經不在了」的掃描收斂成 failed 並冪等退款，回傳處理筆數。

    為什麼需要這支：worker pod 被 rollout／OOM／節點驅逐砍掉時，run_scan_job 的
    三個 except（ScanCancelled／SoftTimeLimitExceeded／一般例外）都跑不到——那些
    handler 需要 Python 還活著。被 SIGKILL 時什麼都不會執行，於是 ScanJob 永遠停在
    crawling／scanning，hold_for_scan 扣的 coin 永遠不退。

    也不能靠 Celery 的 acks_late 重投解決：run_scan_job 入口的 CAS 是
    filter(status=QUEUED).update(...)，重投時狀態已是 crawling，只會直接 return。
    冪等保護反而讓重試變成空轉，所以必須有外部回收。

    判斷依據是「開始多久了」而不是「有沒有心跳」：超過硬性 time limit 還在非終態，
    代表連 Celery 的 hard limit 都沒能把它殺掉，任務必然已經不在了。用 started_at，
    沒有 started_at（從未被取件）則退回 created_at。
    """
    cutoff = timezone.now() - timedelta(seconds=settings.CELERY_TASK_TIME_LIMIT)
    stale = ScanJob.objects.filter(
        status__in=[
            ScanJob.Status.QUEUED,
            ScanJob.Status.CRAWLING,
            ScanJob.Status.SCANNING,
            ScanJob.Status.AGENT_TESTING,
        ],
    ).filter(
        Q(started_at__lt=cutoff) | Q(started_at__isnull=True, created_at__lt=cutoff)
    )

    reaped = 0
    for scan_job_id in list(stale.values_list("id", flat=True)):
        # 一筆失敗不能讓其餘卡住的掃描繼續卡著——這是批次維護作業。
        try:
            if _fail_and_refund_stale_scan(scan_job_id):
                reaped += 1
        except Exception:  # noqa: BLE001
            logger.exception("回收卡住的掃描失敗 scan_job_id=%s", scan_job_id)
    return reaped


@transaction.atomic
def _fail_and_refund_stale_scan(scan_job_id: int) -> bool:
    """單筆收斂。用 CAS 更新，萬一與還活著的 worker 撞上，只有一邊會贏。"""
    now = timezone.now()
    updated = ScanJob.objects.filter(
        id=scan_job_id,
        status__in=[
            ScanJob.Status.QUEUED,
            ScanJob.Status.CRAWLING,
            ScanJob.Status.SCANNING,
            ScanJob.Status.AGENT_TESTING,
        ],
    ).update(
        status=ScanJob.Status.FAILED,
        completed_at=now,
        progress={},
        error_message="掃描執行期間中斷（可能因伺服器重啟或資源不足），已自動退回預扣點數。",
        updated_at=now,
    )
    if not updated:
        return False

    scan_job = ScanJob.objects.select_related("user").get(id=scan_job_id)
    append_log(scan_job_id, "掃描執行期間中斷，已自動回收並退款", level="error")
    # refund_full_for_scan 本身冪等（淨扣為 0 時回 None），重跑不會重複退款。
    refund_full_for_scan(scan_job.user, scan_job, reason="執行中斷")
    logger.warning("回收卡住的掃描 scan_job_id=%s", scan_job_id)
    return True


# ---------------------------------------------------------------------------
# 掃描流程（run_scan_job）＝ 依序執行的階段函式
#
# 每個階段一個函式、只做一件事，階段之間的中間產物放在 ScanRunContext。
# run_scan_job 只負責：啟動（CAS 取件）→ 依 SCAN_PIPELINE 逐段執行 → 三種終止收尾
# （取消／超時／失敗），階段失敗時 log 會標出是哪一段（[階段名:例外類別]）。
#
# 狀態推進仍然全部集中在本檔（scans/CLAUDE.md 的狀態機規則）；各階段函式可以單獨
# 測試與重用。新增階段時：寫一支 stage_xxx(ctx)、加進 SCAN_PIPELINE，若要在進度條
# 顯示，同步 planned_scan_steps() 與前端 SCAN_STEP_META。
# ---------------------------------------------------------------------------


class ScanTargetUnreachable(Exception):
    """爬取結束卻沒有任何可分析的頁面：不能標成「完成」並給出看似正常的分數。

    訊息會直接顯示給使用者（不含內部細節）。
    """


def _ensure_usable_pages(crawled_pages: list[dict], warnings: dict) -> None:
    """至少要有一頁正常回應（2xx／3xx 且未被阻擋），否則整次掃描視為失敗並全額退款。

    2026-10-06 實測：瀏覽器無法連線時爬到 0 頁，掃描仍標「完成」並給 73 分（只剩 DNS／SSL
    等站台層級檢查），使用者會誤以為網站很健康。
    """
    usable = [
        page for page in crawled_pages
        if page.get("status_code") and page["status_code"] < 400 and not page.get("blocked_reason")
    ]
    if usable:
        return
    if crawled_pages:
        raise ScanTargetUnreachable(
            "沒有取得任何可分析的頁面：網站回應錯誤或擋下了掃描（可能是 WAF、CDN 防護或登入限制）。"
            "本次不收費，請確認網址可公開瀏覽後再試。"
        )
    failed = len((warnings or {}).get("failed_urls") or [])
    raise ScanTargetUnreachable(
        "無法連線到網站，沒有取得任何頁面"
        + (f"（{failed} 個網址連線失敗）" if failed else "")
        + "。本次不收費，請確認網址可公開瀏覽後再試。"
    )


@dataclass
class ScanRunContext:
    """一次掃描執行期間，各階段共用的狀態與中間產物。"""

    scan_job: ScanJob
    execution_plan: ScanExecutionPlan
    steps: list[str]
    crawl_phase_started: str
    # 任務起始的 monotonic 時間（計算各階段還剩多少預算用；0＝未記錄，視為剛開始）
    started_monotonic: float = 0.0
    # 爬取階段
    crawled_pages: list[dict] = field(default_factory=list)
    warnings: dict = field(default_factory=dict)
    site_signals: dict = field(default_factory=dict)
    discovered_endpoints: list = field(default_factory=list)
    # 分析階段
    pages: list[tuple[Page, dict]] = field(default_factory=list)
    all_findings: list[dict] = field(default_factory=list)
    scan_phase_started: str = ""
    scanning_total: int = 0
    # 主動探測階段
    page_urls: list[str] = field(default_factory=list)
    endpoint_urls: list[str] = field(default_factory=list)
    katana_findings: list[dict] = field(default_factory=list)
    katana_tech: list[str] = field(default_factory=list)
    nuclei_findings: list[dict] = field(default_factory=list)
    # 這次 Nuclei 用的引擎、模板版本與模板集指紋（nuclei_scanner.template_set_info）
    nuclei_template_set: dict = field(default_factory=dict)
    # AEO 可回答性檢測（aeo/evaluate.py 的 AeoEvaluation）
    aeo_evaluation: object | None = None
    # PageSpeed Insights 背景量測（stage_pagespeed_start 送出，stage_pagespeed 取結果）
    pagespeed_future: object | None = None
    # Agent 階段
    agent_meta: dict = field(default_factory=dict)
    agent_result: object | None = None
    # 目前執行到哪一段（失敗時寫進 log）
    runtime_stage: str = "target_validation"
    # 覆蓋紀錄（coverage.py）：各項檢查是否完整跑完、產生了哪些問題
    coverage: ScanCoverage = field(default_factory=ScanCoverage)
    # ZAP 主動掃描用的 HAR 暫存目錄（爬取時錄、stage_zap_active 用完即刪；被動已退役）
    har_dir: Path | None = None

    @property
    def scan_job_id(self) -> int:
        return self.scan_job.id

    @property
    def deep_scan_total(self) -> int:
        """分析之後的資安補充階段用延伸的 done/total，讓進度條持續往前走。"""
        return self.scanning_total + 4

    def record(
        self, findings: list[dict], *, page: Page | None = None, check: str | None = None
    ) -> None:
        """寫入 Finding 並納入計分清單；check＝產生這批 finding 的檢查（覆蓋紀錄用）。"""
        for finding in findings:
            Finding.objects.create(scan_job=self.scan_job, page=page, **finding)
        self.all_findings.extend(findings)
        if check:
            self.coverage.add_findings(check, findings)

    def scanning_progress(self, done: int, step: str) -> None:
        """分析之後各資安補充步驟的進度（phase 固定 scanning）。"""
        _write_progress(
            self.scan_job_id,
            phase="scanning",
            done=done,
            total=self.deep_scan_total,
            phase_started_at=self.scan_phase_started,
            step=step,
            steps=self.steps,
        )


def start_scan_run(scan_job_id: int) -> ScanRunContext | dict:
    """CAS 取件（queued → crawling）並建立執行 context。

    已被別的 worker 取走或已結束時回傳 {"status": 目前狀態}，呼叫端直接結束。
    """
    now = timezone.now()
    crawl_phase_started = now.isoformat()
    initial_progress = {
        "pages_done": 0,
        "pages_total": 1,
        "phase": "crawling",
        "phase_started_at": crawl_phase_started,
    }
    started = ScanJob.objects.filter(
        id=scan_job_id,
        status=ScanJob.Status.QUEUED,
    ).update(
        status=ScanJob.Status.CRAWLING,
        started_at=now,
        scan_log=[],
        progress=initial_progress,
        updated_at=now,
    )
    if not started:
        current_status = ScanJob.objects.values_list("status", flat=True).get(id=scan_job_id)
        return {"status": current_status}
    scan_job = ScanJob.objects.select_related("user").get(id=scan_job_id)
    execution_plan = build_scan_execution_plan(scan_job)
    ctx = ScanRunContext(
        scan_job=scan_job,
        execution_plan=execution_plan,
        steps=planned_scan_steps(scan_job, execution_plan),
        crawl_phase_started=crawl_phase_started,
        started_monotonic=time.monotonic(),
    )
    _write_progress(
        scan_job_id, phase="crawling", done=0, total=1,
        phase_started_at=crawl_phase_started, step="crawl", steps=ctx.steps,
    )
    scope_label = "單頁" if execution_plan.scope == "single" else "全網站"
    append_log(
        scan_job_id,
        "掃描任務啟動 — 目標："
        f"{redact_pii_in_text(redact_url_query_values(scan_job.normalized_url))}，"
        f"範圍：{scope_label}，模式：{scan_job.scan_mode}",
    )
    return ctx


def stage_validate_target(ctx: ScanRunContext) -> None:
    """再次確認目標是公開 HTTP(S) 網址（建立時已檢查；排隊期間 DNS 可能改變）。"""
    assert_public_http_url(ctx.scan_job.normalized_url)


def stage_crawl(ctx: ScanRunContext) -> None:
    """Playwright BFS 爬取；每頁回報進度並當作取消檢查點。"""
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id

    # crawler callback：在 async loop 內透過 sync_to_async 寫 DB；
    # 同時是合作式 cancel 的檢查點，若已被使用者終止就 raise ScanCancelled
    async def _crawl_progress(done: int, total: int) -> None:
        await sync_to_async(_write_progress, thread_sensitive=True)(
            scan_job_id, phase="crawling", done=done, total=total,
            phase_started_at=ctx.crawl_phase_started, step="crawl", steps=ctx.steps,
        )
        cancelled = await sync_to_async(is_cancelled, thread_sensitive=True)(scan_job_id)
        if cancelled:
            raise ScanCancelled()

    append_log(
        scan_job_id,
        f"開始爬取，最大深度 {scan_job.max_depth}，最大頁數 {scan_job.max_pages}",
    )
    if _runs_zap_active(scan_job):
        ctx.har_dir = Path(tempfile.mkdtemp(prefix=f"argus-har-{scan_job_id}-"))
    crawled_pages, warnings, site_signals, discovered_endpoints = _run_async(
        lambda: crawl_site(
            start_url=scan_job.normalized_url,
            origin=scan_job.origin,
            scan_job_id=scan_job.id,
            scan_mode=scan_job.scan_mode,
            max_depth=scan_job.max_depth,
            max_pages=scan_job.max_pages,
            respect_robots=scan_job.respect_robots,
            progress_callback=_crawl_progress,
            run_accessibility=_runs_accessibility(scan_job),
            har_dir=ctx.har_dir,
        )
    )
    ctx.crawled_pages = crawled_pages
    ctx.warnings = redact_warning_summary(warnings)
    ctx.site_signals = site_signals
    ctx.discovered_endpoints = discovered_endpoints
    if site_signals.get("sitemap_seeded"):
        append_log(
            scan_job_id,
            f"sitemap 提供 {site_signals['sitemap_seeded']} 個頁面網址，已加入爬取佇列",
        )
    append_log(scan_job_id, f"爬取完成，共 {len(crawled_pages)} 頁")
    budget = ctx.warnings.get("crawl_budget")
    if budget:
        append_log(ctx.scan_job_id, crawl_budget_text(budget))
    _ensure_usable_pages(crawled_pages, warnings)
    # robots／範圍限制略過的頁面是使用者設定，不算不完整；擷取失敗才是
    failed = warnings.get("failed_urls") or []
    # 內容在上限內沒穩定的頁面照樣分析，只在說明註記（LIMITED），不改覆蓋狀態：
    # 輪播或持續更新的頁面不該讓整次掃描變成部分評估
    not_ready = ((budget or {}).get("render_readiness") or {}).get("timeout", 0)
    notes = [f"{len(failed)} 個頁面擷取失敗"] if failed else []
    if not_ready:
        notes.append(f"{not_ready} 個頁面在等待上限內內容未穩定（render_readiness_timeout）")
    ctx.coverage.mark("crawl", PARTIAL if failed else COMPLETED, "；".join(notes))
    _mark_axe_coverage(ctx)
    if discovered_endpoints:
        append_log(
            scan_job_id,
            f"爬取期間觀察到 {len(discovered_endpoints)} 個 same-origin API 端點"
            "（XHR/fetch 被動攔截，供主動工具作為攻擊面輸入）",
        )


def _runs_zap_active(scan_job: ScanJob) -> bool:
    """ZAP 主動掃描：勾資安＋已開啟主動 ZAP＋全站主動已授權才跑（會送攻擊 payload）。"""
    if "security" not in scan_job.effective_categories or not zap_active_enabled():
        return False
    return build_scan_execution_plan(scan_job).run_zap_active


def _zap_active_skip_reason(scan_job: ScanJob) -> str | None:
    """沒跑主動掃描時的原因（覆蓋說明用）；回 None 代表這次本來就與主動掃描無關、不標。

    主動沒跑時原本完全不留痕跡，判讀報告的人分不清是「旗標沒開」「沒授權」還是「跑了沒發現」
    （某授權掃描實測：覆蓋只見 zap_passive，看不出主動為何缺席）。只有勾了資安才標。
    """
    if "security" not in scan_job.effective_categories:
        return None
    if not build_scan_execution_plan(scan_job).run_zap_active:
        return "僅「全站＋主動模式＋網域已驗證」的掃描會執行主動掃描"
    if not zap_enabled():
        return "平台未部署或未啟用 ZAP"
    if not zap_active_enabled():
        return "平台未開啟 ZAP 主動掃描（ARGUS_ZAP_ACTIVE_ENABLED）"
    return None


def _discard_har(ctx: ScanRunContext) -> None:
    """HAR 含頁面內容與 Cookie 屬性，用完或掃描中止都要刪掉。"""
    if ctx.har_dir is not None:
        shutil.rmtree(ctx.har_dir, ignore_errors=True)
        ctx.har_dir = None


def _runs_accessibility(scan_job: ScanJob) -> bool:
    """axe-core 只在勾了 UX 時跑（每頁約 1 秒，沒勾就不花這個時間）。"""
    return bool(settings.ARGUS_AXE_ENABLED) and "ux" in scan_job.effective_categories


def _mark_axe_coverage(ctx: ScanRunContext) -> None:
    """axe-core 檢查了幾頁：全部可分析頁面都跑完＝completed，部分＝partial，全失敗＝failed。"""
    if "ux" not in ctx.scan_job.effective_categories:
        return
    if not settings.ARGUS_AXE_ENABLED:
        ctx.coverage.mark("axe", SKIPPED, "已停用")
        return
    usable = [p for p in ctx.crawled_pages if not p.get("blocked_reason")]
    audited = [p for p in usable if (p.get("a11y") or {}).get("violations") is not None]
    if not usable:
        return
    version = next((p["a11y"].get("version") for p in audited if p["a11y"].get("version")), "")
    if version:
        ctx.warnings.setdefault("tools", {})["axe-core"] = version
    if len(audited) == len(usable):
        ctx.coverage.mark("axe", COMPLETED)
    elif not audited:
        ctx.coverage.mark("axe", FAILED, "每一頁都檢查失敗")
    else:
        ctx.coverage.mark(
            "axe", PARTIAL,
            f"{len(usable) - len(audited)} 頁未檢查（逾時、失敗或超過頁數上限）",
        )


def _persist_pages(ctx: ScanRunContext) -> None:
    """把爬到的頁面寫成 Page 紀錄，保留原始 page_data 供後續分析使用。"""
    for page_data in ctx.crawled_pages:
        page = Page.objects.create(
            scan_job=ctx.scan_job,
            url=page_data["url"],
            final_url=page_data["final_url"],
            origin=page_data["origin"],
            status_code=page_data["status_code"],
            title=page_data["title"],
            html=page_data["html"],
            rendered_dom=page_data["rendered_dom"],
            html_only_text=page_data["html_only"],
            screenshot_path=page_data["screenshot_path"],
            load_time_ms=page_data["load_time_ms"],
            depth=page_data["depth"],
            blocked_reason=page_data["blocked_reason"],
            outgoing_links=page_data["outgoing_links"],
            headers=page_data["headers"],
            element_boxes=page_data["element_boxes"],
            layout_metrics=page_data.get("layout_metrics") or {},
        )
        ctx.pages.append((page, page_data))


def _analyze_categories(ctx: ScanRunContext) -> list[str]:
    return [c for c in ANALYZE_STEP_ORDER if c in ctx.scan_job.effective_categories]


_STOP_REASONS = {
    "max_pages": "達到頁數上限",
    "queue_exhausted": "沒有更多可爬的同網站頁面",
    "browser_failed": "瀏覽器異常中止",
}


def crawl_budget_text(budget: dict) -> str:
    """爬取預算的一行說明（roadmap「爬取」第 2 項）：為什麼停、頁面從哪來、略過多少、花在哪。"""
    seeds = budget.get("seeds") or {}
    parts = [
        f"爬取結束：{_STOP_REASONS.get(budget.get('stop_reason'), budget.get('stop_reason'))}"
        f"（{budget.get('pages', 0)}／{budget.get('max_pages')} 頁，"
        f"耗時 {round((budget.get('elapsed_ms') or 0) / 1000)} 秒）",
        f"來源：起始網址 {seeds.get('start', 0)}、sitemap {seeds.get('sitemap', 0)}、"
        f"頁面連結 {budget.get('links_queued', 0)}",
    ]
    skipped = [
        f"{label} {budget[key]}"
        for key, label in (
            ("links_dropped_limit", "超過頁數上限未排入"),
            ("skipped_depth", "超過深度"),
            ("skipped_robots", "robots.txt 禁止"),
            ("failed", "擷取失敗"),
        )
        if budget.get(key)
    ]
    if skipped:
        parts.append("略過：" + "、".join(skipped))
    if budget.get("throttle_waits"):
        waited = round(budget["throttle_wait_ms"] / 1000)
        parts.append(f"速率限制等待 {budget['throttle_waits']} 次共 {waited} 秒")
    if budget.get("page_ms_avg") is not None:
        parts.append(f"每頁平均 {round(budget['page_ms_avg'] / 1000, 1)} 秒")
    ready = budget.get("render_readiness")
    if ready:
        text = f"等內容穩定平均 {round(ready['avg_ms'] / 1000, 1)} 秒"
        if ready.get("timeout"):
            text += f"，{ready['timeout']} 頁在上限內未穩定（照樣擷取，內容可能不完整）"
        parts.append(text)
    return "；".join(parts)


def stage_enter_scanning(ctx: ScanRunContext) -> None:
    """爬取 → 分析的狀態轉換：記錄警告、推進到 scanning、落地頁面。"""
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    if ctx.warnings:
        for k, v in ctx.warnings.items():
            # 爬取預算是摘要不是警告，已在 stage_crawl 以一行說明記錄
            if k in ("crawl_budget", "tools"):
                continue
            append_log(scan_job_id, f"爬取警告 [{k}]: {v}", level="warn")
    # 進入 scanning 前再檢查一次：避免使用者剛 cancel 就被 worker 覆蓋回 SCANNING
    raise_if_cancelled(scan_job_id)
    ctx.scan_phase_started = timezone.now().isoformat()
    analyze_cats = _analyze_categories(ctx)
    page_count = max(len(ctx.crawled_pages), 1)
    ctx.scanning_total = page_count * max(len(analyze_cats), 1)
    scan_job.status = ScanJob.Status.SCANNING
    scan_job.warning_summary = ctx.warnings
    scan_job.progress = {
        "pages_done": 0,
        "pages_total": ctx.scanning_total,
        "phase": "scanning",
        "phase_started_at": ctx.scan_phase_started,
        "step": f"analyze_{analyze_cats[0]}" if analyze_cats else "deep_security",
        "step_done": 0,
        "step_total": page_count if analyze_cats else 0,
        "step_started_at": ctx.scan_phase_started,
        "steps": ctx.steps,
    }
    scan_job.save(update_fields=["status", "warning_summary", "progress", "updated_at"])
    append_log(scan_job_id, f"開始分析，共 {len(ctx.crawled_pages)} 頁待掃描")
    _persist_pages(ctx)


def stage_fingerprint(ctx: ScanRunContext) -> None:
    """網站特徵（Smart Scan 階段 1）：只用爬取已有的訊號，不發請求、不改任何掃描決策。

    失敗只記 log，不影響掃描；結果寫 ScanJob.fingerprint，供之後的準確率評估與動態加掃使用。
    """
    scan_job = ctx.scan_job
    failed = (ctx.warnings or {}).get("failed_urls") or []
    crawl_complete = not failed and len(ctx.crawled_pages) < scan_job.max_pages
    try:
        snapshot = fingerprint_snapshot(
            ctx.crawled_pages, ctx.discovered_endpoints, crawl_complete=crawl_complete
        )
    except Exception as exc:
        logger.exception("網站特徵整理失敗 scan_job_id=%s", ctx.scan_job_id)
        append_log(ctx.scan_job_id, f"網站特徵整理失敗（{exc.__class__.__name__}）", level="warn")
        snapshot = {"version": 1, "phase": "pre_scan", "error": exc.__class__.__name__}
    scan_job.fingerprint = snapshot
    scan_job.save(update_fields=["fingerprint", "updated_at"])
    if "error" not in snapshot:
        found = [
            label for label, value in (
                ("CMS " + (snapshot["cms"] or ""), snapshot["cms"]),
                ("登入頁", snapshot["has_login"]),
                ("API", snapshot["has_api"]),
                ("上傳欄位", snapshot["has_upload"]),
                ("邊緣服務 " + (snapshot["edge"] or ""), snapshot["edge"]),
            ) if value
        ]
        append_log(
            ctx.scan_job_id,
            "網站特徵（只記錄，不影響本次掃描）："
            + ("、".join(found) if found else "沒有明顯特徵"),
        )


def _analyze_one_page(page: Page, page_data: dict, category: str) -> list[dict]:
    """對單一頁面跑單一維度的規則分析（資安維度另含 inline 秘鑰偵測）。"""
    page_findings = analyze_page(
        PageAnalysisInput(
            url=page.url,
            final_url=page.final_url,
            title=page.title,
            html=page.html,
            headers=page_data["headers"],
            element_boxes=page_data["element_boxes"],
            html_only=page_data["html_only"],
            layout_metrics=page_data.get("layout_metrics") or {},
            ux_signals=page_data.get("ux_signals") or {},
            js_errors=page_data.get("js_errors") or [],
            a11y=page_data.get("a11y") or {},
        ),
        categories={category},
    )
    # Inline/HTML 硬編碼秘鑰偵測＋AI 提示詞注入＋密碼欄位未遮蔽（被動：只解析已抓到的 HTML）
    if category == "security":
        secrets = detect_secrets_in_text(page.html)
        location = page.final_url or page.url
        injection = build_injection_finding(detect_content_injection(page.html), location)
        for secret_finding in (
            build_secret_finding(secrets, location, source="inline_html"),
            build_browser_key_finding(secrets, location, source="inline_html"),
            injection,
        ):
            if secret_finding:
                page_findings.append(owasp_mapper.tag(secret_finding))
        page_findings.extend(
            owasp_mapper.tag(f) for f in analyze_password_fields(page.html, location)
        )
    return page_findings


def stage_analyze_pages(ctx: ScanRunContext) -> None:
    """逐維度、逐頁分析。

    一次只跑一個維度，進度才能告訴使用者「現在在分析 GEO／UX／資安」；
    結果與一次跑全部維度相同（analyze_page 各維度互不相依）。
    """
    scan_job_id = ctx.scan_job_id
    page_count = max(len(ctx.crawled_pages), 1)
    page_finding_counts = [0] * len(ctx.pages)
    for cat_idx, category in enumerate(_analyze_categories(ctx)):
        category_found = 0
        for page_idx, (page, page_data) in enumerate(ctx.pages):
            # 被阻擋的頁面內容是錯誤頁，不進行分析，僅保留紀錄與警告
            if not page_data["blocked_reason"]:
                page_findings = _analyze_one_page(page, page_data, category)
                ctx.record(page_findings, page=page, check=f"page_{category}")
                if category == "ux":
                    # axe-core 的 finding 另外歸到 axe 檢查，歷史比較才能對回它
                    ctx.coverage.add_findings(
                        "axe", [f for f in page_findings if f["rule_id"].startswith("axe-")]
                    )
                page_finding_counts[page_idx] += len(page_findings)
                category_found += len(page_findings)
            # 每處理一頁就更新 progress；同時當作 cancel 檢查點
            _write_progress(
                scan_job_id,
                phase="scanning",
                done=cat_idx * page_count + page_idx + 1,
                total=ctx.scanning_total,
                phase_started_at=ctx.scan_phase_started,
                step=f"analyze_{category}",
                steps=ctx.steps,
                step_done=page_idx + 1,
                step_total=page_count,
            )
            raise_if_cancelled(scan_job_id)
        ctx.coverage.mark(f"page_{category}", COMPLETED)
        append_log(
            scan_job_id,
            f"{CATEGORY_LOG_LABELS[category]} 分析完成：{category_found} 項問題",
        )

    for page_idx, (_page, page_data) in enumerate(ctx.pages, start=1):
        found = page_finding_counts[page_idx - 1]
        blocked = (
            f"（阻擋：{page_data['blocked_reason']}）"
            if page_data["blocked_reason"]
            else ""
        )
        append_log(
            scan_job_id,
            f"[{page_idx}/{len(ctx.pages)}] "
            f"{redact_pii_in_text(redact_url_query_values(page_data['url']))} "
            f"HTTP {page_data['status_code']} {blocked}→ {found} 項問題",
        )


def _aeo_site_pages(ctx: ScanRunContext) -> list[SitePage]:
    return [
        SitePage(
            url=page.final_url or page.url,
            html=page_data.get("html") or "",
            raw_html=page_data.get("html_only") or "",
            blocked=bool(page_data.get("blocked_reason")),
            headers=page_data.get("headers") or {},
        )
        for page, page_data in ctx.pages
    ]


def stage_aeo_answerability(ctx: ScanRunContext) -> None:
    """AEO 可回答性檢測（站台層級）：網站內容能否回答一組具體問題，逐題附原文證據。

    內容不足以出題時標記為未充分評估（AEO 不評分），而不是給 100 分。
    """
    scan_job = ctx.scan_job
    if "aeo" not in scan_job.effective_categories:
        return
    ctx.scanning_progress(ctx.scanning_total, "aeo_answers")
    evaluation = evaluate_site(_aeo_site_pages(ctx))
    ctx.aeo_evaluation = evaluation
    ctx.record(evaluation.findings, check="aeo_answers")
    ctx.coverage.mark(
        "aeo_answers",
        COMPLETED if evaluation.status == "evaluated" else PARTIAL,
        "" if evaluation.status == "evaluated" else (evaluation.reason or "內容不足"),
    )
    scan_job.aeo_report = evaluation.summary
    scan_job.save(update_fields=["aeo_report", "updated_at"])
    if evaluation.status == "evaluated":
        summary = evaluation.summary
        counts = summary["counts"]
        append_log(
            ctx.scan_job_id,
            f"AEO 問答檢測：{summary['questions_total']} 題，可回答 {counts['answered']}、"
            f"資訊不足 {counts['insufficient']}、衝突 {counts['conflict']}、"
            f"無答案 {counts['missing']}（可回答性 {evaluation.score} 分）",
        )
    else:
        append_log(ctx.scan_job_id, f"AEO 問答檢測未充分評估：{evaluation.reason}", level="warn")


def stage_site_security(ctx: ScanRunContext) -> None:
    """站台層級安全檢查（HTTPS/HSTS/CSP/X-Frame-Options/X-Content-Type-Options）。

    這些是伺服器設定、整站幾乎一致；逐頁評估只會得到同一組問題的多份複本，
    並依頁數不成比例拖低資安分數，所以對整批頁面只評估一次（page=None）。
    未勾「資安」維度時整段跳過。
    """
    if "security" not in ctx.scan_job.effective_categories:
        return
    findings = analyze_security_site_level(ctx.crawled_pages)
    ctx.record(findings, check="site_security")
    ctx.coverage.mark("site_security", COMPLETED)
    if findings:
        append_log(
            ctx.scan_job_id,
            f"站台層級安全檢查（HTTPS/HSTS/CSP 等）：{len(findings)} 項發現",
        )


def _collect_probe_targets(ctx: ScanRunContext) -> None:
    """整理 sqlmap 候選：已爬頁面（排除被擋）＋爬取期間被動攔截的 same-origin 端點。

    Nuclei 只掃網站根網址（模板多半檢查網站層級路徑），不用這份清單。
    """
    ctx.page_urls = [
        assert_public_http_url(p["url"])
        for p in ctx.crawled_pages
        if not p.get("blocked_reason")
    ]
    ctx.endpoint_urls = []
    for endpoint in ctx.discovered_endpoints:
        try:
            normalized_endpoint = assert_public_http_url(endpoint)
        except ValueError:
            continue
        if normalized_endpoint in ctx.page_urls or normalized_endpoint in ctx.endpoint_urls:
            continue
        ctx.endpoint_urls.append(normalized_endpoint)


def _tool_failed(ctx: ScanRunContext, check: str, tool: str, exc: Exception) -> None:
    """外部工具失敗：記 log 並標記覆蓋紀錄（工具失敗不能被呈現成「0 項問題」）。"""
    logger.exception("掃描子步驟失敗 scan_job_id=%s", ctx.scan_job_id)
    append_log(ctx.scan_job_id, f"{tool} 略過（{exc.__class__.__name__}）", level="warn")
    # 原因只寫固定代碼，不寫例外訊息（可能含網址或工具輸出）
    reason = str(exc) if isinstance(exc, NucleiUnavailable) else exc.__class__.__name__
    ctx.coverage.mark(check, FAILED, reason)


def _apply_nuclei_run(ctx: ScanRunContext, run) -> None:
    """Nuclei 結果：逾時的結果只是部分完成，不能當成「完整跑完、沒有問題」。"""
    ctx.nuclei_findings = run.findings
    ctx.nuclei_template_set = run.template_set
    if run.timed_out:
        used = run.timeout_seconds or settings.ARGUS_NUCLEI_TIMEOUT
        ctx.coverage.mark(
            "nuclei", PARTIAL,
            f"逾時（{used} 秒），只有逾時前完成的模板有結果",
        )
    else:
        ctx.coverage.mark("nuclei", COMPLETED)


# Nuclei 之後各階段（深度資安、敏感路徑、SEO 連結、PageSpeed、評分與結算）的時間保留量；
# Agent 會跑時另加（ARGUS_AGENT_MAX_STEPS 步的 LLM 呼叫與工具執行，最壞可達十餘分鐘）。
_POST_NUCLEI_RESERVE_SECONDS = 600
_AGENT_RESERVE_SECONDS = 900
# 剩餘預算低於此值就不跑 Nuclei：短時間內跑不完幾個模板，還壓縮後續階段、
# 增加 Celery soft limit 溢出（整個掃描失敗＋退款）的風險。
_NUCLEI_MIN_RUN_SECONDS = 120


def _nuclei_timeout_seconds(ctx: ScanRunContext) -> int:
    """Nuclei 這次可用的逾時上限（秒）。

    固定 660 秒對「全網站掃描與 Katana 分預算後只剩 1 RPS」的大型／回應慢網站不夠用
    （KEV 模板集約 630 個請求，速率限制本身就要 630 秒起跳）。這裡在整體掃描時限
    （Celery soft limit 扣除後續階段保留時間）允許的範圍內，把上限從
    ARGUS_NUCLEI_TIMEOUT 放寬到 ARGUS_NUCLEI_MAX_TIMEOUT；預算不足時縮短到剩餘值。
    """
    elapsed = time.monotonic() - ctx.started_monotonic if ctx.started_monotonic else 0.0
    reserve = _POST_NUCLEI_RESERVE_SECONDS
    plan = ctx.execution_plan
    if settings.ARGUS_AGENT_ENABLED and (plan.run_agent or plan.run_agent_ux):
        reserve += _AGENT_RESERVE_SECONDS
    remaining = max(settings.CELERY_TASK_SOFT_TIME_LIMIT - elapsed - reserve, 0)
    extended = min(settings.ARGUS_NUCLEI_MAX_TIMEOUT, remaining)
    return int(min(max(settings.ARGUS_NUCLEI_TIMEOUT, extended), remaining))


def _run_nuclei_for_scan(ctx: ScanRunContext, target: str, rate_limit: int) -> None:
    """依整體掃描剩餘預算執行 Nuclei 並套用結果（例外由呼叫端處理）。

    剩餘時間連最低執行量都不夠時直接不跑：覆蓋紀錄標 time_budget_exhausted，
    比把整個任務推向 Celery soft limit（掃描失敗＋退款）好。
    """
    timeout = _nuclei_timeout_seconds(ctx)
    if timeout < _NUCLEI_MIN_RUN_SECONDS:
        append_log(
            ctx.scan_job_id,
            f"Nuclei 略過：掃描已接近整體時限（只剩 {timeout} 秒），優先保留時間給後續分析",
            level="warn",
        )
        ctx.coverage.mark("nuclei", FAILED, "time_budget_exhausted")
        return
    _apply_nuclei_run(
        ctx, run_nuclei(target, ctx.scan_job_id, rate_limit=rate_limit, timeout=timeout)
    )


def _run_site_active_tools(
    ctx: ScanRunContext, target: str, skip_nuclei: bool = False
) -> None:
    """全網站主動掃描：Katana 與 Nuclei 共享 ARGUS_ACTIVE_MAX_RPS 預算。

    `skip_nuclei`（目標位於全代理 CDN 後）時只跑 Katana，並讓它獨佔整個 RPS 預算；
    Nuclei 的覆蓋紀錄與說明由呼叫端 `stage_active_probe` 處理。
    """
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    active_rps = max(int(settings.ARGUS_ACTIVE_MAX_RPS), 1)

    if skip_nuclei:
        append_log(scan_job_id, "全網站主動掃描：略過 Nuclei（位於 CDN 後），Katana 獨佔 RPS 預算")
        try:
            ctx.katana_findings, ctx.katana_tech = run_katana(
                target, scan_job.max_depth, scan_job.max_pages,
                rate_limit=active_rps, scan_job_id=scan_job_id,
            )
            ctx.coverage.mark("katana", COMPLETED)
        except ScanCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            _tool_failed(ctx, "katana", "Katana", exc)
        return

    append_log(scan_job_id, "全網站主動掃描：Katana 與 Nuclei 執行受控探測")
    katana_rps = max(active_rps // 2, 1)
    nuclei_rps = max(active_rps - katana_rps, 1)

    if active_rps == 1:
        # 只有 1 RPS 預算時不可並行兩個最低各 1 RPS 的工具，否則總流量會翻倍。
        try:
            ctx.katana_findings, ctx.katana_tech = run_katana(
                target,
                scan_job.max_depth,
                scan_job.max_pages,
                rate_limit=1,
                scan_job_id=scan_job_id,
            )
            ctx.coverage.mark("katana", COMPLETED)
        except ScanCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            _tool_failed(ctx, "katana", "Katana", exc)
        raise_if_cancelled(scan_job_id)
        try:
            _run_nuclei_for_scan(ctx, target, 1)
        except ScanCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            _tool_failed(ctx, "nuclei", "Nuclei", exc)
        return

    # 預算至少 2 RPS 才並行，兩個 process 的 RPS 合計不得超過總上限。
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_katana = executor.submit(
            run_katana,
            target,
            scan_job.max_depth,
            scan_job.max_pages,
            rate_limit=katana_rps,
            scan_job_id=scan_job_id,
        )
        f_nuclei = executor.submit(_run_nuclei_for_scan, ctx, target, nuclei_rps)
    try:
        ctx.katana_findings, ctx.katana_tech = f_katana.result()
        ctx.coverage.mark("katana", COMPLETED)
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        _tool_failed(ctx, "katana", "Katana", exc)
    try:
        f_nuclei.result()  # 結果已在執行緒內套用；這裡只讓例外冒出
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        _tool_failed(ctx, "nuclei", "Nuclei", exc)


def _run_single_page_nuclei(ctx: ScanRunContext, target: str) -> None:
    """單頁主動掃描：不啟動 Katana 整站探索；Nuclei 與全網站相同，只掃網站根網址。"""
    append_log(ctx.scan_job_id, "單頁主動掃描：略過 Katana 整站探索")
    try:
        _run_nuclei_for_scan(ctx, target, settings.ARGUS_ACTIVE_MAX_RPS)
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        _tool_failed(ctx, "nuclei", "Nuclei", exc)


_WAF_KEYWORDS = {"cloudflare", "fastly", "akamai", "aws waf", "imperva", "sucuri", "f5"}


def _waf_blocked_nuclei_note(ctx: ScanRunContext) -> list[dict]:
    """Nuclei 無發現且 Katana 偵測到已知 WAF／CDN 時，補一筆 info 說明結果可能不完整。

    0 項發現只代表「沒有產生 finding」，不能推論成 WAF 擋下了攻擊（2026-10-06 審查）；
    真的被攔截要看 403／challenge 等證據，由 waf_scanner.detect_waf_block 判定。
    """
    # 只有完整跑完才談得上「0 項發現」；失敗或逾時已由覆蓋紀錄說明
    if (
        ctx.nuclei_findings
        or not ctx.katana_tech
        or ctx.coverage.status_of("nuclei") != COMPLETED
    ):
        return []
    detected_wafs = [
        t for t in ctx.katana_tech if any(w in t.lower() for w in _WAF_KEYWORDS)
    ]
    if not detected_wafs:
        return []
    waf_names = "、".join(detected_wafs)
    template_count = ctx.nuclei_template_set.get("templates", 0)
    append_log(
        ctx.scan_job_id,
        f"目標位於 {waf_names} 之後且 Nuclei 0 項發現，已新增「結果可能不完整」說明",
    )
    return [{
        "category": "security",
        "severity": "info",
        "title": f"主動弱點掃描 0 項發現，但目標位於 {waf_names} 之後",
        "description": (
            f"Nuclei 以 {template_count} 個已知被利用漏洞（KEV）模板探測網站根網址，"
            "沒有產生任何發現。"
            f"由於流量先經過 {waf_names}，部分探測可能在邊緣節點就被過濾，"
            "因此「0 項發現」不代表網站沒有弱點，也不能證明防火牆擋下了攻擊。"
        ),
        "remediation": (
            "此為資訊性提示，不需要修復。"
            "如需完整弱點掃描，可在 WAF 規則中暫時放行授權的掃描來源，"
            "或在沒有 WAF 的測試環境執行深度資安稽核。"
        ),
        "evidence": (
            f"偵測技術棧：{', '.join(ctx.katana_tech)}；"
            f"Nuclei 掃描網站根網址（KEV 模板 {template_count} 個），回傳 0 項發現"
        ),
        "selector": "",
        "bounding_box": None,
        "impact_area": "vulnerability",
        "confidence": 0.5,
        "priority_score": 10.0,
        "ai_handoff_prompt": (
            f"網站位於 {waf_names} 之後，Nuclei 主動掃描 0 項發現，結果可能被邊緣節點過濾。"
            "請建議如何在授權環境下完成更完整的弱點掃描。"
        ),
    }]


def _behind_waf_cdn(ctx: ScanRunContext) -> str:
    """目標前方若是全代理型 WAF／CDN（會過濾 root-URL KEV 探測）就回供應商名稱，否則回 ""。

    用爬蟲已抓到的首頁回應標頭判定（cf-ray、x-amz-cf-id…，`infra_scanner.detect_edge`），
    退而求其次用 fingerprint 階段記的 edge 供應商字串；只認 `_WAF_CAPABLE`（Cloudflare 等
    會把流量停在邊緣的服務，不含 Vercel／Netlify 這種直接代管應用的平台）。
    """
    from apps.scans.security.infra_scanner import _WAF_CAPABLE, detect_edge

    root = next((p for p in ctx.crawled_pages if p.get("headers")), None)
    edge = detect_edge((root or {}).get("headers") or {}, [], [])
    if edge and edge.get("waf_capable"):
        return str(edge["provider"])
    provider = str((ctx.scan_job.fingerprint or {}).get("edge") or "")
    return provider if provider in _WAF_CAPABLE else ""


def _nuclei_skipped_cdn_note(ctx: ScanRunContext, provider: str) -> list[dict]:
    """目標位於全代理 CDN 後、刻意略過 Nuclei 時補的 info 說明（0 項不等於沒弱點）。"""
    append_log(
        ctx.scan_job_id,
        f"目標位於 {provider} 之後，已略過 root-URL KEV Nuclei 掃描（會被邊緣過濾），節省掃描時間",
    )
    return [{
        "category": "security",
        "severity": "info",
        "title": f"已略過主動弱點掃描：目標位於 {provider} 之後",
        "description": (
            f"目標流量先經過 {provider}（全代理型 CDN／WAF），Nuclei 的已知被利用漏洞（KEV）模板"
            "探測網站根網址時會停在邊緣節點、幾乎到不了原始主機，實測一律 0 項發現卻耗時十餘分鐘。"
            "為縮短掃描時間已略過。這不代表網站沒有弱點，也不能證明防護規則有在運作。"
        ),
        "remediation": (
            "此為資訊性提示，不需要修復。如需完整的已知漏洞掃描，可在沒有 CDN／WAF 的測試環境、"
            "或在邊緣規則暫時放行授權掃描來源後執行。"
        ),
        "evidence": f"偵測到前端邊緣：{provider}；已略過網站根網址的 KEV Nuclei 掃描",
        "selector": "",
        "bounding_box": None,
        "impact_area": "vulnerability",
        "confidence": 0.5,
        "priority_score": 10.0,
        "ai_handoff_prompt": (
            f"網站位於 {provider} 之後，Argus 已略過 Nuclei root-URL 主動掃描（會被邊緣過濾）。"
            "請建議如何在授權環境下完成更完整的已知漏洞掃描。"
        ),
    }]


def stage_active_probe(ctx: ScanRunContext) -> None:
    """主動探測（Nuclei／Katana），同時遵守「單頁／全網站」範圍與 active 授權。

    被動模式不發任何探針；單頁主動只讓 Nuclei 掃輸入頁。目標位於全代理型 CDN／WAF 後時，
    root-URL KEV Nuclei 會被邊緣過濾（實測 0 發現卻耗十餘分鐘），略過並改出一筆說明。
    """
    plan = ctx.execution_plan
    raise_if_cancelled(ctx.scan_job_id)
    _collect_probe_targets(ctx)
    target = assert_public_http_url(ctx.scan_job.normalized_url)

    behind_cdn = _behind_waf_cdn(ctx) if plan.run_nuclei else ""
    skip_nuclei = bool(behind_cdn) and settings.ARGUS_NUCLEI_SKIP_BEHIND_CDN
    run_nuclei_now = plan.run_nuclei and not skip_nuclei

    # active_probe 只要是本次計畫的步驟就標記為進行中：CDN 短路跳過 Nuclei 時 Katana 仍在這一步跑，
    # 進度條才不會停在上一步、再跳到 deep_security（步數清單與總進度不受影響，純視覺一致性）。
    if plan.run_nuclei:
        ctx.scanning_progress(ctx.scanning_total, "active_probe")
    if plan.run_katana:
        _run_site_active_tools(ctx, target, skip_nuclei=skip_nuclei)
    elif run_nuclei_now:
        _run_single_page_nuclei(ctx, target)
    elif not plan.run_nuclei:
        append_log(ctx.scan_job_id, "被動模式：略過 Nuclei、Katana 與其他主動探測工具")
    if skip_nuclei:
        ctx.nuclei_findings = _nuclei_skipped_cdn_note(ctx, behind_cdn)
        ctx.coverage.mark(
            "nuclei", SKIPPED,
            f"位於 {behind_cdn} 等全代理 CDN 之後，root-URL KEV 探測會被邊緣過濾，已略過",
        )
    elif not plan.run_nuclei:
        ctx.coverage.mark("nuclei", SKIPPED, "未授權主動測試")
    if not plan.run_katana:
        ctx.coverage.mark("katana", SKIPPED, "單頁或未授權主動測試")
    ctx.scanning_progress(ctx.scanning_total + 1, "deep_security")

    waf_note = _waf_blocked_nuclei_note(ctx)
    if waf_note:
        ctx.nuclei_findings = waf_note
        # 0 項發現但流量先經過 WAF／CDN：探測可能被邊緣過濾，不能當成完整結果
        ctx.coverage.mark("nuclei", PARTIAL, "目標位於 WAF／CDN 之後，探測可能被過濾")
    ctx.record(ctx.katana_findings, check="katana")
    ctx.record(ctx.nuclei_findings, check="nuclei")
    if ctx.nuclei_template_set:
        # 模板集紀錄：同一指紋才代表同一組檢查，重現或比較結果時要看這裡
        scan_job = ctx.scan_job
        warnings = dict(scan_job.warning_summary or {})
        warnings["nuclei"] = ctx.nuclei_template_set
        scan_job.warning_summary = warnings
        scan_job.save(update_fields=["warning_summary", "updated_at"])
    # Kali 主動驗證已移到 Agent 之後（Hermes-first fallback）；這裡標示 Nuclei 階段結束、
    # 即將進入深度被動安全掃描。
    ctx.scanning_progress(ctx.scanning_total + 2, "deep_security")


def stage_deep_security(ctx: ScanRunContext) -> None:
    """深度被動安全掃描（security/ 子套件）。

    TLS、Cookie、標頭品質、SRI、DNS、JS 函式庫已知漏洞、服務版本 CVE，外加 WAF 封鎖偵測。
    """
    scan_job = ctx.scan_job
    host = urlparse(scan_job.normalized_url).hostname or ""
    root_page = next((p for p in ctx.crawled_pages if p.get("headers")), None)
    root_headers = root_page["headers"] if root_page else {}
    root_url = (
        (root_page.get("final_url") or root_page.get("url"))
        if root_page else scan_job.normalized_url
    )
    findings = (
        analyze_ssl(host, scan_job_id=scan_job.id)
        + analyze_cookies(root_headers, root_url)
        + analyze_headers(ctx.crawled_pages)
        + analyze_sri(ctx.crawled_pages)
        + analyze_dns(host)
        + analyze_js_libraries(ctx.crawled_pages)
        + analyze_services(ctx.crawled_pages)
        + _js_secret_findings(ctx)
        # ADR-0005 §2：移植自 ZAP 被動的自家檢查（混合內容／URL 敏感參數／頁面錯誤洩漏）
        + analyze_passive_html(ctx.crawled_pages)
    )
    # WAF／防護機制封鎖偵測（被動：統計已落地 Page 的 403/429 與 challenge 特徵，
    # 達閾值才產出單一 info finding，未達閾值回 None 不打擾使用者）
    waf_block_finding = detect_waf_block(scan_job)
    if waf_block_finding:
        findings.append(waf_block_finding)
        append_log(ctx.scan_job_id, "偵測到 WAF／防護機制封鎖跡象，已新增說明 finding")
    # 已知漏洞補 EPSS 被利用機率與 OSV 修補版本（只送函式庫名稱／版本／CVE；失敗原樣保留）
    findings = enrich_vuln_intel(findings)
    findings = [owasp_mapper.tag(f) for f in findings]
    ctx.record(findings, check="deep_security")
    ctx.coverage.mark("deep_security", COMPLETED)
    _passive_api_check(ctx)
    owasp_mapper.backfill(scan_job)
    append_log(ctx.scan_job_id, f"深度被動安全掃描完成：{len(findings)} 項發現")
    ctx.scanning_progress(
        ctx.scanning_total + 3,
        _first_step(
            ctx.steps, "zap_active", "exposure_probe", "geo_site", "seo_links", "agent",
            "scoring",
        ),
    )


def _js_secret_findings(ctx: ScanRunContext) -> list[dict]:
    """外部 JS bundle 的秘鑰 finding（ADR-0005 §1）：crawler 已掃好，這裡按來源檔分組成 finding。

    與逐頁的 HTML／inline script 秘鑰（`_analyze_one_page`）互補——那只看頁面本身，不看外部 .js。
    """
    by_source: dict[str, list[dict]] = {}
    for secret in ctx.site_signals.get("js_secrets") or []:
        by_source.setdefault(secret.get("source") or "JavaScript 檔案", []).append(secret)
    findings: list[dict] = []
    for source, secrets in by_source.items():
        location = redact_url_query_values(source)
        secret_finding = build_secret_finding(secrets, location, source="js_bundle")
        if secret_finding:
            findings.append(secret_finding)
        browser_key_finding = build_browser_key_finding(secrets, location, source="js_bundle")
        if browser_key_finding:
            findings.append(browser_key_finding)
    return findings


def _passive_api_check(ctx: ScanRunContext) -> None:
    """被動 API 檢查：爬取期間前端自己呼叫的同網站 API 回應（不發新請求）。

    API 端點清單存 `warning_summary["api_surface"]`（方法、路徑、狀態碼，不含查詢字串與回應內容）。
    另併入前端 JS bundle 靜態抽出、但頁面執行期未實際呼叫的端點（`site_signals.js_api_paths`），
    標為 `source="js_static"`，避免「公開頁不呼叫後端 API」時附錄誤報成「沒有可檢查的端點」。
    """
    observations = ctx.site_signals.get("api_observations") or []
    static_paths = sorted(_static_api_paths(ctx))
    if not observations and not static_paths:
        ctx.coverage.mark("api_passive", SKIPPED, "爬取期間沒有觀察到同網站的 API 呼叫")
        return
    try:
        api_findings, surface = analyze_api(observations, ctx.scan_job.origin)
    except Exception as exc:  # noqa: BLE001 — API 檢查失敗不影響其他資安檢查
        _tool_failed(ctx, "api_passive", "被動 API 檢查", exc)
        return
    # 靜態發現的端點（執行期沒被呼叫的才補上，避免與觀察到的重複）
    observed_paths = {row["path"] for row in surface["endpoints"]}
    static_rows = [
        {"method": "靜態", "path": p, "status": None, "content_type": "",
         "rules": [], "source": "js_static"}
        for p in static_paths if p not in observed_paths
    ]
    if static_rows:
        surface["endpoints"] = (surface["endpoints"] + static_rows)[:MAX_SURFACE_ENDPOINTS]
        surface["static_discovered"] = len(static_rows)
    ctx.record([owasp_mapper.tag(f) for f in api_findings], check="api_passive")
    ctx.coverage.mark("api_passive", COMPLETED)
    scan_job = ctx.scan_job
    warnings = dict(scan_job.warning_summary or {})
    warnings["api_surface"] = surface
    scan_job.warning_summary = warnings
    scan_job.save(update_fields=["warning_summary", "updated_at"])
    append_log(
        ctx.scan_job_id,
        f"被動 API 檢查：執行期 {surface['total']} 個、靜態 {len(static_rows)} 個端點，"
        f"{len(api_findings)} 項發現",
    )


def stage_zap_active(ctx: ScanRunContext) -> None:
    """OWASP ZAP 主動掃描：先用爬蟲 HAR 建站台樹，再對目標送攻擊 payload 找弱點。

    只在「全站＋主動模式＋網域已驗證」且開啟 `ARGUS_ZAP_ACTIVE_ENABLED` 時跑；與被動分析互補。
    ZAP 無法使用或無可掃描節點時只標覆蓋 skipped／failed，掃描照常完成。
    """
    scan_job = ctx.scan_job
    if not _runs_zap_active(scan_job):
        reason = _zap_active_skip_reason(scan_job)
        if reason:
            ctx.coverage.mark("zap_active", SKIPPED, reason)
        return
    raise_if_cancelled(ctx.scan_job_id)
    ctx.scanning_progress(ctx.scanning_total + 3, "zap_active")
    har_files = sorted(ctx.har_dir.glob("*.har")) if ctx.har_dir else []
    try:
        result = run_zap_active(
            har_files, scan_job.origin, scan_job.id,
            cancel_check=lambda: raise_if_cancelled(ctx.scan_job_id),
        )
    except ZapBusy as exc:
        append_log(ctx.scan_job_id, f"ZAP 主動掃描略過：{exc}", level="warn")
        ctx.coverage.mark("zap_active", SKIPPED, str(exc))
        return
    except ZapError as exc:
        append_log(ctx.scan_job_id, f"ZAP 主動掃描失敗：{exc}", level="warn")
        ctx.coverage.mark("zap_active", FAILED, str(exc))
        return
    finally:
        _discard_har(ctx)
    if not result.scanned:
        ctx.coverage.mark("zap_active", SKIPPED, result.reason or "沒有可主動掃描的節點")
        return
    findings, overlap = alerts_to_findings(result.alerts, result.version, active=True)
    if result.version:
        warnings = dict(scan_job.warning_summary or {})
        warnings["tools"] = {**(warnings.get("tools") or {}), "OWASP ZAP": result.version}
        scan_job.warning_summary = warnings
        scan_job.save(update_fields=["warning_summary", "updated_at"])
    ctx.record(findings, check="zap_active")
    if result.completed:
        ctx.coverage.mark("zap_active", COMPLETED)
    else:
        ctx.coverage.mark("zap_active", PARTIAL, "ZAP 主動掃描在時限內沒有跑完")
    append_log(
        ctx.scan_job_id,
        f"ZAP {result.version} 主動掃描：{len(result.alerts)} 則告警，新增 {len(findings)} 項問題；"
        f"另有 {sum(overlap.values())} 則與既有檢查相同、不重複列出",
    )


def _observed_api_paths(ctx: ScanRunContext) -> list[str]:
    """爬取時觀察到的同網站 API 路徑：被動 API 檢查的回應摘要＋攔截到的 XHR／fetch 端點。"""
    paths = [
        str(item.get("path") or "")
        for item in ctx.site_signals.get("api_observations") or []
        if isinstance(item, dict)
    ]
    paths += [urlparse(url).path for url in ctx.discovered_endpoints or []]
    # 爬蟲從同源 JS bundle 靜態抽出的 API 路徑（繞過 Cloudflare 的確定性發現，2026-10-16）
    paths += _static_api_paths(ctx)
    return paths


def _static_api_paths(ctx: ScanRunContext) -> list[str]:
    """JS 靜態抽出的 API 路徑，排除爬蟲當成網頁造訪過的路徑。

    `service`、`v1` 這類提示字也會出現在一般頁面網址（2026-10-17 實掃：`/service/1` 是導覽列
    連到的頁面，卻被列進 API 端點清單）；爬蟲實際造訪過的就是頁面，不是 API。
    """
    page_paths = {
        urlparse(page.get(key) or "").path.rstrip("/") or "/"
        for page in ctx.crawled_pages or []
        for key in ("url", "final_url")
        if page.get(key)
    }
    return [
        path for path in ctx.site_signals.get("js_api_paths") or []
        if (path.rstrip("/") or "/") not in page_paths
    ]


def stage_exposure(ctx: ScanRunContext) -> None:
    """敏感資訊外洩：robots.txt 敏感路徑（被動，任何模式）＋敏感檔案主動探測（全網站 active）。"""
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    robots_disallow = ctx.site_signals.get("robots_disallow") or []
    ctx.record(
        [
            owasp_mapper.tag(f)
            for f in exposure_scanner.analyze_robots_disclosure(robots_disallow)
        ],
        check="exposure_robots",
    )
    ctx.coverage.mark("exposure_robots", COMPLETED)

    if ctx.execution_plan.run_exposure:
        raise_if_cancelled(scan_job_id)
        append_log(scan_job_id, "敏感檔案外洩探測開始（主動內容探測，繞連結直接探隱藏檔）")
        try:
            probe_results = _run_async(
                lambda: exposure_scanner.probe_paths(
                    scan_job.normalized_url,
                    scan_job.origin,
                    scan_job_id,
                    robots_disallow=robots_disallow,
                    api_path_prefixes=exposure_scanner.api_prefixes(_observed_api_paths(ctx)),
                )
            )
            exposure_findings = [
                owasp_mapper.tag(f)
                for f in exposure_scanner.analyze_probe_results(probe_results)
            ]
            ctx.record(exposure_findings, check="exposure_probe")
            ctx.coverage.mark("exposure_probe", COMPLETED)
            append_log(
                scan_job_id,
                f"敏感檔案外洩探測完成：探測 {len(probe_results)} 路徑，"
                f"發現 {len(exposure_findings)} 項外洩",
            )
        except ScanCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 — 探測失敗不影響主掃描
            logger.exception("掃描子步驟失敗 scan_job_id=%s", scan_job_id)
            ctx.coverage.mark("exposure_probe", FAILED, exc.__class__.__name__)
            append_log(
                scan_job_id,
                f"敏感檔案外洩探測略過（{exc.__class__.__name__}）",
                level="warn",
            )
        _run_authz_probe(ctx)
    else:
        ctx.coverage.mark("exposure_probe", SKIPPED, "單頁或未授權主動測試")
        ctx.coverage.mark("authz_probe", SKIPPED, "單頁或未授權主動測試")
        if ctx.execution_plan.active_authorized:
            append_log(scan_job_id, "單頁範圍：略過整站敏感檔案路徑探測")


    if ctx.katana_tech:
        updated_warnings = dict(scan_job.warning_summary or {})
        updated_warnings["tech_stack"] = ctx.katana_tech
        scan_job.warning_summary = updated_warnings
        scan_job.save(update_fields=["warning_summary", "updated_at"])
    ctx.scanning_progress(
        ctx.deep_scan_total, _first_step(ctx.steps, "geo_site", "seo_links", "agent", "scoring")
    )
    append_log(
        scan_job_id,
        f"資安補充掃描完成：Katana {len(ctx.katana_findings)} 項，"
        f"Nuclei {len(ctx.nuclei_findings)} 項"
        + (f"，技術棧：{', '.join(ctx.katana_tech)}" if ctx.katana_tech else ""),
    )


def _run_authz_probe(ctx: ScanRunContext) -> None:
    """未授權存取探測：對發現的 API 端點做無憑證 GET，成批帳號／成員記錄匿名可讀即報。

    把 Agent 偶然打到的未授權個資 API 沉澱成確定性檢查；失敗不影響主掃描。
    """
    scan_job_id = ctx.scan_job_id
    origin = ctx.scan_job.origin
    candidates = [
        f"{origin}/{path.lstrip('/')}"
        for path in dict.fromkeys(_observed_api_paths(ctx))  # 去重保序
        if path
    ]
    if not candidates:
        ctx.coverage.mark("authz_probe", SKIPPED, "沒有發現可探測的 API 端點")
        return
    raise_if_cancelled(scan_job_id)
    try:
        results = _run_async(
            lambda: probe_unauthorized_endpoints(candidates, scan_job_id)
        )
        findings = [
            owasp_mapper.tag(f) for f in analyze_unauthorized_results(results)
        ]
        ctx.record(findings, check="authz_probe")
        ctx.coverage.mark("authz_probe", COMPLETED)
        append_log(
            scan_job_id,
            f"未授權存取探測完成：探測 {len(results)} 個 API 端點，"
            f"發現 {len(findings)} 項未授權記錄外洩",
        )
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 — 探測失敗不影響主掃描
        logger.exception("掃描子步驟失敗 scan_job_id=%s", scan_job_id)
        ctx.coverage.mark("authz_probe", FAILED, exc.__class__.__name__)
        append_log(
            scan_job_id,
            f"未授權存取探測略過（{exc.__class__.__name__}）",
            level="warn",
        )


def stage_geo_site(ctx: ScanRunContext) -> None:
    """站台層級 GEO 檢查（llms.txt、AI 爬蟲可存取性、組織實體與文章作者）；未勾 GEO 維度時跳過。"""
    if "geo" not in ctx.scan_job.effective_categories:
        return
    findings = analyze_site_signals(ctx.site_signals)
    entity = analyze_entity([page for page, _data in ctx.pages])
    findings += entity_findings(entity) + freshness_findings(entity, timezone.localdate())
    ctx.record(findings, check="geo_site")
    ctx.coverage.mark("geo_site", COMPLETED)
    append_log(ctx.scan_job_id, f"站台訊號分析完成：{len(findings)} 項發現")


def stage_seo_links(ctx: ScanRunContext) -> None:
    """SEO 連結狀態與站台層級網址檢查（勾 SEO 才跑），結果寫 ScanJob.seo_report。

    失效站內連結、www 重複、主網址不一致、重複 title、sitemap／robots／noindex 矛盾另轉成 Finding
    （`seo/site_findings.py`），
    問題清單與報告才看得到；連結檢查本身失敗只記 log、不影響掃描完成。
    """
    scan_job = ctx.scan_job
    if "seo" not in scan_job.effective_categories or not ctx.pages:
        return
    ctx.scanning_progress(ctx.deep_scan_total, "seo_links")
    start_url = scan_job.normalized_url or scan_job.original_url
    try:
        report = build_link_report(
            start_url,
            [page for page, _data in ctx.pages],
            should_stop=lambda: raise_if_cancelled(ctx.scan_job_id),
            site_signals=ctx.site_signals,
        )
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - 輔助資料，失敗不影響掃描
        logger.warning("SEO 連結檢查失敗 scan_job_id=%s", ctx.scan_job_id, exc_info=True)
        append_log(ctx.scan_job_id, f"SEO 連結檢查失敗：{exc.__class__.__name__}", level="warning")
        ctx.coverage.mark("seo_links", FAILED, exc.__class__.__name__)
        return
    report["coverage"] = link_coverage(report)
    try:
        trend = _link_trend_for(ctx, report)
    except Exception:  # noqa: BLE001 - 趨勢是輔助資料，失敗不影響掃描
        logger.warning("SEO 連結趨勢計算失敗 scan_job_id=%s", ctx.scan_job_id, exc_info=True)
        trend = None
    if trend:
        report["trend"] = trend
    scan_job.seo_report = report
    scan_job.save(update_fields=["seo_report", "updated_at"])
    try:
        site_findings = seo_site_findings(
            report,
            [page for page, _data in ctx.pages],
            start_url,
            sitemap_urls=ctx.site_signals.get("sitemap_urls") or [],
            robots_text=ctx.site_signals.get("robots_text"),
        )
    except Exception:  # noqa: BLE001 - 轉換失敗不影響掃描
        logger.warning("SEO 站台問題轉換失敗 scan_job_id=%s", ctx.scan_job_id, exc_info=True)
        site_findings = []
    ctx.record(site_findings, check="seo_links")
    unchecked = report.get("unchecked", 0)
    not_confirmed = coverage_text(report["coverage"])
    ctx.coverage.mark(
        "seo_links", PARTIAL if unchecked else COMPLETED,
        f"沒有明確結果的連結：{not_confirmed}" if unchecked else "",
    )
    links = report.get("links") or {}
    broken = sum(1 for r in links.values() if r["verdict"] == "broken")
    append_log(
        ctx.scan_job_id,
        f"SEO 連結檢查完成：{len(links)} 個連結（失效 {broken}），"
        f"未檢查 {report.get('unchecked', 0)} 個" + _reused_text(report.get("reused") or {}),
    )


def _reused_text(reused: dict) -> str:
    """沿用爬取階段已取得結果、沒有重送的請求（roadmap §11 第 1 項）。"""
    count = reused.get("links", 0) + reused.get("site_checks", 0) + int(bool(reused.get("robots")))
    return f"；沿用爬取階段已有結果 {count} 個請求" if count else ""


def _link_trend_for(ctx: ScanRunContext, report: dict) -> dict | None:
    """和同專案上一次有連結檢查的完成掃描比較失效連結（roadmap §11 第 3 項）。

    沒有可比的掃描回 None。
    """
    from apps.scans.projects import completed_scans

    scan_job = ctx.scan_job
    if scan_job.project is None:
        return None
    previous = (
        completed_scans(scan_job.project)
        .filter(created_at__lt=scan_job.created_at)
        .exclude(id=scan_job.id)
        .exclude(seo_report={})
        .first()
    )
    if previous is None or "links" not in (previous.seo_report or {}):
        return None
    current = effective_verdicts(report, crawled_verdicts(
        (page.url, page.final_url, page.status_code) for page, _data in ctx.pages
    ))
    before = effective_verdicts(previous.seo_report, crawled_verdicts(
        previous.pages.values_list("url", "final_url", "status_code")
    ))
    return link_trend(
        current, before, previous_scan_id=previous.id,
        previous_checked_at=previous.seo_report.get("checked_at"),
    )


# PageSpeed Insights 只是等 Google 量測（20～90 秒），不佔本機資源：爬取完就在背景送出，
# 與頁面分析、資安檢查、連結檢查同時進行，stage_pagespeed 只取結果（2026-10-10）。
# 只在背景執行網路請求，資料庫寫入與覆蓋紀錄仍在主流程做。
_PAGESPEED_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pagespeed")


def _pagespeed_target(ctx: ScanRunContext) -> str:
    return ctx.scan_job.normalized_url or ctx.scan_job.original_url


def stage_pagespeed_start(ctx: ScanRunContext) -> None:
    """勾 UX 且已設定金鑰時，在背景送出 PageSpeed Insights 量測。"""
    if "ux" not in ctx.scan_job.effective_categories or not pagespeed_enabled():
        return
    url = _pagespeed_target(ctx)
    # 用 lambda 在執行時才取 fetch_pagespeed，測試 patch 模組名稱才有效
    ctx.pagespeed_future = _PAGESPEED_EXECUTOR.submit(lambda: fetch_pagespeed(url))


def stage_pagespeed(ctx: ScanRunContext) -> None:
    """Google PageSpeed Insights：首頁的 Lighthouse 實驗室分數＋CrUX 真實使用者資料。

    勾 UX 且有設定金鑰才跑；結果寫 ScanJob.performance_report，不併入 Argus 分數。
    量測失敗只記 log 與覆蓋紀錄，不影響掃描完成。量測通常已在背景完成
    （stage_pagespeed_start），這裡只等結果；沒有背景量測時當場量測。
    """
    scan_job = ctx.scan_job
    if "ux" not in scan_job.effective_categories:
        return
    if not pagespeed_enabled():
        # 勾了使用體驗卻沒有量測：記下原因，效能分頁據此說明是平台尚未設定，不是使用者沒勾
        ctx.coverage.mark("pagespeed", SKIPPED, "平台尚未設定 Google PageSpeed Insights 金鑰")
        return
    raise_if_cancelled(ctx.scan_job_id)
    ctx.scanning_progress(ctx.deep_scan_total, "pagespeed")
    try:
        if ctx.pagespeed_future is not None:
            report = ctx.pagespeed_future.result()
        else:
            report = fetch_pagespeed(_pagespeed_target(ctx))
    except PageSpeedError as exc:
        append_log(ctx.scan_job_id, f"PageSpeed Insights 量測失敗：{exc}", level="warn")
        ctx.coverage.mark("pagespeed", FAILED, str(exc))
        return
    raise_if_cancelled(ctx.scan_job_id)
    scan_job.performance_report = report
    scan_job.save(update_fields=["performance_report", "updated_at"])
    lab = report.get("lab") or {}
    if lab.get("error"):
        ctx.coverage.mark("pagespeed", PARTIAL, "Lighthouse 無法完成量測")
    else:
        ctx.coverage.mark("pagespeed", COMPLETED)
    scores = lab.get("scores") or {}
    field = report.get("field") or {}
    append_log(
        ctx.scan_job_id,
        f"PageSpeed Insights：效能 {scores.get('performance', '—')}；真實使用者資料"
        + ("有" if field.get("metrics") else "不足"),
    )


def stage_favicon(ctx: ScanRunContext) -> None:
    """更新所屬網站專案的圖示（會員區辨識網站用）；最多每 7 天抓一次，失敗不影響掃描。"""
    project = ctx.scan_job.project
    if project is None or not ctx.pages or not needs_refresh(project):
        return
    page, _data = ctx.pages[0]
    try:
        refresh_project_favicon(project, page.html or "", page.final_url or page.url)
    except Exception:  # noqa: BLE001 - 圖示只是輔助資料
        logger.warning("網站圖示更新失敗 scan_job_id=%s", ctx.scan_job_id, exc_info=True)


# Hermes-Agent 子代理角色 → 前端顯示的中文名（讓使用者看得出「現在在跑哪個專家」）。
# role_label 由 runner._run_session 帶入：recon／orchestrator／ux／specialist／specialist:<role>。
_AGENT_ROLE_LABELS = {
    "recon": "偵察目標",
    "orchestrator": "指揮調度",
    "ux": "擬真使用者體驗測試",
    "specialist": "資安專家測試",
}
# specialist:<role> 的 8 種專家角色（對應 runner.SPECIALIST_ROLES）。
_AGENT_SPECIALIST_LABELS = {
    "auth_idor": "認證與越權（IDOR）專家",
    "injection": "注入攻擊專家",
    "logic_abuse": "商業邏輯濫用專家",
    "info_leak": "資訊洩漏專家",
    "xss_hunter": "跨站腳本（XSS）專家",
    "jwt_token_abuse": "JWT／Token 濫用專家",
    "file_upload": "檔案上傳專家",
    "crypto": "加密弱點專家",
}


def _agent_role_label(role_label: str) -> str:
    """把 runner 傳來的 role_label 轉成前端顯示用中文；未知角色給通用字樣。"""
    if role_label.startswith("specialist:"):
        role = role_label.split(":", 1)[1]
        return _AGENT_SPECIALIST_LABELS.get(role, f"{role} 專家")
    return _AGENT_ROLE_LABELS.get(role_label, "資安測試")


# 主動層覆蓋摘要（2026-10-18）：agent 之前已跑完 Nuclei／ZAP 主動／敏感檔探測／未授權探測
# （都在 SCAN_PIPELINE 排在 agent 前），把「已經做過哪些『無腦全掃』」告訴 recon／orchestrator，
# 叫專家別重做、把步數花在要推理／串接／差異式的部分（告知式，不硬跳過角色）。
_COVERAGE_STATUS_ZH = {
    COMPLETED: "已完整執行", PARTIAL: "部分執行（可能不完整）",
    SKIPPED: "本次略過", FAILED: "執行失敗",
}


def _active_coverage_summary(ctx: ScanRunContext) -> str:
    """組一段「確定性主動層這次已做過什麼」給 agent 參考；沒有任何主動檢查跑過時回空字串。"""
    cov = ctx.coverage
    api_count = len({p for p in _observed_api_paths(ctx) if p})
    rows: list[tuple[str, str | None, str]] = [
        ("Nuclei 已知漏洞（KEV）掃描", cov.status_of("nuclei"), ""),
        ("OWASP ZAP 主動掃描（spider＋active）", cov.status_of("zap_active"), ""),
        ("敏感檔案外洩探測（內建字典主動探隱藏檔）", cov.status_of("exposure"), ""),
        (
            "未授權存取探測（對同源 API 端點做無憑證 GET）",
            cov.status_of("authz_probe"),
            f"；已涵蓋約 {api_count} 個被觀察到的 API 端點" if api_count else "",
        ),
    ]
    lines = [
        f"- {label}：{_COVERAGE_STATUS_ZH.get(status, '')}{extra}"
        for label, status, extra in rows
        if status and status in _COVERAGE_STATUS_ZH
    ]
    return "\n".join(lines)


def stage_agent(ctx: ScanRunContext) -> None:
    """可選的 Hermes-Agent（資安 deep_mode 與／或擬真使用者 UX 測試）。

    預設 ARGUS_AGENT_ENABLED=False，避免每次掃描都消耗 LLM token。Agent 失敗不讓整個
    掃描失敗；Agent 確認的 security finding 會餵進計分（DB 落地由 runner 負責）。
    """
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    plan = ctx.execution_plan
    if not settings.ARGUS_AGENT_ENABLED:
        return
    if not (plan.run_agent or plan.run_agent_ux):
        append_log(scan_job_id, "Agent 略過：僅全網站且已授權的主動掃描可執行")
        return
    raise_if_cancelled(scan_job_id)
    # 送出表單的授權：主動授權掃描（run_agent）本就已驗證；被動 UX 測試
    # 只有在目標網域已通過所有權驗證（或 staff 測試旁路）時才允許實際送出。
    from apps.scans.services import get_hostname, user_owns_domain

    scan_hostname = get_hostname(scan_job.normalized_url or scan_job.original_url or "")
    may_submit_forms = bool(plan.run_agent) or user_owns_domain(scan_job.user, scan_hostname)
    from apps.agent.runner import max_total_steps_estimate, run_agent_for_scan

    agent_phase_started = timezone.now().isoformat()
    # agent 跑十餘分鐘，過去進度一路停在 0／20（那 20 還只是單一子代理的上限），看起來像卡住。
    # 以最壞情況總步數當分母，再由 runner 每步回報累計步數，進度條才會動、看得出活著（2026-10-18）。
    agent_total = max(max_total_steps_estimate(), 1)
    agent_steps_seen = {"n": 0}

    def _report_agent_step(role_label: str, round_no: int) -> None:
        """runner 每個子代理每步回呼：累加全域步數並回寫進度（fail-safe，不影響掃描）。"""
        try:
            agent_steps_seen["n"] += 1
            done = min(agent_steps_seen["n"], agent_total)
            _write_progress(
                scan_job_id, phase="agent_testing", done=done, total=agent_total,
                phase_started_at=agent_phase_started, step="agent", steps=ctx.steps,
                step_done=done, step_total=agent_total,
                detail=_agent_role_label(role_label),
            )
        except Exception:  # noqa: BLE001 — 進度回報失敗不得影響 agent 與掃描
            pass

    scan_job.status = ScanJob.Status.AGENT_TESTING
    scan_job.progress = {
        "pages_done": 0,
        "pages_total": agent_total,
        "phase": "agent_testing",
        "phase_started_at": agent_phase_started,
        "step": "agent",
        "step_done": 0,
        "step_total": agent_total,
        "step_started_at": agent_phase_started,
        "steps": ctx.steps,
    }
    scan_job.save(update_fields=["status", "progress", "updated_at"])
    try:
        # 把確定性工具這次已找到的資安問題餵給 agent，叫它別重報（ADR-0005 §5）——
        # 消掉「agent 盲跑 → 撞一堆重複 → 事後去重」的浪費
        known_findings = [f for f in ctx.all_findings if f.get("category") == "security"]
        agent_result = _run_async(
            lambda: run_agent_for_scan(
                scan_job,
                recon_intel=ctx.discovered_endpoints,
                may_submit_forms=may_submit_forms,
                known_findings=known_findings,
                coverage_summary=_active_coverage_summary(ctx),
                progress_cb=_report_agent_step,
            )
        )
        ctx.agent_result = agent_result
        if agent_result:
            ctx.agent_meta = {
                "status": agent_result.status,
                "steps": agent_result.steps,
                "tokens": agent_result.total_tokens,
                "issues_reported": len(agent_result.issues),
                "error": agent_result.error,
                # agent 自述的受阻報告（缺工具／被拒／逾時），供能力改善分析
                "feedback": (agent_result.final_summary or "")[:1000],
            }
            _write_progress(
                scan_job_id,
                phase="agent_testing",
                done=min(max(agent_result.steps, agent_steps_seen["n"]), agent_total),
                total=agent_total,
                phase_started_at=agent_phase_started,
                step="agent",
                steps=ctx.steps,
            )
            for issue in agent_result.issues:
                ctx.all_findings.append(
                    {
                        "category": "ux",
                        "severity": issue.get("severity", "low"),
                        "title": issue.get("title", ""),
                        # 與 apps/agent/findings.py::persist_agent_issues 寫入 DB 時
                        # 用的 default_priority 對齊，否則 agent 回報的 critical/high
                        # UX 問題在 top_actions 排序時會輸給瑣碎的 SEO 項目。
                        "priority_score": 50.0,
                    }
                )
    except Exception as exc:  # noqa: BLE001 — agent 失敗不應讓整個掃描失敗
        logger.exception("Agent 執行失敗 scan_job_id=%s", scan_job_id)
        ctx.agent_meta = {"status": "error", "error": exc.__class__.__name__}

    if ctx.agent_result:
        ctx.all_findings.extend(ctx.agent_result.security_findings)
    _mark_agent_coverage(ctx)


def _mark_agent_coverage(ctx: ScanRunContext) -> None:
    """Agent 的覆蓋狀態：跑完＝completed、步數或 token 預算用完＝partial、
    出錯＝failed、沒啟動＝skipped。

    agent 的 finding 由 runner 直接落 DB，歷史比較以規則前綴（AGENT_UX_／agent-）對回檢查。
    """
    result = ctx.agent_result
    if ctx.agent_meta.get("status") == "error":
        status, reason = FAILED, ctx.agent_meta.get("error", "")
    elif result is None:
        status, reason = SKIPPED, "沒有可開始測試的頁面"
    elif result.status == "completed":
        status, reason = COMPLETED, ""
    elif str(result.error or "").startswith("max_steps_reached"):
        status, reason = PARTIAL, "步數上限內未完成"
    elif str(result.error or "").startswith("token_budget_exceeded"):
        # 預算用完前回報的問題照樣有效，只是沒跑完全部流程（2026-10-10 實測 14 步用完 6 萬）
        status, reason = PARTIAL, "token 預算內未完成"
    else:
        status, reason = FAILED, str(result.error or "")[:120]
    plan = ctx.execution_plan
    if plan.run_agent:
        ctx.coverage.mark("agent", status, reason)
    if plan.run_agent_ux:
        ctx.coverage.mark("agent_ux", status, reason)


def stage_kali(ctx: ScanRunContext) -> None:
    """Kali 主動驗證 fallback（Agent 之後、計分之前；僅 active＋authorized）。

    ARGUS_KALI_ENABLED 等其餘 gating 由 validate_findings_with_kali → run_sqlmap 的三重鎖
    負責，預設完全 inert。ScanCancelled 原樣重拋，讓取消傳遞到退款分支。
    """
    if not ctx.execution_plan.run_kali:
        return
    scan_job_id = ctx.scan_job_id
    raise_if_cancelled(scan_job_id)
    try:
        kali_findings = validate_findings_with_kali(
            scan_job_id, ctx.page_urls + ctx.endpoint_urls
        )
        ctx.coverage.mark("kali", COMPLETED)
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 — 非 cancel 的基礎設施失敗只 silent-fail
        logger.exception("掃描子步驟失敗 scan_job_id=%s", scan_job_id)
        append_log(
            scan_job_id,
            f"Kali 主動驗證略過（{exc.__class__.__name__}）",
            level="warn",
        )
        ctx.coverage.mark("kali", FAILED, exc.__class__.__name__)
        kali_findings = []
    ctx.record(kali_findings, check="kali")
    if kali_findings:
        append_log(scan_job_id, f"Kali 主動驗證確認 {len(kali_findings)} 項可利用漏洞")


def tested_categories_for(ctx: ScanRunContext) -> set[str]:
    """本次真的有測到的維度（沒列入的維度在分數中顯示「未評估」而不是滿分）。

    - security（DNS/SSL 站台層級）與 geo（llms.txt/robots）即使 0 頁仍有站台層級檢查。
    - seo/aeo 只來自逐頁分析：0 頁時沒測，不可把「沒測」當成「零問題」灌高總分。
    - ux 有兩個來源，任一成立才算有測：行動版版面量測（空 dict＝沒量到）、
      Agent 實際跑完（拋例外時 agent_meta 也有值，但 status=error 不算）。
    - aeo 的可回答性檢測若因內容不足而未充分評估，不列入。
    - 最後與勾選維度取交集：「沒買」不能被算成「測過」。
    """
    tested = {"security", "geo"}
    if ctx.crawled_pages:
        tested.update({"seo", "aeo"})
    if any(page.get("layout_metrics") for page in ctx.crawled_pages):
        tested.add("ux")
    if ctx.agent_meta and ctx.agent_meta.get("status") != "error":
        tested.add("ux")
    # AEO 內容不足以出題：未充分評估，不評分（不能因為沒問題可問就給 100 分）
    if ctx.aeo_evaluation is not None and ctx.aeo_evaluation.status != "evaluated":
        tested.discard("aeo")
    # 覆蓋契約：該維度的檢查全部失敗／被阻擋＝沒有測到，不能以「0 項問題」計分
    checks = ctx.coverage.to_json(())["checks"]
    recorded = {entry["category"] for entry in checks.values()}
    tested = {
        cat for cat in tested
        if cat not in recorded or category_status(checks, cat) != "not_tested"
    }
    return tested & ctx.scan_job.effective_categories


def coverage_for(ctx: ScanRunContext, tested_categories: set[str]) -> dict:
    """寫入 ScanJob.coverage 的內容；沒進計分的勾選維度一律標 not_tested。"""
    coverage = ctx.coverage.to_json(ctx.scan_job.effective_categories)
    for category in coverage["categories"]:
        if category not in tested_categories:
            coverage["categories"][category] = "not_tested"
    return coverage


def base_scores_for(ctx: ScanRunContext) -> dict[str, int]:
    """分類基準分：AEO 以可回答性分數為基準（見 scanners.calculate_scores）。"""
    evaluation = ctx.aeo_evaluation
    if evaluation is not None and evaluation.status == "evaluated":
        return {"aeo": evaluation.score}
    return {}


def stage_site_profile(ctx: ScanRunContext) -> None:
    """網站概況：基礎架構（DNS／IP／反解／CDN 邊緣）與網站優勢，寫 ScanJob.site_profile。

    只查目標自身網域的 DNS 並讀已取得的回應標頭；失敗只記 log，不影響掃描。
    """
    scan_job = ctx.scan_job
    hostname = urlparse(scan_job.normalized_url or scan_job.original_url).hostname or ""
    try:
        profile = build_site_profile(
            hostname=hostname,
            pages=ctx.crawled_pages,
            seo_report=scan_job.seo_report or {},
            findings=ctx.all_findings,
            categories=set(scan_job.effective_categories),
            extra_tech=ctx.katana_tech,
            ai_bot_policy=ctx.site_signals.get("ai_bot_policy"),
        )
    except Exception:  # noqa: BLE001 - 輔助資訊
        logger.warning("網站概況失敗 scan_job_id=%s", ctx.scan_job_id, exc_info=True)
        return
    scan_job.site_profile = profile
    scan_job.save(update_fields=["site_profile", "updated_at"])
    edge = (profile.get("infrastructure") or {}).get("edge")
    append_log(
        ctx.scan_job_id,
        f"網站概況：{'位於 ' + edge['provider'] + ' 之後' if edge else '未偵測到 CDN／反向代理'}；"
        f"網站優勢 {len(profile.get('strengths') or [])} 項",
    )


def stage_scoring(ctx: ScanRunContext) -> None:
    """計分並把掃描推進到 completed（CAS；已被取消則轉走取消分支）。"""
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    tested_categories = tested_categories_for(ctx)
    _write_progress(
        scan_job_id,
        phase=(
            "agent_testing"
            if scan_job.status == ScanJob.Status.AGENT_TESTING
            else "scanning"
        ),
        done=1,
        total=1,
        phase_started_at=timezone.now().isoformat(),
        step="scoring",
        steps=ctx.steps,
    )
    # 0 頁是「掃描實質失效」的強信號：標記並警告，避免總分（只反映站台層級）被誤讀為安全
    if not ctx.crawled_pages:
        eff_warnings = dict(scan_job.warning_summary or {})
        eff_warnings["scan_effectiveness"] = "no_pages_crawled"
        scan_job.warning_summary = eff_warnings
        append_log(
            scan_job_id,
            "掃描有效性警示：未抓到任何頁面（目標可能不可達或全 timeout）；"
            "SEO/AEO 未評估，總分僅反映站台層級檢查，不應解讀為網站安全。",
            level="warn",
        )
    # 跨層去重：確定性探測與 Agent 打到同一端點＋同類型時只留確定性那筆，否則計分扣兩次、
    # 報告列兩次（實測某授權掃描的 API 規格端點同時出現確定性 high 與 Agent high）
    ctx.all_findings, dropped = consolidate_cross_layer(ctx.all_findings)
    if dropped:
        Finding.objects.filter(
            scan_job=scan_job,
            rule_id__in=[str(f.get("rule_id") or "") for f in dropped],
        ).delete()
        append_log(
            scan_job_id,
            f"跨層去重：{len(dropped)} 筆 Agent 觀察與確定性探測指向同一端點，"
            "已合併，保留可重現的確定性發現",
        )
    overall_score, category_scores, top_actions = calculate_scores(
        ctx.all_findings,
        tested_categories=tested_categories,
        base_scores=base_scores_for(ctx),
    )
    append_log(
        scan_job_id,
        f"掃描完成 — 總分 {overall_score}，共 {len(ctx.all_findings)} 項發現",
    )
    scan_job.overall_score = overall_score
    scan_job.category_scores = category_scores
    scan_job.top_actions = top_actions
    scan_job.coverage = coverage_for(ctx, tested_categories)
    scan_job.scoring_version = SCORING_VERSION
    scan_job.ruleset_version = RULESET_VERSION
    if ctx.agent_meta:
        warning_summary = dict(scan_job.warning_summary or {})
        warning_summary["agent"] = ctx.agent_meta
        scan_job.warning_summary = warning_summary
    completed_at = timezone.now()
    completed = ScanJob.objects.filter(
        id=scan_job_id,
        status__in=[
            ScanJob.Status.CRAWLING,
            ScanJob.Status.SCANNING,
            ScanJob.Status.AGENT_TESTING,
        ],
    ).update(
        status=ScanJob.Status.COMPLETED,
        overall_score=overall_score,
        category_scores=category_scores,
        top_actions=top_actions,
        warning_summary=scan_job.warning_summary,
        coverage=scan_job.coverage,
        scoring_version=SCORING_VERSION,
        ruleset_version=RULESET_VERSION,
        progress={},
        completed_at=completed_at,
        updated_at=completed_at,
    )
    if not completed:
        raise ScanCancelled()
    scan_job.refresh_from_db()


def stage_settlement(ctx: ScanRunContext) -> dict:
    """點數結算（依實際頁數退差額）與修正產出額度贈與，回傳 task 結果。

    掃描已寫成 completed，結算失敗不可往上拋：拋出去會落到通用 except，把已完成的
    掃描改成 failed 並「全額」退款。這裡保留結果，只記錄待補結算。
    """
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    settlement_error = None
    try:
        # 深度資安附加費只在 agent 真的以深度模式跑過才收（沒跑就退回預扣）
        deep_agent_ran = bool(ctx.execution_plan.run_agent and ctx.agent_result is not None)
        settle_scan_actual(
            scan_job.user, scan_job, len(ctx.crawled_pages), deep_agent_ran=deep_agent_ran
        )
    except Exception as exc:  # noqa: BLE001
        settlement_error = exc.__class__.__name__
        append_log(
            scan_job_id,
            f"點數結算失敗（掃描結果保留，待補結算）：{settlement_error}",
            level="error",
        )
        warning_summary = dict(scan_job.warning_summary or {})
        warning_summary["settlement_error"] = settlement_error
        ScanJob.objects.filter(id=scan_job_id).update(warning_summary=warning_summary)
        scan_job.warning_summary = warning_summary
    # 付費掃描結算成功 → 附贈 1 次修正產出額度（冪等）。贈與失敗只記 log。
    try:
        grant_fixgen_entitlement(scan_job.user, scan_job)
    except Exception as exc:  # noqa: BLE001
        append_log(
            scan_job_id,
            f"修正產出額度贈與失敗（{exc.__class__.__name__}）",
            level="warn",
        )
    # AI 掃描解讀不在完成時自動產生（2026-10-10 使用者決策）：每次都花 token，
    # 改由使用者在報告頁按「產生 AI 解讀」才派工（views.ScanJobViewSet.ai_insight）
    return {
        "status": scan_job.status,
        "pages": len(ctx.crawled_pages),
        "findings": len(ctx.all_findings),
        "agent": ctx.agent_meta,
        "settlement_error": settlement_error,
    }


# 執行順序即此表順序；名稱會出現在失敗 log（[名稱:例外類別]）。
SCAN_PIPELINE: tuple[tuple[str, Callable[[ScanRunContext], None]], ...] = (
    ("target_validation", stage_validate_target),
    ("crawl", stage_crawl),
    ("enter_scanning", stage_enter_scanning),
    ("pagespeed_start", stage_pagespeed_start),
    ("fingerprint", stage_fingerprint),
    ("page_analysis", stage_analyze_pages),
    ("aeo_answers", stage_aeo_answerability),
    ("site_security", stage_site_security),
    ("active_probe", stage_active_probe),
    ("deep_security", stage_deep_security),
    ("zap_active", stage_zap_active),
    ("exposure", stage_exposure),
    ("geo_site", stage_geo_site),
    ("seo_links", stage_seo_links),
    ("pagespeed", stage_pagespeed),
    ("favicon", stage_favicon),
    ("agent", stage_agent),
    ("kali", stage_kali),
    ("site_profile", stage_site_profile),
    ("scoring", stage_scoring),
)


def _refund_or_raise(scan_job: ScanJob, *, reason: str, label: str) -> None:
    """終止分支的全額退款（冪等）；退款失敗要讓 task 失敗，才不會默默吞掉未退的點數。"""
    try:
        refund_full_for_scan(scan_job.user, scan_job, reason=reason)
    except Exception as exc:  # noqa: BLE001
        logger.exception("掃描子步驟失敗 scan_job_id=%s", scan_job.id)
        append_log(scan_job.id, f"{label}退款失敗：{exc.__class__.__name__}", level="error")
        raise RuntimeError(f"掃描{label}退款未完成。") from None


def finish_cancelled(scan_job: ScanJob) -> dict:
    append_log(scan_job.id, "掃描已被使用者終止", level="warn")
    ScanJob.objects.filter(id=scan_job.id).update(
        status=ScanJob.Status.CANCELLED,
        completed_at=timezone.now(),
        progress={},
        error_message="使用者已終止掃描",
    )
    _refund_or_raise(scan_job, reason="取消", label="取消")
    return {"status": "cancelled"}


def finish_timeout(scan_job: ScanJob) -> dict:
    soft_limit_min = settings.CELERY_TASK_SOFT_TIME_LIMIT // 60
    timeout_msg = f"掃描超時（超過 {soft_limit_min} 分鐘上限）"
    append_log(scan_job.id, timeout_msg, level="error")
    ScanJob.objects.filter(id=scan_job.id).update(
        status=ScanJob.Status.FAILED,
        completed_at=timezone.now(),
        progress={},
        error_message=timeout_msg,
    )
    _refund_or_raise(scan_job, reason="超時", label="超時")
    return {"status": "timeout"}


def finish_failed(scan_job: ScanJob, runtime_stage: str, exc: Exception) -> dict:
    """非預期例外：使用者剛好取消的走取消（狀態已是 cancelled）；否則標失敗並全額退款。"""
    if is_cancelled(scan_job.id):
        append_log(scan_job.id, "掃描已被使用者終止", level="warn")
        _refund_or_raise(scan_job, reason="取消", label="取消")
        return {"status": "cancelled"}
    append_log(
        scan_job.id,
        f"掃描執行失敗 [{runtime_stage}:{exc.__class__.__name__}]",
        level="error",
    )
    scan_job.status = ScanJob.Status.FAILED
    scan_job.error_message = "掃描執行失敗。"
    scan_job.completed_at = timezone.now()
    scan_job.progress = {}
    scan_job.save(
        update_fields=["status", "error_message", "completed_at", "progress", "updated_at"]
    )
    _refund_or_raise(scan_job, reason="失敗", label="失敗")
    raise RuntimeError("掃描執行失敗。") from None


def finish_unreachable(scan_job: ScanJob, message: str) -> dict:
    """沒有可分析的頁面：標失敗、顯示原因並全額退款（不是程式錯誤，不 raise）。"""
    if is_cancelled(scan_job.id):
        append_log(scan_job.id, "掃描已被使用者終止", level="warn")
        _refund_or_raise(scan_job, reason="取消", label="取消")
        return {"status": "cancelled"}
    append_log(scan_job.id, message, level="error")
    scan_job.status = ScanJob.Status.FAILED
    scan_job.error_message = message
    scan_job.completed_at = timezone.now()
    scan_job.progress = {}
    scan_job.save(
        update_fields=["status", "error_message", "completed_at", "progress", "updated_at"]
    )
    _refund_or_raise(scan_job, reason="失敗", label="失敗")
    return {"status": "failed", "reason": "no_usable_pages"}


@shared_task
def run_ai_insight_task(scan_job_id: int) -> None:
    """AI 掃描解讀（ai_insight.py）。不重試：每次都會花 token，失敗由使用者決定是否重新產生。"""
    from apps.scans.ai_insight import generate_ai_insight

    generate_ai_insight(scan_job_id)


@shared_task(bind=True)
def run_scan_job(self, scan_job_id: int) -> dict:
    ctx = start_scan_run(scan_job_id)
    if isinstance(ctx, dict):
        return ctx
    try:
        for stage_name, stage in SCAN_PIPELINE:
            ctx.runtime_stage = stage_name
            stage(ctx)
        return stage_settlement(ctx)
    except ScanCancelled:
        return finish_cancelled(ctx.scan_job)
    except SoftTimeLimitExceeded:
        return finish_timeout(ctx.scan_job)
    except ScanTargetUnreachable as exc:
        return finish_unreachable(ctx.scan_job, str(exc))
    except Exception as exc:
        return finish_failed(ctx.scan_job, ctx.runtime_stage, exc)
    finally:
        _discard_har(ctx)
