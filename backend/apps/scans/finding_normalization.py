"""把既有掃描的發現套用目前的判定規則並重新計分（不重新爬取、不對目標發任何請求）。

2026-09-28 報告審查後，幾條規則的判定改了，但已完成的掃描仍保留舊結果：
- PII：舊版看到任何個資一律高風險；現在依資料種類與脈絡分級（本網域 Email 只是資訊提示）。
  以資料庫裡保存的頁面 HTML 重跑同一支 analyze_data_exposure()，結果與新掃描一致。
- AI Agent 觀察型回報：舊版可到高風險；現在上限中風險，並補上判定依據與 IP 核對。
- Cookie 證據：舊版存了完整 Cookie 值；現在只留頭尾。
- AI Agent 資安觀察的代號（2026-10-16）：舊版全部共用 agent-observed-security，
  改為每個問題自己的代號。

改完後以 calculate_scores() 重算分數與優先清單，網頁與報告才會一致；快取的報告檔刪除，
下次下載時重新產生（報告編號不變）。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from django.db import transaction

from apps.scans.models import Finding, ScanJob
from apps.scans.reports import report_output_path
from apps.scans.scanners import (
    PageAnalysisInput,
    analyze_data_exposure,
    calculate_scores,
    is_agent_observation,
    summarize_agent_security,
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
    from apps.agent.tools import SCANNER_IP_NOTE, scanner_ip_disclosure

    hostname = urlparse(scan_job.normalized_url or "").hostname or ""
    changed = 0
    for finding in scan_job.findings.filter(rule_id__startswith="agent-observed-security"):
        updates = []
        evidence_json = finding.evidence_json if isinstance(finding.evidence_json, dict) else {}
        # 證據中的 IP 全是掃描器出口（設定 ARGUS_SCANNER_EGRESS_IPS 之後才判得出來）：降為資訊提示
        if finding.severity != Finding.Severity.INFO and scanner_ip_disclosure(
            finding.title, finding.description or "", finding.evidence or ""
        ):
            finding.severity = Finding.Severity.INFO
            if SCANNER_IP_NOTE.strip() not in (finding.description or ""):
                finding.description = (finding.description or "").rstrip() + SCANNER_IP_NOTE
                updates.append("description")
            updates.append("severity")
        # 以主動工具驗證過的回報（2026-10-10 起）本來就允許高風險，不降級
        if finding.severity in (
            Finding.Severity.HIGH, Finding.Severity.CRITICAL
        ) and not evidence_json.get("tool_verified"):
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


_OBSERVED_ENDPOINT = re.compile(r"（觀察端點：(.*?)）")


def _rekey_agent_security(scan_job: ScanJob) -> int:
    """舊的 Agent 資安觀察共用代號 agent-observed-security，改成每個問題自己的代號（2026-10-16）。

    共用代號讓計分與優先處理只留第一筆、報告把所有 Agent 觀察併成一張卡、歷史比較把不同問題
    當成同一個。新代號與新掃描同一套規則（類型＋端點）；同一次掃描裡同類型、標題相近的回報
    給同一個代號，畫面與報告會合併顯示——只改代號，不刪任何發現。端點從描述裡的
    「（觀察端點：…）」取回。
    """
    from apps.agent.findings import AGENT_SECURITY_RULE, agent_security_rule_id, rank, same_issue

    rows = list(scan_job.findings.filter(rule_id=AGENT_SECURITY_RULE))
    if not rows:
        return 0
    items = []
    for finding in rows:
        match = _OBSERVED_ENDPOINT.search(finding.description or "")
        items.append({
            "finding": finding,
            "title": finding.title,
            "description": finding.description,
            "severity": finding.severity,
            "evidence_json": (
                finding.evidence_json if isinstance(finding.evidence_json, dict) else {}
            ),
            "rule_id": agent_security_rule_id(
                finding.title, finding.description, match.group(1) if match else ""
            ),
        })
    items.sort(key=rank)
    assigned: list[dict] = []
    for item in items:
        group = next((kept for kept in assigned if same_issue(kept, item)), None)
        item["finding"].rule_id = group["rule_id"] if group else item["rule_id"]
        item["finding"].save(update_fields=["rule_id"])
        if group is None:
            assigned.append(item)
    return len(rows)


def rekey_agent_findings_and_rescore(scan_job) -> int:
    """migration 0035 用：只做代號回填與重算分數（不重跑 PII 等其他重新判定）。

    migration 傳入的是歷史 model：只用欄位、`findings` 關聯與 save(update_fields)，
    不碰 model 上的方法或 TextChoices（歷史 model 沒有），狀態直接比字串。
    """
    with transaction.atomic():
        changed = _rekey_agent_security(scan_job)
        if changed and scan_job.status == "completed":
            _rescore(scan_job)
            path = report_output_path(scan_job)
            transaction.on_commit(lambda: path.unlink(missing_ok=True))
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


def stored_scoring_inputs(scan_job: ScanJob) -> tuple[list[dict], set[str] | None, dict]:
    """由資料庫保存的發現還原計分輸入：(findings, tested_categories, base_scores)。

    重新計分（_rescore）與分數說明（score-breakdown API）共用，兩邊的輸入一致。
    AI Agent 觀察（agent-observed-security-*）不進基準分（ADR-0006 決策 C，與 stage_scoring 一致）；
    2026-10-19 實掃它們被算回去，分數說明與報告附錄誤判「計分後被重新判定」而整段不列。
    """
    findings = [
        {
            "title": f.title,
            "category": f.category,
            "severity": f.severity,
            "rule_id": f.rule_id,
            "priority_score": f.priority_score,
        }
        for f in scan_job.findings.order_by("-priority_score", "id")
        if not is_agent_observation({"rule_id": f.rule_id})
    ]
    tested = set((scan_job.category_scores or {}).keys()) or None
    aeo_report = scan_job.aeo_report or {}
    base_scores = (
        {"aeo": aeo_report["score"]}
        if aeo_report.get("status") == "evaluated" and aeo_report.get("score") is not None
        else {}
    )
    return findings, tested, base_scores


def _rescore(scan_job: ScanJob) -> None:
    findings, tested, base_scores = stored_scoring_inputs(scan_job)
    overall, category_scores, top_actions = calculate_scores(
        findings, tested_categories=tested, base_scores=base_scores
    )
    scan_job.overall_score = overall
    scan_job.category_scores = category_scores
    scan_job.top_actions = top_actions
    # Agent 觀察不在 findings（基準分）裡，另以摘要獨立呈現——與 stage_scoring 相同
    scan_job.agent_findings_summary = summarize_agent_security([
        {"rule_id": rule_id, "severity": severity}
        for rule_id, severity in scan_job.findings.values_list("rule_id", "severity")
    ])
    # 只用目前公式重算分數、只重跑部分規則：計分版本更新，規則集版本維持原樣（versions.py）
    scan_job.scoring_version = SCORING_VERSION
    scan_job.save(
        update_fields=[
            "overall_score", "category_scores", "top_actions", "agent_findings_summary",
            "scoring_version", "updated_at",
        ]
    )


@transaction.atomic
def renormalize_scan(scan_job: ScanJob) -> dict[str, int]:
    """回傳各類調整的筆數；有任何調整才重算分數並刪除快取的報告檔。"""
    counts = {
        "pii": _renormalize_pii(scan_job),
        "agent": _renormalize_agent(scan_job),
        "agent_rule": _rekey_agent_security(scan_job),
        "cookie": _renormalize_cookies(scan_job),
    }
    if any(counts.values()) and scan_job.status == ScanJob.Status.COMPLETED:
        _rescore(scan_job)
        path = report_output_path(scan_job)
        transaction.on_commit(lambda: path.unlink(missing_ok=True))
    return counts
