import asyncio
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from asgiref.sync import sync_to_async
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.services import refund_full_for_scan, settle_scan_actual
from apps.scans.cancellation import ScanCancelled, is_cancelled, raise_if_cancelled
from apps.scans.crawler import crawl_site
from apps.scans.katana_scanner import run_katana
from apps.scans.models import Finding, Page, ScanJob
from apps.scans.nuclei_scanner import run_nuclei
from apps.scans.scan_logger import append_log
from apps.scans.scan_plan import build_scan_execution_plan
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
from apps.scans.security.sri_scanner import analyze_sri
from apps.scans.security.ssl_scanner import analyze_ssl
from apps.scans.services import assert_public_http_url


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


def _write_progress(
    scan_job_id: int, *, phase: str, done: int, total: int, phase_started_at: str
) -> None:
    """寫 ScanJob.progress；用 filter().update() 避免覆蓋其他欄位且 race-safe。"""
    ScanJob.objects.filter(id=scan_job_id).update(
        progress={
            "pages_done": done,
            "pages_total": max(total, 1),  # 避免除以 0
            "phase": phase,
            "phase_started_at": phase_started_at,
        }
    )


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


@shared_task(bind=True)
def run_scan_job(self, scan_job_id: int) -> dict:
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
    scope_label = "單頁" if execution_plan.scope == "single" else "全網站"
    append_log(
        scan_job_id,
        "掃描任務啟動 — 目標："
        f"{redact_pii_in_text(redact_url_query_values(scan_job.normalized_url))}，"
        f"範圍：{scope_label}，模式：{scan_job.scan_mode}",
    )

    runtime_stage = "target_validation"
    try:
        assert_public_http_url(scan_job.normalized_url)
        # crawler callback：在 async loop 內透過 sync_to_async 寫 DB；
        # 同時是合作式 cancel 的檢查點，若已被使用者終止就 raise ScanCancelled
        async def _crawl_progress(done: int, total: int) -> None:
            await sync_to_async(_write_progress, thread_sensitive=True)(
                scan_job_id, phase="crawling", done=done, total=total,
                phase_started_at=crawl_phase_started,
            )
            cancelled = await sync_to_async(is_cancelled, thread_sensitive=True)(scan_job_id)
            if cancelled:
                raise ScanCancelled()

        append_log(
            scan_job_id,
            f"開始爬取，最大深度 {scan_job.max_depth}，最大頁數 {scan_job.max_pages}",
        )
        runtime_stage = "crawl"
        crawled_pages, warnings, site_signals = _run_async(
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
        warnings = redact_warning_summary(warnings)
        append_log(scan_job_id, f"爬取完成，共 {len(crawled_pages)} 頁")
        runtime_stage = "analysis"
        if warnings:
            for k, v in warnings.items():
                append_log(scan_job_id, f"爬取警告 [{k}]: {v}", level="warn")
        # 進入 scanning 前再檢查一次：避免使用者剛 cancel 就被 worker 覆蓋回 SCANNING
        raise_if_cancelled(scan_job_id)
        scan_phase_started = timezone.now().isoformat()
        scan_job.status = ScanJob.Status.SCANNING
        scan_job.warning_summary = warnings
        scan_job.progress = {
            "pages_done": 0,
            "pages_total": max(len(crawled_pages), 1),
            "phase": "scanning",
            "phase_started_at": scan_phase_started,
        }
        scan_job.save(update_fields=["status", "warning_summary", "progress", "updated_at"])
        append_log(scan_job_id, f"開始分析，共 {len(crawled_pages)} 頁待掃描")

        all_findings: list[dict] = []
        scanning_total = max(len(crawled_pages), 1)
        for scanned_idx, page_data in enumerate(crawled_pages, start=1):
            page = Page.objects.create(
                scan_job=scan_job,
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
            )
            # 被阻擋的頁面內容是錯誤頁，不進行四維掃描，僅保留紀錄與警告
            if not page_data["blocked_reason"]:
                page_findings = analyze_page(
                    PageAnalysisInput(
                        url=page.url,
                        final_url=page.final_url,
                        title=page.title,
                        html=page.html,
                        headers=page_data["headers"],
                        element_boxes=page_data["element_boxes"],
                        html_only=page_data["html_only"],
                    )
                )
                all_findings.extend(page_findings)
                for finding in page_findings:
                    Finding.objects.create(scan_job=scan_job, page=page, **finding)
                # Inline/HTML 硬編碼秘鑰偵測（被動：只分析已抓到的 HTML，不發額外請求）
                page_secrets = detect_secrets_in_text(page.html)
                secret_finding = build_secret_finding(
                    page_secrets, page.final_url or page.url, source="inline_html"
                )
                if secret_finding:
                    secret_finding = owasp_mapper.tag(secret_finding)
                    Finding.objects.create(scan_job=scan_job, page=page, **secret_finding)
                    all_findings.append(secret_finding)
            # 不論是否被阻擋，已處理一頁就更新 progress；同時當作 cancel 檢查點
            _write_progress(
                scan_job.id,
                phase="scanning",
                done=scanned_idx,
                total=scanning_total,
                phase_started_at=scan_phase_started,
            )
            blocked = (
                f"（阻擋：{page_data['blocked_reason']}）"
                if page_data["blocked_reason"]
                else ""
            )
            findings_count = len(page_findings) if not page_data["blocked_reason"] else 0
            append_log(
                scan_job_id,
                f"[{scanned_idx}/{scanning_total}] "
                f"{redact_pii_in_text(redact_url_query_values(page_data['url']))} "
                f"HTTP {page_data['status_code']} {blocked}→ {findings_count} 項問題",
            )
            raise_if_cancelled(scan_job_id)

        # HTTPS/HSTS/CSP/X-Frame-Options/X-Content-Type-Options 是伺服器設定，整站幾乎一致；
        # 對每頁各自呼叫 analyze_security() 只會得到同一組問題的多份複本，且會把 SECURITY
        # 分數依頁數不成比例地往下拖。改為對整批頁面只評估一次、page=None 的站台層級 finding。
        site_level_security_findings = analyze_security_site_level(crawled_pages)
        for finding in site_level_security_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(site_level_security_findings)
        if site_level_security_findings:
            append_log(
                scan_job_id,
                "站台層級安全檢查（HTTPS/HSTS/CSP 等）："
                f"{len(site_level_security_findings)} 項發現",
            )

        # Katana/Nuclei/Kali/深度被動掃描/exposure probe 這幾個階段合計常常耗時數十秒到數分鐘，
        # 但過去完全不寫 progress，使用者會看到進度條卡在「scanning 100%」不動、誤以為當機。
        # 沿用 phase="scanning"（progress 格式契約只允許 crawling/scanning/agent_testing 三值），
        # 用延伸的 done/total 讓進度條在這段期間持續往前走。
        deep_scan_total = scanning_total + 4

        # 主動工具必須同時遵守「單頁／全網站」範圍與 active 授權。
        # 被動模式不發 Nuclei/Katana 探針；單頁主動只讓 Nuclei 掃輸入頁，
        # 不啟動 Katana 整站探索。
        raise_if_cancelled(scan_job_id)
        # 收集已爬取的頁面 URL（排除被阻擋的頁面），整批餵給 Nuclei
        crawled_urls = [
            assert_public_http_url(p["url"])
            for p in crawled_pages
            if not p.get("blocked_reason")
        ]
        validated_target = assert_public_http_url(scan_job.normalized_url)
        katana_findings: list[dict] = []
        katana_tech: list[str] = []
        nuclei_findings: list[dict] = []

        if execution_plan.run_katana:
            append_log(
                scan_job_id,
                "全網站主動掃描：Katana 與 Nuclei 執行受控探測",
            )
            active_rps = max(int(settings.ARGUS_ACTIVE_MAX_RPS), 1)
            katana_rps = max(active_rps // 2, 1)
            nuclei_rps = max(active_rps - katana_rps, 1)

            if active_rps == 1:
                # 只有 1 RPS 預算時不可並行兩個最低各 1 RPS 的工具，否則總流量會翻倍。
                try:
                    katana_findings, katana_tech = run_katana(
                        validated_target,
                        scan_job.max_depth,
                        scan_job.max_pages,
                        rate_limit=1,
                        scan_job_id=scan_job_id,
                    )
                except ScanCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    append_log(
                        scan_job_id,
                        f"Katana 略過（{exc.__class__.__name__}）",
                        level="warn",
                    )
                raise_if_cancelled(scan_job_id)
                try:
                    nuclei_findings = run_nuclei(
                        validated_target,
                        scan_job_id,
                        deep=True,
                        extra_urls=crawled_urls,
                        rate_limit=1,
                    )
                except ScanCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    append_log(
                        scan_job_id,
                        f"Nuclei 略過（{exc.__class__.__name__}）",
                        level="warn",
                    )
            else:
                # 預算至少 2 RPS 才並行，兩個 process 的 RPS 合計不得超過總上限。
                with ThreadPoolExecutor(max_workers=2) as executor:
                    f_katana = executor.submit(
                        run_katana,
                        validated_target,
                        scan_job.max_depth,
                        scan_job.max_pages,
                        rate_limit=katana_rps,
                        scan_job_id=scan_job_id,
                    )
                    f_nuclei = executor.submit(
                        run_nuclei,
                        validated_target,
                        scan_job_id,
                        deep=True,
                        extra_urls=crawled_urls,
                        rate_limit=nuclei_rps,
                    )
                try:
                    katana_findings, katana_tech = f_katana.result()
                except ScanCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    append_log(
                        scan_job_id,
                        f"Katana 略過（{exc.__class__.__name__}）",
                        level="warn",
                    )
                try:
                    nuclei_findings = f_nuclei.result()
                except ScanCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    append_log(
                        scan_job_id,
                        f"Nuclei 略過（{exc.__class__.__name__}）",
                        level="warn",
                    )
        elif execution_plan.run_nuclei:
            append_log(
                scan_job_id,
                "單頁主動掃描：Nuclei 僅掃描輸入頁，略過 Katana 整站探索",
            )
            try:
                nuclei_findings = run_nuclei(
                    validated_target,
                    scan_job_id,
                    deep=True,
                    extra_urls=[],
                    rate_limit=settings.ARGUS_ACTIVE_MAX_RPS,
                )
            except ScanCancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                append_log(
                    scan_job_id,
                    f"Nuclei 略過（{exc.__class__.__name__}）",
                    level="warn",
                )
        else:
            append_log(
                scan_job_id,
                "被動模式：略過 Nuclei、Katana 與其他主動探測工具",
            )
        _write_progress(
            scan_job.id,
            phase="scanning",
            done=scanning_total + 1,
            total=deep_scan_total,
            phase_started_at=scan_phase_started,
        )

        # 若 Nuclei 無發現，且 Katana 偵測到已知 WAF / CDN，
        # 新增 info finding 向使用者說明探針遭攔截、保護機制有效
        if not nuclei_findings and katana_tech:
            _WAF_KEYWORDS = {"cloudflare", "fastly", "akamai", "aws waf", "imperva", "sucuri", "f5"}
            detected_wafs = [t for t in katana_tech if any(w in t.lower() for w in _WAF_KEYWORDS)]
            if detected_wafs:
                waf_names = "、".join(detected_wafs)
                scanned_count = len(crawled_urls) + 1  # entry URL + crawled
                nuclei_findings = [{
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
                        f"偵測技術棧：{', '.join(katana_tech)}；"
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
                append_log(
                    scan_job_id,
                    f"偵測到 WAF 保護（{waf_names}），Nuclei 探針可能被攔截，已新增說明 finding",
                )

        for finding in katana_findings + nuclei_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(katana_findings + nuclei_findings)

        # 舊版 Kali 主動驗證（security 掃描前）已移至本函式末段 agent 之後的
        # Hermes-first fallback；此處保留 scanning 進度回報，標示 Nuclei 階段結束、
        # 即將進入深度被動安全掃描（進度 step 編號維持不變）。
        _write_progress(
            scan_job.id,
            phase="scanning",
            done=scanning_total + 2,
            total=deep_scan_total,
            phase_started_at=scan_phase_started,
        )
        # === 深度被動安全掃描（security/ sub-package，純加法、silent-fail）===
        host = urlparse(scan_job.normalized_url).hostname or ""
        root_page = next((p for p in crawled_pages if p.get("headers")), None)
        root_headers = root_page["headers"] if root_page else {}
        root_url = (
            (root_page.get("final_url") or root_page.get("url"))
            if root_page else scan_job.normalized_url
        )
        deep_security_findings = (
            analyze_ssl(host, scan_job_id=scan_job.id)
            + analyze_cookies(root_headers, root_url)
            + analyze_headers(crawled_pages)
            + analyze_sri(crawled_pages)
            + analyze_dns(host)
            + analyze_js_libraries(crawled_pages)
        )
        deep_security_findings = [owasp_mapper.tag(f) for f in deep_security_findings]
        for finding in deep_security_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(deep_security_findings)
        owasp_mapper.backfill(scan_job)
        append_log(
            scan_job_id,
            f"深度被動安全掃描完成：{len(deep_security_findings)} 項發現",
        )
        _write_progress(
            scan_job.id,
            phase="scanning",
            done=scanning_total + 3,
            total=deep_scan_total,
            phase_started_at=scan_phase_started,
        )

        # === robots.txt 敏感路徑洩露（被動，任何模式都產出）===
        robots_disclosure = exposure_scanner.analyze_robots_disclosure(
            site_signals.get("robots_disallow") or []
        )
        for finding in robots_disclosure:
            tagged = owasp_mapper.tag(finding)
            Finding.objects.create(scan_job=scan_job, page=None, **tagged)
        all_findings.extend(robots_disclosure)

        # === 敏感檔案外洩主動探測（僅全網站 active+authorized）===
        if execution_plan.run_exposure:
            raise_if_cancelled(scan_job_id)
            append_log(scan_job_id, "敏感檔案外洩探測開始（主動內容探測，繞連結直接探隱藏檔）")
            try:
                probe_results = _run_async(
                    lambda: exposure_scanner.probe_paths(
                        scan_job.normalized_url,
                        scan_job.origin,
                        scan_job_id,
                        robots_disallow=site_signals.get("robots_disallow") or [],
                    )
                )
                exposure_findings = [
                    owasp_mapper.tag(f)
                    for f in exposure_scanner.analyze_probe_results(probe_results)
                ]
                for finding in exposure_findings:
                    Finding.objects.create(scan_job=scan_job, page=None, **finding)
                all_findings.extend(exposure_findings)
                append_log(
                    scan_job_id,
                    f"敏感檔案外洩探測完成：探測 {len(probe_results)} 路徑，"
                    f"發現 {len(exposure_findings)} 項外洩",
                )
            except ScanCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 — 探測失敗不影響主掃描
                append_log(
                    scan_job_id,
                    f"敏感檔案外洩探測略過（{exc.__class__.__name__}）",
                    level="warn",
                )
        elif execution_plan.active_authorized:
            append_log(
                scan_job_id,
                "單頁範圍：略過整站敏感檔案路徑探測",
            )

        if katana_tech:
            updated_warnings = dict(scan_job.warning_summary or {})
            updated_warnings["tech_stack"] = katana_tech
            scan_job.warning_summary = updated_warnings
            scan_job.save(update_fields=["warning_summary", "updated_at"])
        _write_progress(
            scan_job.id,
            phase="scanning",
            done=deep_scan_total,
            total=deep_scan_total,
            phase_started_at=scan_phase_started,
        )

        append_log(
            scan_job_id,
            f"資安補充掃描完成：Katana {len(katana_findings)} 項，"
            f"Nuclei {len(nuclei_findings)} 項"
            + (f"，技術棧：{', '.join(katana_tech)}" if katana_tech else ""),
        )

        # 站台層級的 GEO FAST 檢查（llms.txt、AI 爬蟲可存取性）
        site_findings = analyze_site_signals(site_signals)
        for finding in site_findings:
            Finding.objects.create(scan_job=scan_job, page=None, **finding)
        all_findings.extend(site_findings)
        append_log(scan_job_id, f"站台訊號分析完成：{len(site_findings)} 項發現")

        # Phase 2：可選的 Hermes-Agent 動態 UX 測試
        # 預設 ARGUS_AGENT_ENABLED=False；只在使用者明確啟用時才跑，避免每次掃描都消耗 LLM token。
        # Task 6：Agent 在 Kali fallback 之前執行；agent 確認的 security finding 餵進 scoring。
        agent_meta = {}
        agent_result = None
        if settings.ARGUS_AGENT_ENABLED and execution_plan.run_agent:
            raise_if_cancelled(scan_job_id)
            agent_phase_started = timezone.now().isoformat()
            scan_job.status = ScanJob.Status.AGENT_TESTING
            scan_job.progress = {
                "pages_done": 0,
                "pages_total": settings.ARGUS_AGENT_MAX_STEPS,
                "phase": "agent_testing",
                "phase_started_at": agent_phase_started,
            }
            scan_job.save(update_fields=["status", "progress", "updated_at"])
            try:
                from apps.agent.runner import run_agent_for_scan

                agent_result = _run_async(lambda: run_agent_for_scan(scan_job))
                if agent_result:
                    agent_meta = {
                        "status": agent_result.status,
                        "steps": agent_result.steps,
                        "tokens": agent_result.total_tokens,
                        "issues_reported": len(agent_result.issues),
                        "error": agent_result.error,
                    }
                    _write_progress(
                        scan_job.id,
                        phase="agent_testing",
                        done=agent_result.steps,
                        total=settings.ARGUS_AGENT_MAX_STEPS,
                        phase_started_at=agent_phase_started,
                    )
                    for issue in agent_result.issues:
                        all_findings.append(
                            {
                                "category": "ux",
                                "severity": issue.get("severity", "low"),
                                "title": issue.get("title", ""),
                                # 與 apps/agent/findings.py::persist_agent_issues 寫入 DB 時
                                # 用的 default_priority 對齊，否則這裡沒帶 priority_score
                                # 會讓 agent 回報的 critical/high UX 問題在 top_actions 排序
                                # 時輸給 priority_score 15~40 的瑣碎 SEO 項目。
                                "priority_score": 50.0,
                            }
                        )
            except Exception as exc:  # noqa: BLE001 — agent 失敗不應讓整個掃描失敗
                agent_meta = {"status": "error", "error": exc.__class__.__name__}
        elif settings.ARGUS_AGENT_ENABLED:
            append_log(
                scan_job_id,
                "Agent 略過：僅全網站且已授權的主動掃描可執行",
            )

        # Task 6：Agent 確認的 security finding 餵進 scoring（DB 落地由 runner 負責）
        if agent_result:
            all_findings.extend(agent_result.security_findings)

        # === Kali 主動驗證 fallback（agent 之後、scoring 之前）===
        # 僅 active + authorized 才嘗試；ARGUS_KALI_ENABLED 等其餘 gating
        # 由 validate_findings_with_kali → run_sqlmap 的三重鎖負責，預設完全 inert。
        # Redis fingerprints 讓 fallback 只處理 agent 沒驗證過的獨特 target（一次 batch）。
        # ScanCancelled 必須原樣重拋，讓合作式取消傳遞到 cancelled/refund 分支。
        if execution_plan.run_kali:
            raise_if_cancelled(scan_job_id)
            try:
                kali_findings = validate_findings_with_kali(scan_job_id, crawled_urls)
            except ScanCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 — 非 cancel 的基礎設施失敗只 silent-fail
                append_log(
                    scan_job_id,
                    f"Kali 主動驗證略過（{exc.__class__.__name__}）",
                    level="warn",
                )
                kali_findings = []
            for finding in kali_findings:
                Finding.objects.create(scan_job=scan_job, page=None, **finding)
            all_findings.extend(kali_findings)
            if kali_findings:
                append_log(
                    scan_job_id,
                    f"Kali 主動驗證確認 {len(kali_findings)} 項可利用漏洞",
                )

        # UX 只有 Hermes-Agent 實際「跑完」才算「有測」；未啟用時 agent_meta 為空 dict
        # （falsy），跑完/出錯時都會有值。但單純「有值」不夠精準：agent 拋例外時
        # agent_meta 也會是 {"status": "error", ...}（仍是 truthy），此時 UX 根本沒被
        # 真正測過，category_scores["ux"] 只是恰好維持在 100（因為沒有 UX finding），
        # 若也算「有測」計入平均，等於把「測到一半就掛掉」誤當「測過了、乾淨」。
        # 頁面內容類分類（seo/aeo）只來自 analyze_page（頁面層級）；爬蟲 0 頁（目標不可
        # 達/全 timeout）時根本沒有頁面可分析，若仍計入 overall_score 平均，等於把「沒
        # 測」誤當「零問題」灌高總分（與上方 UX 的把關同理）。security（DNS/SSL 站台
        # 層級）與 geo（analyze_site_signals：llms.txt/robots）即使 0 頁仍有站台層級
        # 檢查，故保留。正常掃描（有頁）行為與舊版完全一致。
        tested_categories = {"security", "geo"}
        if crawled_pages:
            tested_categories.update({"seo", "aeo"})
        if agent_meta and agent_meta.get("status") != "error":
            tested_categories.add("ux")
        # 0 頁是「掃描實質失效」的強信號：在 warning_summary 標記 + scan_log 警告，
        # 避免 overall_score（此時只反映站台層級）被誤讀為「網站安全」。
        if not crawled_pages:
            _eff_warnings = dict(scan_job.warning_summary or {})
            _eff_warnings["scan_effectiveness"] = "no_pages_crawled"
            scan_job.warning_summary = _eff_warnings
            append_log(
                scan_job_id,
                "掃描有效性警示：未抓到任何頁面（目標可能不可達或全 timeout）；"
                "SEO/AEO 未評估，總分僅反映站台層級檢查，不應解讀為網站安全。",
                level="warn",
            )
        overall_score, category_scores, top_actions = calculate_scores(
            all_findings, tested_categories=tested_categories
        )
        append_log(
            scan_job_id,
            f"掃描完成 — 總分 {overall_score}，共 {len(all_findings)} 項發現",
        )
        scan_job.overall_score = overall_score
        scan_job.category_scores = category_scores
        scan_job.top_actions = top_actions
        if agent_meta:
            warning_summary = dict(scan_job.warning_summary or {})
            warning_summary["agent"] = agent_meta
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
        # 點數結算：依實際爬到的頁數退回未使用的 coin（max_pages - actual_pages）× 單價
        try:
            settle_scan_actual(scan_job.user, scan_job, len(crawled_pages))
        except Exception as exc:  # noqa: BLE001
            append_log(scan_job_id, f"點數結算失敗：{exc.__class__.__name__}", level="error")
            raise
        return {
            "status": scan_job.status,
            "pages": len(crawled_pages),
            "findings": len(all_findings),
            "agent": agent_meta,
        }
    except ScanCancelled:
        append_log(scan_job_id, "掃描已被使用者終止", level="warn")
        ScanJob.objects.filter(id=scan_job_id).update(
            status=ScanJob.Status.CANCELLED,
            completed_at=timezone.now(),
            progress={},
            error_message="使用者已終止掃描",
        )
        try:
            refund_full_for_scan(scan_job.user, scan_job, reason="取消")
        except Exception as exc:  # noqa: BLE001
            append_log(scan_job_id, f"取消退款失敗：{exc.__class__.__name__}", level="error")
            raise RuntimeError("掃描取消退款未完成。") from None
        return {"status": "cancelled"}
    except SoftTimeLimitExceeded:
        soft_limit_min = settings.CELERY_TASK_SOFT_TIME_LIMIT // 60
        timeout_msg = f"掃描超時（超過 {soft_limit_min} 分鐘上限）"
        append_log(scan_job_id, timeout_msg, level="error")
        ScanJob.objects.filter(id=scan_job_id).update(
            status=ScanJob.Status.FAILED,
            completed_at=timezone.now(),
            progress={},
            error_message=timeout_msg,
        )
        try:
            refund_full_for_scan(scan_job.user, scan_job, reason="超時")
        except Exception as exc:  # noqa: BLE001
            append_log(scan_job_id, f"超時退款失敗：{exc.__class__.__name__}", level="error")
            raise RuntimeError("掃描超時退款未完成。") from None
        return {"status": "timeout"}
    except Exception as exc:
        if is_cancelled(scan_job_id):
            append_log(scan_job_id, "掃描已被使用者終止", level="warn")
            try:
                refund_full_for_scan(scan_job.user, scan_job, reason="取消")
            except Exception as refund_exc:  # noqa: BLE001
                append_log(
                    scan_job_id,
                    f"取消退款失敗：{refund_exc.__class__.__name__}",
                    level="error",
                )
                raise RuntimeError("掃描取消退款未完成。") from None
            return {"status": "cancelled"}
        append_log(
            scan_job_id,
            f"掃描執行失敗 [{runtime_stage}:{exc.__class__.__name__}]",
            level="error",
        )
        scan_job.status = ScanJob.Status.FAILED
        scan_job.error_message = "掃描執行失敗。"
        scan_job.completed_at = timezone.now()
        scan_job.progress = {}
        scan_job.save(
            update_fields=[
                "status", "error_message", "completed_at", "progress", "updated_at",
            ]
        )
        # 失敗時全額退回預扣的 coin
        try:
            refund_full_for_scan(scan_job.user, scan_job, reason="失敗")
        except Exception as refund_exc:  # noqa: BLE001
            append_log(
                scan_job_id,
                f"失敗退款失敗：{refund_exc.__class__.__name__}",
                level="error",
            )
            raise RuntimeError("掃描失敗退款未完成。") from None
        raise RuntimeError("掃描執行失敗。") from None
