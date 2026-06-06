import asyncio
from concurrent.futures import ThreadPoolExecutor

from asgiref.sync import sync_to_async
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.billing.services import refund_full_for_scan, settle_scan_actual
from apps.scans.cancellation import ScanCancelled, is_cancelled, raise_if_cancelled
from apps.scans.crawler import crawl_site
from apps.scans.katana_scanner import run_katana
from apps.scans.models import Finding, Page, ScanJob
from apps.scans.nuclei_scanner import run_nuclei
from apps.scans.scan_logger import append_log
from apps.scans.scanners import (
    PageAnalysisInput,
    analyze_page,
    analyze_site_signals,
    calculate_scores,
)


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


@shared_task(bind=True)
def run_scan_job(self, scan_job_id: int) -> dict:
    scan_job = ScanJob.objects.get(id=scan_job_id)
    now = timezone.now()
    crawl_phase_started = now.isoformat()
    scan_job.status = ScanJob.Status.CRAWLING
    scan_job.started_at = now
    scan_job.scan_log = []  # 每次重新開始清空舊 log
    scan_job.progress = {
        "pages_done": 0,
        "pages_total": 1,
        "phase": "crawling",
        "phase_started_at": crawl_phase_started,
    }
    scan_job.save(update_fields=["status", "started_at", "scan_log", "progress", "updated_at"])
    append_log(
        scan_job_id,
        f"掃描任務啟動 — 目標：{scan_job.normalized_url}，模式：{scan_job.scan_mode}",
    )

    try:
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
        crawled_pages, warnings, site_signals = asyncio.run(
            crawl_site(
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
        append_log(scan_job_id, f"爬取完成，共 {len(crawled_pages)} 頁")
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
                f"[{scanned_idx}/{scanning_total}] {page_data['url']} "
                f"HTTP {page_data['status_code']} {blocked}→ {findings_count} 項問題",
            )
            raise_if_cancelled(scan_job_id)

        # 並行執行 Katana（JS 秘鑰 / 技術棧）+ Nuclei（資安掃描）
        raise_if_cancelled(scan_job_id)
        deep_mode = (
            scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and scan_job.active_testing_authorized
        )
        append_log(
            scan_job_id,
            "資安補充掃描開始 — Katana（JS 秘鑰 / 技術棧）並行 Nuclei"
            f"（{'深度付費' if deep_mode else '快速免費'}）",
        )
        # 收集已爬取的頁面 URL（排除被阻擋的頁面），整批餵給 Nuclei
        crawled_urls = [
            p["url"] for p in crawled_pages if not p.get("blocked_reason")
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_katana = executor.submit(
                run_katana,
                scan_job.normalized_url,
                scan_job.max_depth,
                scan_job.max_pages,
            )
            f_nuclei = executor.submit(
                run_nuclei,
                scan_job.normalized_url,
                scan_job_id,
                deep=deep_mode,
                extra_urls=crawled_urls,
            )
        try:
            katana_findings, katana_tech = f_katana.result()
        except Exception as exc:  # noqa: BLE001
            append_log(scan_job_id, f"Katana 略過（{exc.__class__.__name__}）", level="warn")
            katana_findings, katana_tech = [], []
        try:
            nuclei_findings = f_nuclei.result()
        except Exception as exc:  # noqa: BLE001
            append_log(scan_job_id, f"Nuclei 略過（{exc.__class__.__name__}）", level="warn")
            nuclei_findings = []

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

        if katana_tech:
            updated_warnings = dict(scan_job.warning_summary or {})
            updated_warnings["tech_stack"] = katana_tech
            scan_job.warning_summary = updated_warnings
            scan_job.save(update_fields=["warning_summary", "updated_at"])

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
        agent_meta = {}
        if settings.ARGUS_AGENT_ENABLED:
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

                agent_result = asyncio.run(run_agent_for_scan(scan_job))
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
                            }
                        )
            except Exception as exc:  # noqa: BLE001 — agent 失敗不應讓整個掃描失敗
                agent_meta = {"status": "error", "error": exc.__class__.__name__}

        overall_score, category_scores, top_actions = calculate_scores(all_findings)
        append_log(
            scan_job_id,
            f"掃描完成 — 總分 {overall_score}，共 {len(all_findings)} 項發現",
        )
        scan_job.status = ScanJob.Status.COMPLETED
        scan_job.overall_score = overall_score
        scan_job.category_scores = category_scores
        scan_job.top_actions = top_actions
        if agent_meta:
            warning_summary = dict(scan_job.warning_summary or {})
            warning_summary["agent"] = agent_meta
            scan_job.warning_summary = warning_summary
        scan_job.progress = {}  # 完成後清空，前端不再顯示進行中動畫
        scan_job.completed_at = timezone.now()
        scan_job.save(
            update_fields=[
                "status",
                "overall_score",
                "category_scores",
                "top_actions",
                "warning_summary",
                "progress",
                "completed_at",
                "updated_at",
            ]
        )
        # 點數結算：依實際爬到的頁數退回未使用的 coin（max_pages - actual_pages）× 單價
        try:
            settle_scan_actual(scan_job.user, scan_job, len(crawled_pages))
        except Exception:  # noqa: BLE001 — 退款失敗不應讓掃描結果消失，僅紀錄
            pass
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
        except Exception:  # noqa: BLE001
            pass
        return {"status": "cancelled"}
    except Exception as exc:
        detail = str(exc).strip()[:500]
        class_name = exc.__class__.__name__
        append_log(
            scan_job_id,
            f"掃描失敗：{class_name}: {detail}" if detail else f"掃描失敗：{class_name}",
            level="error",
        )
        scan_job.status = ScanJob.Status.FAILED
        scan_job.error_message = f"{class_name}: {detail}" if detail else class_name
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
        except Exception:  # noqa: BLE001
            pass
        raise
