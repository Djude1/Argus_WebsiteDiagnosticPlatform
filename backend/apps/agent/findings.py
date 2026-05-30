"""把 Hermes-Agent 的 report_ux_issue 結果落地成 Finding。

設計：
- loop 層只負責收集 issues（dict 列表），不直接寫 DB；落地分離方便測試。
- 落地時依 issue['url'] 找對應 Page（若找不到則 page=None，視為站台層級 finding）。
- ai_handoff_prompt 走專案統一模板，明確要求對方 LLM「不要輸出完整修復程式碼」。
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.scans.models import Finding, Page, ScanJob

UX_HANDOFF_TEMPLATE = """我網站有以下 UX 問題，請協助我分析並提供修復方向：
- 問題類型: ux
- 嚴重度: {severity}
- 問題描述: {description}
- 對應位置: {url}
- 元素 selector: {selector}
- 修補建議方向: {remediation}

請依此資訊提供具體修改方向、檢查步驟與注意事項；不要輸出完整修復程式碼。"""


VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}


def persist_agent_issues(
    scan_job: ScanJob, issues: Iterable[dict], default_priority: float = 50.0
) -> list[Finding]:
    """把 agent 收集的 issue 落地成 Finding（category=ux）。

    回傳新建的 Finding 物件列表。同 scan_job 內若已有相同 title 的 ux finding，
    則略過（避免 agent 多輪重複回報同一問題）。
    """
    created: list[Finding] = []
    existing_titles = set(
        scan_job.findings.filter(category=Finding.Category.UX).values_list("title", flat=True)
    )

    page_cache: dict[str, Page | None] = {}

    for issue in issues:
        title = (issue.get("title") or "").strip()[:255]
        if not title or title in existing_titles:
            continue

        severity = issue.get("severity") or "low"
        if severity not in VALID_SEVERITIES:
            severity = "low"

        description = (issue.get("description") or "").strip()
        if not description:
            continue

        remediation = (issue.get("remediation") or "請檢視該流程的可用性並對齊使用者預期。").strip()
        url = (issue.get("url") or "").strip()
        selector = (issue.get("selector") or "").strip()[:512]

        page = _resolve_page(scan_job, url, page_cache)

        handoff = UX_HANDOFF_TEMPLATE.format(
            severity=severity,
            description=description,
            url=url or "(站台層級)",
            selector=selector or "(無)",
            remediation=remediation,
        )

        finding = Finding.objects.create(
            scan_job=scan_job,
            page=page,
            category=Finding.Category.UX,
            severity=severity,
            title=title,
            description=description,
            remediation=remediation,
            evidence=f"URL: {url}\nselector: {selector}",
            selector=selector,
            ai_handoff_prompt=handoff,
            priority_score=default_priority,
            impact_area="ux",
            confidence=0.7,  # Agent 自我回報，預設信心略低於規則式掃描
        )
        created.append(finding)
        existing_titles.add(title)

    return created


def _resolve_page(scan_job: ScanJob, url: str, cache: dict[str, Page | None]) -> Page | None:
    if not url:
        return None
    if url in cache:
        return cache[url]
    page = scan_job.pages.filter(final_url=url).first() or scan_job.pages.filter(url=url).first()
    cache[url] = page
    return page
