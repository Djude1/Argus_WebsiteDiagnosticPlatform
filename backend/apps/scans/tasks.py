import asyncio
import logging
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
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
from apps.scans.crawler import crawl_site
from apps.scans.katana_scanner import run_katana
from apps.scans.models import Finding, Page, ScanJob
from apps.scans.nuclei_scanner import run_nuclei
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
from apps.scans.security.cookie_scanner import analyze_cookies
from apps.scans.security.dns_scanner import analyze_dns
from apps.scans.security.header_scanner import analyze_headers
from apps.scans.security.js_library_scanner import analyze_js_libraries
from apps.scans.security.kali_tools import validate_findings_with_kali
from apps.scans.security.redaction import (
    redact_pii_in_text,
    redact_url_query_values,
    redact_warning_summary,
)
from apps.scans.security.secret_scanner import build_secret_finding, detect_secrets_in_text
from apps.scans.security.service_cve_scanner import analyze_services
from apps.scans.security.sri_scanner import analyze_sri
from apps.scans.security.ssl_scanner import analyze_ssl
from apps.scans.security.waf_scanner import detect_waf_block
from apps.scans.services import assert_public_http_url

logger = logging.getLogger(__name__)

# Nuclei extra_urls 中帶參數 API 端點的上限：模板掃描對 API 端點命中率低，
# 全塞只會把 1 RPS 的時間預算炸掉（#23 實測 12 URL × 全模板掃掛死）
_NUCLEI_MAX_ENDPOINT_URLS = 3


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
    if execution_plan.run_exposure:
        steps.append("exposure_probe")
    if "geo" in cats:
        steps.append("geo_site")
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


@dataclass
class ScanRunContext:
    """一次掃描執行期間，各階段共用的狀態與中間產物。"""

    scan_job: ScanJob
    execution_plan: ScanExecutionPlan
    steps: list[str]
    crawl_phase_started: str
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
    # AEO 可回答性檢測（aeo/evaluate.py 的 AeoEvaluation）
    aeo_evaluation: object | None = None
    # Agent 階段
    agent_meta: dict = field(default_factory=dict)
    agent_result: object | None = None
    # 目前執行到哪一段（失敗時寫進 log）
    runtime_stage: str = "target_validation"

    @property
    def scan_job_id(self) -> int:
        return self.scan_job.id

    @property
    def deep_scan_total(self) -> int:
        """分析之後的資安補充階段用延伸的 done/total，讓進度條持續往前走。"""
        return self.scanning_total + 4

    def record(self, findings: list[dict], *, page: Page | None = None) -> None:
        """寫入 Finding 並納入計分清單。"""
        for finding in findings:
            Finding.objects.create(scan_job=self.scan_job, page=page, **finding)
        self.all_findings.extend(findings)

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
        )
    )
    ctx.crawled_pages = crawled_pages
    ctx.warnings = redact_warning_summary(warnings)
    ctx.site_signals = site_signals
    ctx.discovered_endpoints = discovered_endpoints
    append_log(scan_job_id, f"爬取完成，共 {len(crawled_pages)} 頁")
    if discovered_endpoints:
        append_log(
            scan_job_id,
            f"爬取期間觀察到 {len(discovered_endpoints)} 個 same-origin API 端點"
            "（XHR/fetch 被動攔截，供主動工具作為攻擊面輸入）",
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


def stage_enter_scanning(ctx: ScanRunContext) -> None:
    """爬取 → 分析的狀態轉換：記錄警告、推進到 scanning、落地頁面。"""
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    if ctx.warnings:
        for k, v in ctx.warnings.items():
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
        ),
        categories={category},
    )
    # Inline/HTML 硬編碼秘鑰偵測（被動：只分析已抓到的 HTML，不發額外請求）
    if category == "security":
        secret_finding = build_secret_finding(
            detect_secrets_in_text(page.html),
            page.final_url or page.url,
            source="inline_html",
        )
        if secret_finding:
            page_findings.append(owasp_mapper.tag(secret_finding))
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
                ctx.record(page_findings, page=page)
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
    ctx.record(evaluation.findings)
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
    ctx.record(findings)
    if findings:
        append_log(
            ctx.scan_job_id,
            f"站台層級安全檢查（HTTPS/HSTS/CSP 等）：{len(findings)} 項發現",
        )


def _collect_probe_targets(ctx: ScanRunContext) -> list[str]:
    """整理主動工具的目標：已爬頁面（排除被擋）＋爬取期間被動攔截的 same-origin 端點。

    回傳 Nuclei 的 URL 清單；sqlmap 候選（頁面＋全部端點）留在 ctx 供 Kali 階段使用。
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
    # Nuclei 只吃頁面 URL＋前幾個帶參數端點——模板掃描對 API 端點命中率低，
    # 全塞只會把 1 RPS 的時間預算炸掉（#23 實測 12 URL × 全模板掛死）
    return ctx.page_urls + [
        u for u in ctx.endpoint_urls if "?" in u
    ][:_NUCLEI_MAX_ENDPOINT_URLS]


def _log_tool_skipped(scan_job_id: int, tool: str, exc: Exception) -> None:
    logger.exception("掃描子步驟失敗 scan_job_id=%s", scan_job_id)
    append_log(scan_job_id, f"{tool} 略過（{exc.__class__.__name__}）", level="warn")


def _run_site_active_tools(ctx: ScanRunContext, target: str, nuclei_urls: list[str]) -> None:
    """全網站主動掃描：Katana 與 Nuclei 共享 ARGUS_ACTIVE_MAX_RPS 預算。"""
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    append_log(scan_job_id, "全網站主動掃描：Katana 與 Nuclei 執行受控探測")
    active_rps = max(int(settings.ARGUS_ACTIVE_MAX_RPS), 1)
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
        except ScanCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            _log_tool_skipped(scan_job_id, "Katana", exc)
        raise_if_cancelled(scan_job_id)
        try:
            ctx.nuclei_findings = run_nuclei(
                target,
                scan_job_id,
                deep=True,
                extra_urls=nuclei_urls,
                rate_limit=1,
            )
        except ScanCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            _log_tool_skipped(scan_job_id, "Nuclei", exc)
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
        f_nuclei = executor.submit(
            run_nuclei,
            target,
            scan_job_id,
            deep=True,
            extra_urls=nuclei_urls,
            rate_limit=nuclei_rps,
        )
    try:
        ctx.katana_findings, ctx.katana_tech = f_katana.result()
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        _log_tool_skipped(scan_job_id, "Katana", exc)
    try:
        ctx.nuclei_findings = f_nuclei.result()
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        _log_tool_skipped(scan_job_id, "Nuclei", exc)


def _run_single_page_nuclei(ctx: ScanRunContext, target: str) -> None:
    """單頁主動掃描：Nuclei 只掃輸入頁，不啟動 Katana 整站探索。"""
    append_log(ctx.scan_job_id, "單頁主動掃描：Nuclei 僅掃描輸入頁，略過 Katana 整站探索")
    try:
        ctx.nuclei_findings = run_nuclei(
            target,
            ctx.scan_job_id,
            deep=True,
            extra_urls=[],
            rate_limit=settings.ARGUS_ACTIVE_MAX_RPS,
        )
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        _log_tool_skipped(ctx.scan_job_id, "Nuclei", exc)


_WAF_KEYWORDS = {"cloudflare", "fastly", "akamai", "aws waf", "imperva", "sucuri", "f5"}


def _waf_blocked_nuclei_note(ctx: ScanRunContext) -> list[dict]:
    """Nuclei 無發現且 Katana 偵測到已知 WAF／CDN 時，補一筆 info 說明探針可能被攔截。"""
    if ctx.nuclei_findings or not ctx.katana_tech:
        return []
    detected_wafs = [
        t for t in ctx.katana_tech if any(w in t.lower() for w in _WAF_KEYWORDS)
    ]
    if not detected_wafs:
        return []
    waf_names = "、".join(detected_wafs)
    scanned_count = len(ctx.page_urls) + 1  # entry URL + crawled
    append_log(
        ctx.scan_job_id,
        f"偵測到 WAF 保護（{waf_names}），Nuclei 探針可能被攔截，已新增說明 finding",
    )
    return [{
        "category": "security",
        "severity": "info",
        "title": f"Nuclei 資安掃描受 WAF / CDN 保護攔截（{waf_names}）",
        "description": (
            f"偵測到 {waf_names} 等 WAF / CDN 保護機制，"
            f"Nuclei 對 {scanned_count} 個頁面發出的主動探針請求可能被攔截，"
            "導致掃描回傳 0 項發現。"
            "這表示您的網站已部署有效的入侵防護，屬正向安全指標。"
        ),
        "remediation": (
            "此為資訊性提示，無需修復。"
            "如需完整弱點掃描，建議在 WAF 規則中加入可信掃描來源 IP 的例外，"
            "或在 staging 環境（無 WAF）執行深度資安稽核。"
        ),
        "evidence": (
            f"偵測技術棧：{', '.join(ctx.katana_tech)}；"
            f"Nuclei 掃描 {scanned_count} 個 URL，回傳 0 項發現"
        ),
        "selector": "",
        "bounding_box": None,
        "impact_area": "vulnerability",
        "confidence": 0.9,
        "priority_score": 10.0,
        "ai_handoff_prompt": (
            f"網站部署了 {waf_names} WAF / CDN 保護，Nuclei 資安探針被攔截。"
            "這是良好的安全措施。建議定期在授權環境下進行深度內部安全掃描。"
        ),
    }]


def stage_active_probe(ctx: ScanRunContext) -> None:
    """主動探測（Nuclei／Katana），同時遵守「單頁／全網站」範圍與 active 授權。

    被動模式不發任何探針；單頁主動只讓 Nuclei 掃輸入頁。
    """
    plan = ctx.execution_plan
    raise_if_cancelled(ctx.scan_job_id)
    nuclei_urls = _collect_probe_targets(ctx)
    target = assert_public_http_url(ctx.scan_job.normalized_url)

    if plan.run_nuclei:
        ctx.scanning_progress(ctx.scanning_total, "active_probe")
    if plan.run_katana:
        _run_site_active_tools(ctx, target, nuclei_urls)
    elif plan.run_nuclei:
        _run_single_page_nuclei(ctx, target)
    else:
        append_log(ctx.scan_job_id, "被動模式：略過 Nuclei、Katana 與其他主動探測工具")
    ctx.scanning_progress(ctx.scanning_total + 1, "deep_security")

    waf_note = _waf_blocked_nuclei_note(ctx)
    if waf_note:
        ctx.nuclei_findings = waf_note
    ctx.record(ctx.katana_findings + ctx.nuclei_findings)
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
    )
    # WAF／防護機制封鎖偵測（被動：統計已落地 Page 的 403/429 與 challenge 特徵，
    # 達閾值才產出單一 info finding，未達閾值回 None 不打擾使用者）
    waf_block_finding = detect_waf_block(scan_job)
    if waf_block_finding:
        findings.append(waf_block_finding)
        append_log(ctx.scan_job_id, "偵測到 WAF／防護機制封鎖跡象，已新增說明 finding")
    findings = [owasp_mapper.tag(f) for f in findings]
    ctx.record(findings)
    owasp_mapper.backfill(scan_job)
    append_log(ctx.scan_job_id, f"深度被動安全掃描完成：{len(findings)} 項發現")
    ctx.scanning_progress(
        ctx.scanning_total + 3,
        _first_step(ctx.steps, "exposure_probe", "geo_site", "agent", "scoring"),
    )


def stage_exposure(ctx: ScanRunContext) -> None:
    """敏感資訊外洩：robots.txt 敏感路徑（被動，任何模式）＋敏感檔案主動探測（全網站 active）。"""
    scan_job = ctx.scan_job
    scan_job_id = ctx.scan_job_id
    robots_disallow = ctx.site_signals.get("robots_disallow") or []
    ctx.record([
        owasp_mapper.tag(f)
        for f in exposure_scanner.analyze_robots_disclosure(robots_disallow)
    ])

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
                )
            )
            exposure_findings = [
                owasp_mapper.tag(f)
                for f in exposure_scanner.analyze_probe_results(probe_results)
            ]
            ctx.record(exposure_findings)
            append_log(
                scan_job_id,
                f"敏感檔案外洩探測完成：探測 {len(probe_results)} 路徑，"
                f"發現 {len(exposure_findings)} 項外洩",
            )
        except ScanCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 — 探測失敗不影響主掃描
            logger.exception("掃描子步驟失敗 scan_job_id=%s", scan_job_id)
            append_log(
                scan_job_id,
                f"敏感檔案外洩探測略過（{exc.__class__.__name__}）",
                level="warn",
            )
    elif ctx.execution_plan.active_authorized:
        append_log(scan_job_id, "單頁範圍：略過整站敏感檔案路徑探測")

    if ctx.katana_tech:
        updated_warnings = dict(scan_job.warning_summary or {})
        updated_warnings["tech_stack"] = ctx.katana_tech
        scan_job.warning_summary = updated_warnings
        scan_job.save(update_fields=["warning_summary", "updated_at"])
    ctx.scanning_progress(
        ctx.deep_scan_total, _first_step(ctx.steps, "geo_site", "agent", "scoring")
    )
    append_log(
        scan_job_id,
        f"資安補充掃描完成：Katana {len(ctx.katana_findings)} 項，"
        f"Nuclei {len(ctx.nuclei_findings)} 項"
        + (f"，技術棧：{', '.join(ctx.katana_tech)}" if ctx.katana_tech else ""),
    )


def stage_geo_site(ctx: ScanRunContext) -> None:
    """站台層級 GEO 檢查（llms.txt、AI 爬蟲可存取性）；未勾 GEO 維度時跳過。"""
    if "geo" not in ctx.scan_job.effective_categories:
        return
    findings = analyze_site_signals(ctx.site_signals)
    ctx.record(findings)
    append_log(ctx.scan_job_id, f"站台訊號分析完成：{len(findings)} 項發現")


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
    agent_phase_started = timezone.now().isoformat()
    scan_job.status = ScanJob.Status.AGENT_TESTING
    scan_job.progress = {
        "pages_done": 0,
        "pages_total": settings.ARGUS_AGENT_MAX_STEPS,
        "phase": "agent_testing",
        "phase_started_at": agent_phase_started,
        "step": "agent",
        "step_done": 0,
        "step_total": settings.ARGUS_AGENT_MAX_STEPS,
        "step_started_at": agent_phase_started,
        "steps": ctx.steps,
    }
    scan_job.save(update_fields=["status", "progress", "updated_at"])
    try:
        from apps.agent.runner import run_agent_for_scan

        agent_result = _run_async(
            lambda: run_agent_for_scan(
                scan_job,
                recon_intel=ctx.discovered_endpoints,
                may_submit_forms=may_submit_forms,
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
                done=agent_result.steps,
                total=settings.ARGUS_AGENT_MAX_STEPS,
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
    except ScanCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 — 非 cancel 的基礎設施失敗只 silent-fail
        logger.exception("掃描子步驟失敗 scan_job_id=%s", scan_job_id)
        append_log(
            scan_job_id,
            f"Kali 主動驗證略過（{exc.__class__.__name__}）",
            level="warn",
        )
        kali_findings = []
    ctx.record(kali_findings)
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
    return tested & ctx.scan_job.effective_categories


def base_scores_for(ctx: ScanRunContext) -> dict[str, int]:
    """分類基準分：AEO 以可回答性分數為基準（見 scanners.calculate_scores）。"""
    evaluation = ctx.aeo_evaluation
    if evaluation is not None and evaluation.status == "evaluated":
        return {"aeo": evaluation.score}
    return {}


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
        settle_scan_actual(scan_job.user, scan_job, len(ctx.crawled_pages))
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
    ("page_analysis", stage_analyze_pages),
    ("aeo_answers", stage_aeo_answerability),
    ("site_security", stage_site_security),
    ("active_probe", stage_active_probe),
    ("deep_security", stage_deep_security),
    ("exposure", stage_exposure),
    ("geo_site", stage_geo_site),
    ("agent", stage_agent),
    ("kali", stage_kali),
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
    except Exception as exc:
        return finish_failed(ctx.scan_job, ctx.runtime_stage, exc)
