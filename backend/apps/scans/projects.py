"""網站專案的彙整資料：總覽與跨掃描問題比較（docs/adr/0003-site-project-workspace.md）。

只讀 DB，不連線目標網站。問題的追蹤單位＝一次掃描中同一條規則（rule_id；沒有 rule_id 時
用「分類＋標題」），與報告合併多頁發現的規則一致。
"""

from __future__ import annotations

from html.parser import HTMLParser

from django.db.models import Count, Q

from apps.scans import versions
from apps.scans.coverage import (
    ABSENT_STATUS_LABELS,
    absent_issue_status,
    incomplete_checks,
    issue_key,
)
from apps.scans.models import ALL_CATEGORIES, Finding, ScanJob, SiteProject
from apps.scans.services import user_owns_domain

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
_SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITY_ORDER)}
_IN_PROGRESS = [
    ScanJob.Status.QUEUED,
    ScanJob.Status.CRAWLING,
    ScanJob.Status.SCANNING,
    ScanJob.Status.AGENT_TESTING,
]
TREND_LIMIT = 12
STREAK_LOOKBACK = 30
TOP_ACTIONS_LIMIT = 5
SAMPLE_URLS_LIMIT = 3
ISSUE_URLS_LIMIT = 50
RECENT_SCANS_LIMIT = 5
SUMMARY_HISTORY_LIMIT = 8
SITE_DESCRIPTION_LIMIT = 160


def completed_scans(project: SiteProject):
    return project.scans.filter(status=ScanJob.Status.COMPLETED).order_by("-completed_at", "-id")


def active_scan(project: SiteProject) -> ScanJob | None:
    return project.scans.filter(status__in=_IN_PROGRESS).order_by("-created_at").first()


def previous_completed(project: SiteProject, scan: ScanJob) -> ScanJob | None:
    """同專案中比 scan 早完成的最近一次完成掃描（用來比較新增／持續／未出現）。"""
    return (
        completed_scans(project).filter(created_at__lt=scan.created_at).exclude(id=scan.id).first()
    )


def issue_groups(scan: ScanJob) -> dict[str, dict]:
    """把一次掃描的 finding 依規則合併成問題；嚴重度取最嚴重的一筆，代表 finding 供連到證據。

    只收本次有勾的維度：掃描流程的部分站台層級檢查（例如 DNS 郵件紀錄）不論勾選都會寫入
    finding，但沒勾的維度不計分、報告顯示未評估，問題分析也必須一致，否則會出現
    「沒勾資安卻列出資安問題」。
    """
    rows = (
        Finding.objects.filter(scan_job=scan, category__in=scan.effective_categories)
        .order_by()
        .values(
            "id",
            "rule_id",
            "category",
            "severity",
            "title",
            "description",
            "remediation",
            "page__final_url",
            "page__url",
        )
    )
    groups: dict[str, dict] = {}
    for row in rows:
        key = issue_key(row["rule_id"], row["category"], row["title"])
        group = groups.get(key)
        url = row["page__final_url"] or row["page__url"] or ""
        if group is None:
            group = groups[key] = {
                "key": key,
                "rule_id": row["rule_id"],
                "title": row["title"],
                "category": row["category"],
                "severity": row["severity"],
                "finding_id": row["id"],
                "description": row["description"],
                "remediation": row["remediation"],
                "occurrences": 0,
                "_urls": [],
            }
        group["occurrences"] += 1
        if url and url not in group["_urls"]:
            group["_urls"].append(url)
        if _SEVERITY_RANK.get(row["severity"], 9) < _SEVERITY_RANK.get(group["severity"], 9):
            group["severity"] = row["severity"]
            group["title"] = row["title"]
            group["finding_id"] = row["id"]
            group["description"] = row["description"]
            group["remediation"] = row["remediation"]
    for group in groups.values():
        urls = group.pop("_urls")
        group["pages"] = len(urls)
        group["sample_urls"] = urls[:SAMPLE_URLS_LIMIT]
        group["urls"] = urls[:ISSUE_URLS_LIMIT]
    return groups


def compare_issues(scan: ScanJob, previous: ScanJob | None) -> tuple[list[dict], list[dict]]:
    """回傳 (本次問題附 status＝new／persisting, 本次未出現的上次問題)。

    「本次未出現」只列本次仍有檢查的分類：沒勾的維度不能算已修好。每一項附 status
    （coverage.absent_issue_status）：只有產生它的檢查本次完整跑完、受影響頁面也有重新分析，
    才是 resolved；其餘是本次未觀察到／未檢查／被阻擋／無法判定。
    沒有前次掃描時，status 為 None（無從比較）。
    """
    current = issue_groups(scan)
    previous_groups = issue_groups(previous) if previous is not None else {}
    for key, group in current.items():
        if previous is None:
            group["status"] = None
        else:
            group["status"] = "persisting" if key in previous_groups else "new"
    checked = scan.effective_categories
    analysed_urls = _analysed_urls(scan) if previous is not None else set()
    missing = []
    for key, group in previous_groups.items():
        if key in current or group["category"] not in checked:
            continue
        status = absent_issue_status(
            previous_coverage=previous.coverage,
            current_coverage=scan.coverage,
            key=key,
            category=group["category"],
            urls=group["urls"],
            analysed_urls=analysed_urls,
        )
        missing.append({
            **{k: group[k] for k in ("key", "rule_id", "title", "category", "severity")},
            "status": status,
            "status_label": ABSENT_STATUS_LABELS[status],
        })
    issues = sorted(
        current.values(),
        key=lambda g: (_SEVERITY_RANK.get(g["severity"], 9), -g["pages"], g["title"]),
    )
    missing.sort(key=lambda g: (_SEVERITY_RANK.get(g["severity"], 9), g["title"]))
    return issues, missing


def _analysed_urls(scan: ScanJob) -> set[str]:
    """本次有完整分析的頁面網址（沒被阻擋、HTTP < 400），含轉址前後兩種寫法。"""
    urls: set[str] = set()
    rows = scan.pages.filter(blocked_reason="", status_code__lt=400).values_list(
        "url", "final_url"
    )
    for url, final_url in rows:
        urls.update(u for u in (url, final_url) if u)
    return urls


def issue_streaks(project: SiteProject, scan: ScanJob, issues: list[dict]) -> None:
    """替每個問題加上 streak（連續幾次完成的掃描都出現，含本次）與 since（最早那次的完成時間）。

    往回看同專案、建立時間不晚於 scan 的完成掃描（最多 STREAK_LOOKBACK 次）；遇到沒出現、
    或那次沒勾該維度（無從判斷）就停。讓使用者看出「這個問題已經拖多久沒修」。
    """
    history = list(
        completed_scans(project)
        .filter(created_at__lte=scan.created_at)
        .order_by("-created_at", "-id")
        .only("id", "completed_at", "categories")[:STREAK_LOOKBACK]
    )
    keys_by_scan: dict[int, set[str]] = {item.id: set() for item in history}
    rows = (
        Finding.objects.filter(scan_job_id__in=list(keys_by_scan))
        .order_by()
        .values_list("scan_job_id", "rule_id", "category", "title")
        .distinct()
    )
    for scan_id, rule_id, category, title in rows:
        keys_by_scan[scan_id].add(issue_key(rule_id, category, title))
    for issue in issues:
        streak, since = 0, None
        for item in history:
            if issue["category"] not in item.effective_categories:
                break
            if issue["key"] not in keys_by_scan[item.id]:
                break
            streak += 1
            since = item.completed_at
        issue["streak"] = streak
        issue["since"] = since


def _scan_brief(scan: ScanJob | None) -> dict | None:
    if scan is None:
        return None
    return {
        "id": scan.id,
        "status": scan.status,
        "overall_score": scan.overall_score,
        "created_at": scan.created_at,
        "completed_at": scan.completed_at,
    }


def project_overview(project: SiteProject) -> dict:
    """專案總覽頁的全部資料。沒有完成的掃描時 latest_scan 為 None。"""
    latest = completed_scans(project).first()
    previous = previous_completed(project, latest) if latest is not None else None
    running = active_scan(project)
    severity_counts = {severity: 0 for severity in SEVERITY_ORDER}
    changes = None
    latest_payload = None
    if latest is not None:
        issues, missing = compare_issues(latest, previous)
        for issue in issues:
            severity_counts[issue["severity"]] = severity_counts.get(issue["severity"], 0) + 1
        if previous is not None:
            changes = {
                "new": sum(1 for issue in issues if issue["status"] == "new"),
                "persisting": sum(1 for issue in issues if issue["status"] == "persisting"),
                "missing": len(missing),
                "resolved": sum(1 for item in missing if item["status"] == "resolved"),
            }
        counts = latest.pages.aggregate(
            n=Count("id"), blocked=Count("id", filter=~Q(blocked_reason=""))
        )
        warnings = latest.warning_summary or {}
        duration = (
            int((latest.completed_at - latest.started_at).total_seconds())
            if latest.completed_at and latest.started_at
            else None
        )
        category_counts: dict[str, int] = {}
        for issue in issues:
            category_counts[issue["category"]] = category_counts.get(issue["category"], 0) + 1
        aeo = latest.aeo_report or {}
        latest_payload = {
            **_scan_brief(latest),
            "category_scores": latest.category_scores or {},
            "categories": sorted(latest.effective_categories),
            "scan_mode": latest.scan_mode,
            "pages_count": counts["n"],
            "issues_count": len(issues),
            # 與問題分析一致：只列本次有勾的維度（top_actions 由計分階段從全部 finding 產生）
            "top_actions": [
                action
                for action in (latest.top_actions or [])
                if action.get("category") in latest.effective_categories
            ][:TOP_ACTIONS_LIMIT],
            "aeo_status": aeo.get("status", ""),
            # 覆蓋契約：各維度覆蓋狀態與沒有完整跑完的檢查（前端提示「部分評估」）
            "coverage": {
                "categories": (latest.coverage or {}).get("categories") or {},
                "incomplete": incomplete_checks(latest.coverage),
            },
            # 儀表板用：本次掃描統計、各維度問題數、AEO 問答摘要
            "stats": {
                "pages": counts["n"],
                "pages_blocked": counts["blocked"],
                "pages_failed": len(warnings.get("failed_urls") or []),
                "max_pages": latest.max_pages,
                "duration_seconds": duration,
                "findings": latest.findings.filter(
                    category__in=latest.effective_categories
                ).count(),
            },
            "category_counts": category_counts,
            "aeo": {
                key: aeo.get(key)
                for key in (
                    "status",
                    "reason",
                    "questions_total",
                    "answered_ratio",
                    "evidence_ratio",
                    "counts",
                )
            }
            if aeo
            else None,
        }
    trend_scans = list(reversed(list(completed_scans(project)[:TREND_LIMIT])))
    trend = [
        {
            "id": scan.id,
            "completed_at": scan.completed_at,
            "overall_score": scan.overall_score,
            "category_scores": scan.category_scores or {},
            "version_label": versions.label(scan),
            # 與前一點的評分或規則版本不同：走勢圖要標示，不能把這段變化當成網站改善
            "model_changed": index > 0 and not versions.comparable(scan, trend_scans[index - 1]),
        }
        for index, scan in enumerate(trend_scans)
    ]
    recent_scans = [
        {**_scan_brief(scan), "scan_mode": scan.scan_mode, "max_pages": scan.max_pages}
        for scan in project.scans.order_by("-created_at", "-id")[:RECENT_SCANS_LIMIT]
    ]
    return {
        "latest_scan": latest_payload,
        "recent_scans": recent_scans,
        "previous_scan": _scan_brief(previous),
        # 兩次掃描的評分與規則版本相同，分數變化才可直接解讀成網站變好／變差（versions.py）
        "score_comparable": versions.comparable(latest, previous),
        "active_scan": (
            {**_scan_brief(running), "progress": running.progress or {}} if running else None
        ),
        "severity_counts": severity_counts,
        "changes": changes,
        "trend": trend,
        "scans_count": project.scans.count(),
        "domain_verified": user_owns_domain(project.user, project.hostname),
        "site_description": site_description(latest),
    }


class _MetaDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        attr = {name.lower(): (value or "") for name, value in attrs}
        key = (attr.get("name") or attr.get("property") or "").lower()
        if key in ("description", "og:description") and attr.get("content", "").strip():
            self.values.setdefault(key, " ".join(attr["content"].split()))


def site_description(scan: ScanJob | None) -> str:
    """網站自己寫的簡介：最新完成掃描首頁的 meta description（沒有就 og:description）。"""
    if scan is None:
        return ""
    home = scan.pages.order_by("depth", "id").values_list("html", flat=True).first()
    if not home:
        return ""
    parser = _MetaDescriptionParser()
    try:
        # 只需要 <head>
        parser.feed(home[:100_000])
    except Exception:  # noqa: BLE001 - 壞掉的 HTML 就當作沒有簡介
        return ""
    text = parser.values.get("description") or parser.values.get("og:description") or ""
    return text[:SITE_DESCRIPTION_LIMIT]


def project_issues(project: SiteProject, scan: ScanJob | None = None) -> dict:
    """問題分析頁：指定（預設最新一次完成）掃描的問題與前次比較。"""
    scan = scan or completed_scans(project).first()
    if scan is None:
        return {"scan": None, "compared_with": None, "issues": [], "missing": []}
    previous = previous_completed(project, scan)
    issues, missing = compare_issues(scan, previous)
    issue_streaks(project, scan, issues)
    return {
        "scan": {**_scan_brief(scan), "categories": sorted(scan.effective_categories)},
        "compared_with": _scan_brief(previous),
        "issues": issues,
        "missing": missing,
    }


def project_pages(project: SiteProject, scan: ScanJob | None = None) -> dict:
    """頁面清單（最新一次或指定一次完成的掃描）：狀態碼、載入時間、每頁問題數與最高嚴重度。

    只計本次有勾的維度；站台層級（沒有對應頁面）的發現不算在任何一頁上，另回總數。
    """
    scan = scan or completed_scans(project).first()
    if scan is None:
        return {"scan": None, "pages": [], "site_level_findings": 0}
    checked = scan.effective_categories
    per_page: dict[int, dict] = {}
    site_level = 0
    rows = (
        Finding.objects.filter(scan_job=scan, category__in=checked)
        .order_by()
        .values("page_id", "severity", "category")
    )
    for row in rows:
        if row["page_id"] is None:
            site_level += 1
            continue
        entry = per_page.setdefault(
            row["page_id"], {"findings": 0, "max_severity": None, "by_category": {}}
        )
        entry["findings"] += 1
        entry["by_category"][row["category"]] = entry["by_category"].get(row["category"], 0) + 1
        current = entry["max_severity"]
        if current is None or _SEVERITY_RANK.get(row["severity"], 9) < _SEVERITY_RANK.get(
            current, 9
        ):
            entry["max_severity"] = row["severity"]
    pages = []
    for page in scan.pages.order_by("depth", "id").only(
        "id",
        "url",
        "final_url",
        "status_code",
        "title",
        "load_time_ms",
        "depth",
        "blocked_reason",
        "screenshot_path",
    ):
        entry = per_page.get(page.id, {"findings": 0, "max_severity": None, "by_category": {}})
        pages.append(
            {
                "id": page.id,
                "url": page.final_url or page.url,
                "title": page.title,
                "status_code": page.status_code,
                "load_time_ms": page.load_time_ms,
                "depth": page.depth,
                "blocked_reason": page.blocked_reason,
                "has_screenshot": bool(page.screenshot_path),
                **entry,
            }
        )
    return {
        "scan": {**_scan_brief(scan), "categories": sorted(checked)},
        "pages": pages,
        "site_level_findings": site_level,
    }


def project_summaries(project_ids: list[int]) -> dict[int, dict]:
    """專案清單與切換器用的摘要：最新一次掃描、最新完成分數與前一次完成分數（算變化）、
    最近幾次完成分數（走勢）、最新完成掃描依嚴重度的問題數。

    兩次查詢撈回這些專案的掃描與最新掃描的問題，避免每個專案各查一次。
    """
    summaries: dict[int, dict] = {
        pid: {
            "scans_count": 0,
            "latest_scan": None,
            "latest_score": None,
            "latest_category_scores": {},
            "previous_score": None,
            # 最新與前一次完成掃描的版本相同，變化才可直接比較（versions.py）
            "score_comparable": False,
            "last_completed_at": None,
            "score_history": [],
            "issue_counts": {},
        }
        for pid in project_ids
    }
    latest_completed: dict[int, tuple[int, set[str]]] = {}
    rows = (
        ScanJob.objects.filter(project_id__in=project_ids)
        .order_by("-created_at", "-id")
        .values(
            "id",
            "project_id",
            "status",
            "overall_score",
            "category_scores",
            "categories",
            "created_at",
            "completed_at",
            "scoring_version",
            "ruleset_version",
        )
    )
    latest_versions: dict[int, tuple[str, str]] = {}
    for row in rows:
        summary = summaries[row["project_id"]]
        summary["scans_count"] += 1
        if summary["latest_scan"] is None:
            summary["latest_scan"] = {
                k: row[k] for k in ("id", "status", "overall_score", "created_at", "completed_at")
            }
        if row["status"] != ScanJob.Status.COMPLETED:
            continue
        if (
            row["overall_score"] is not None
            and len(summary["score_history"]) < SUMMARY_HISTORY_LIMIT
        ):
            summary["score_history"].insert(0, row["overall_score"])
        if summary["last_completed_at"] is None:
            summary["latest_score"] = row["overall_score"]
            summary["latest_category_scores"] = row["category_scores"] or {}
            summary["last_completed_at"] = row["completed_at"]
            effective = {c for c in (row["categories"] or []) if c in ALL_CATEGORIES}
            latest_completed[row["project_id"]] = (row["id"], effective or set(ALL_CATEGORIES))
            latest_versions[row["project_id"]] = (row["scoring_version"], row["ruleset_version"])
        elif summary["previous_score"] is None and summary["latest_score"] is not None:
            summary["previous_score"] = row["overall_score"]
            current = latest_versions.get(row["project_id"], ("", ""))
            summary["score_comparable"] = all(current) and current == (
                row["scoring_version"], row["ruleset_version"]
            )
    _attach_issue_counts(summaries, latest_completed)
    return summaries


def _attach_issue_counts(
    summaries: dict[int, dict], latest: dict[int, tuple[int, set[str]]]
) -> None:
    """最新完成掃描的問題數（同一條規則算一個、取最高嚴重度、只算有勾的維度、不含 info）。"""
    project_by_scan = {scan_id: pid for pid, (scan_id, _) in latest.items()}
    worst: dict[int, dict[str, int]] = {}
    rows = Finding.objects.filter(scan_job_id__in=project_by_scan).values_list(
        "scan_job_id", "severity", "rule_id", "category", "title"
    )
    for scan_id, severity, rule_id, category, title in rows:
        pid = project_by_scan[scan_id]
        if severity == "info" or category not in latest[pid][1]:
            continue
        key = issue_key(rule_id, category, title)
        rank = _SEVERITY_RANK.get(severity, len(SEVERITY_ORDER))
        issues = worst.setdefault(pid, {})
        issues[key] = min(rank, issues.get(key, rank))
    for pid, issues in worst.items():
        counts: dict[str, int] = {}
        for rank in issues.values():
            if rank < len(SEVERITY_ORDER):
                counts[SEVERITY_ORDER[rank]] = counts.get(SEVERITY_ORDER[rank], 0) + 1
        summaries[pid]["issue_counts"] = counts
