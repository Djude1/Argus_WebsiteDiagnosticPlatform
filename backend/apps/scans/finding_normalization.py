"""把既有掃描的發現套用目前的判定規則並重新計分（不重新爬取、不對目標發任何請求）。

2026-09-28 報告審查後，幾條規則的判定改了，但已完成的掃描仍保留舊結果：
- PII：舊版看到任何個資一律高風險；現在依資料種類與脈絡分級（本網域 Email 只是資訊提示）。
  以資料庫裡保存的頁面 HTML 重跑同一支 analyze_data_exposure()，結果與新掃描一致。
- AI Agent 觀察型回報：舊版可到高風險；現在上限中風險，並補上判定依據與 IP 核對。
- Cookie 證據：舊版存了完整 Cookie 值；現在只留頭尾。

改完後以 calculate_scores() 重算分數與優先清單，網頁與報告才會一致；快取的報告檔刪除，
下次下載時重新產生（報告編號不變）。
"""

from __future__ import annotations

from urllib.parse import urlparse

from django.db import transaction

from apps.scans.models import Finding, ScanJob
from apps.scans.reports import report_output_path
from apps.scans.scanners import (
    PageAnalysisInput,
    analyze_data_exposure,
    calculate_scores,
)
from apps.scans.security import owasp_mapper
from apps.scans.security.cookie_scanner import mask_cookie_line
from apps.scans.security.ip_context import describe_ips
from apps.scans.versions import SCORING_VERSION

LEGACY_PII_RULE = "SECURITY_PII_8B24BB8B28"
_AGENT_PREFIX_OLD = "Hermes-Agent 在實際操作與 probe 觀察中發現："
_AGENT_SUFFIX_OLD = "此為 AI agent 帶證據的觀察型回報；攻擊性驗證結論另見工具確認項。"


def _renormalize_pii(scan_job: ScanJob) -> int:
    changed = 0
    for finding in list(
        scan_job.findings.filter(rule_id=LEGACY_PII_RULE).select_related("page")
    ):
        page = finding.page
        if page is None or not page.html:
            continue
        fresh = analyze_data_exposure(
            PageAnalysisInput(
                url=page.url,
                final_url=page.final_url,
                title=page.title,
                html=page.html,
                headers=page.headers or {},
                element_boxes=page.element_boxes or {},
            )
        )
        finding.delete()
        for data in fresh:
            Finding.objects.create(scan_job=scan_job, page=page, **owasp_mapper.tag(data))
        changed += 1
    return changed


def _renormalize_agent(scan_job: ScanJob) -> int:
    hostname = urlparse(scan_job.normalized_url or "").hostname or ""
    changed = 0
    for finding in scan_job.findings.filter(rule_id="agent-observed-security"):
        updates = []
        if finding.severity in (Finding.Severity.HIGH, Finding.Severity.CRITICAL):
            finding.severity = Finding.Severity.MEDIUM
            updates.append("severity")
        if _AGENT_PREFIX_OLD in (finding.description or ""):
            ip_notes = describe_ips(finding.evidence or "", hostname)
            ip_text = ("\n證據中的 IP 自動核對：" + "；".join(ip_notes) + "。") if ip_notes else ""
            finding.description = (
                finding.description.replace(_AGENT_PREFIX_OLD, "AI Agent 在實際操作網站時觀察到：")
                .replace(_AGENT_SUFFIX_OLD, "")
                .strip()
                + ip_text
                + "\n這是 AI 的觀察與判讀，附有擷取的回應作為證據，但未經工具或人工驗證可被利用。"
            )
            finding.evidence_source = "hermes_agent"
            updates += ["description", "evidence_source"]
        if updates:
            finding.save(update_fields=updates)
            changed += 1
    return changed


def _renormalize_cookies(scan_job: ScanJob) -> int:
    changed = 0
    for finding in scan_job.findings.filter(rule_id__startswith="cookie-"):
        first, sep, rest = (finding.evidence or "").partition("\n")
        if not first or "已遮蔽" in first:
            continue
        finding.evidence = mask_cookie_line(first) + sep + rest
        finding.save(update_fields=["evidence"])
        changed += 1
    return changed


def _rescore(scan_job: ScanJob) -> None:
    findings = [
        {
            "title": f.title,
            "category": f.category,
            "severity": f.severity,
            "rule_id": f.rule_id,
            "priority_score": f.priority_score,
        }
        for f in scan_job.findings.order_by("-priority_score", "id")
    ]
    tested = set((scan_job.category_scores or {}).keys()) or None
    aeo_report = scan_job.aeo_report or {}
    base_scores = (
        {"aeo": aeo_report["score"]}
        if aeo_report.get("status") == "evaluated" and aeo_report.get("score") is not None
        else {}
    )
    overall, category_scores, top_actions = calculate_scores(
        findings, tested_categories=tested, base_scores=base_scores
    )
    scan_job.overall_score = overall
    scan_job.category_scores = category_scores
    scan_job.top_actions = top_actions
    # 只用目前公式重算分數、只重跑部分規則：計分版本更新，規則集版本維持原樣（versions.py）
    scan_job.scoring_version = SCORING_VERSION
    scan_job.save(
        update_fields=[
            "overall_score", "category_scores", "top_actions", "scoring_version", "updated_at"
        ]
    )


@transaction.atomic
def renormalize_scan(scan_job: ScanJob) -> dict[str, int]:
    """回傳各類調整的筆數；有任何調整才重算分數並刪除快取的報告檔。"""
    counts = {
        "pii": _renormalize_pii(scan_job),
        "agent": _renormalize_agent(scan_job),
        "cookie": _renormalize_cookies(scan_job),
    }
    if any(counts.values()) and scan_job.status == ScanJob.Status.COMPLETED:
        _rescore(scan_job)
        path = report_output_path(scan_job)
        transaction.on_commit(lambda: path.unlink(missing_ok=True))
    return counts
