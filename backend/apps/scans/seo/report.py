"""SEO 分析頁的 API 資料（只讀資料庫）。

每項結論都附受影響網址、檢測時間與證據：
- 頁面類（Title、H1…）的檢測時間＝爬到該頁的時間（Page.created_at），證據＝原始值。
- 連結與站台類的檢測時間＝ScanJob.seo_report["checked_at"]，證據＝跳轉鏈與狀態碼。
「可索引」是 Argus 依頁面本身判斷；「Google 已收錄」只能由 Search Console 回答，分開顯示。
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.core.cache import cache

from apps.scans.models import Page, ScanJob, SiteProject
from apps.scans.seo.keywords import keyword_report
from apps.scans.seo.link_check import classify_link, robots_blocks
from apps.scans.seo.page_audit import GENERIC_ANCHORS, audit_page

CACHE_VERSION = 1
CACHE_SECONDS = 3600
LEVEL_ORDER = {"critical": 0, "warning": 1, "notice": 2, "pass": 3}
MAX_ISSUE_PAGES = 100
MAX_LINK_SOURCES = 20
MAX_ANCHOR_ISSUES = 300
MAX_SCANS = 30

ISSUE_TITLES = {
    ("status", "critical"): "頁面回應錯誤（4xx／5xx）",
    ("status", "warning"): "爬蟲無法取得頁面",
    ("title", "critical"): "缺少 Title",
    ("title", "warning"): "Title 長度不理想",
    ("description", "warning"): "缺少 Description",
    ("description", "notice"): "Description 長度不理想",
    ("h1", "warning"): "缺少 H1 或 H1 沒有文字",
    ("h1", "notice"): "一頁有多個 H1",
    ("headings", "warning"): "有沒有文字的標題",
    ("headings", "notice"): "標題層級跳號",
    ("content", "notice"): "正文偏少",
    ("canonical", "warning"): "canonical 指向其他網域",
    ("robots", "warning"): "頁面設定 noindex",
    ("robots", "notice"): "搜尋摘要受到限制",
    ("images", "warning"): "圖片缺少 alt",
    ("speed", "warning"): "載入明顯偏慢",
    ("speed", "notice"): "載入偏慢",
    ("open_graph", "notice"): "Open Graph 不完整",
}


def _issue_title(check: dict) -> str:
    if check["key"] in {"title", "description"} and check["value"] and check["level"] in {
        "warning", "notice"
    }:
        short = "過短" in check["advice"] or "偏短" in check["advice"]
        return f"{check['label']} {'過短' if short else '過長（可能被截斷）'}"
    if check["key"] == "canonical" and check["level"] == "notice":
        return "未設定 canonical" if check["value"] == "（未設定）" else "canonical 指向其他網址"
    return ISSUE_TITLES.get((check["key"], check["level"]), check["label"])


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def scan_choices(project: SiteProject) -> list[dict]:
    scans = (
        ScanJob.objects.filter(project=project, status=ScanJob.Status.COMPLETED)
        .order_by("-created_at")[:MAX_SCANS]
    )
    return [
        {
            "id": scan.id,
            "created_at": _iso(scan.created_at),
            "completed_at": _iso(scan.completed_at),
            "pages": scan.pages.count(),
            "seo_checked": "seo" in scan.effective_categories,
            "links_checked": bool((scan.seo_report or {}).get("checked_at")),
        }
        for scan in scans
    ]


def _pages(scan: ScanJob):
    return (
        Page.objects.filter(scan_job=scan)
        .only(
            "id", "url", "final_url", "status_code", "title", "html", "rendered_dom",
            "headers", "load_time_ms", "blocked_reason", "created_at", "depth",
        )
        .order_by("depth", "id")
    )


def _link_rows(audits: list[dict], pages_by_url: dict, seo_report: dict, site_host: str):
    """把所有頁面的連結依目標網址合併，附上檢查結果；另列出錨文字有問題的連結。"""
    results = seo_report.get("links") or {}
    targets: dict[str, dict] = {}
    anchor_issues: list[dict] = []
    for audit in audits:
        for link in audit["links"]:
            url = link["url"]
            row = targets.get(url)
            if row is None:
                row = targets[url] = {
                    "url": url,
                    "type": classify_link(url, site_host),
                    "nofollow": False,
                    "sources": [],
                    "source_count": 0,
                    **_link_status(url, results, pages_by_url),
                }
            row["source_count"] += 1
            row["nofollow"] = row["nofollow"] or "nofollow" in link["rel"]
            if len(row["sources"]) < MAX_LINK_SOURCES:
                row["sources"].append({
                    "page_id": audit["page_id"], "url": audit["final_url"],
                    "anchor": link["text"] or link["label"],
                })
            anchor = (link["text"] or link["label"]).strip()
            problem = ""
            if not anchor:
                problem = "empty"
            elif anchor.casefold() in GENERIC_ANCHORS:
                problem = "generic"
            if problem and len(anchor_issues) < MAX_ANCHOR_ISSUES:
                anchor_issues.append({
                    "problem": problem, "anchor": anchor, "target": url,
                    "page_id": audit["page_id"], "source_url": audit["final_url"],
                })
    rows = sorted(
        targets.values(),
        key=lambda r: (_VERDICT_ORDER.get(r["verdict"], 9), r["type"], r["url"]),
    )
    return rows, anchor_issues


_VERDICT_ORDER = {"broken": 0, "error": 1, "loop": 2, "restricted": 3, "redirect": 4,
                  "other": 5, "unchecked": 6, "skipped": 7, "ok": 8}


def _link_status(url: str, results: dict, pages_by_url: dict) -> dict:
    if url in results:
        result = results[url]
        return {"verdict": result["verdict"], "status": result["status"],
                "chain": result["chain"], "note": result.get("note", "")}
    page = pages_by_url.get(url)
    if page is not None and page["status_code"] is not None and page["final_url"] == url:
        status = page["status_code"]
        verdict = "ok" if status < 300 else ("broken" if status >= 400 else "other")
        return {"verdict": verdict, "status": status,
                "chain": [{"url": url, "status": status}], "note": "爬蟲已造訪"}
    return {"verdict": "unchecked", "status": None, "chain": [], "note": ""}


def _issues(audits, page_meta, link_rows, anchor_issues, seo_report, links_checked_at):
    issues: dict[tuple, dict] = {}

    def add(key, level, title, advice, detected_at, page=None, value="", evidence=None,
            source="page"):
        issue = issues.setdefault((key, level, title), {
            "key": key, "level": level, "title": title, "advice": advice, "source": source,
            "pages": [], "count": 0,
        })
        issue["count"] += 1
        if len(issue["pages"]) < MAX_ISSUE_PAGES:
            issue["pages"].append({
                "page_id": page["page_id"] if page else None,
                "url": page["final_url"] if page else (evidence or {}).get("requested", ""),
                "value": value,
                "evidence": evidence,
                "detected_at": detected_at,
            })

    for audit in audits:
        detected = page_meta[audit["page_id"]]["detected_at"]
        for check in audit["checks"]:
            if check["level"] != "pass":
                add(check["key"], check["level"], _issue_title(check), check["advice"],
                    detected, audit, check["value"])

    for field, level, title, advice in (
        ("title", "warning", "多個頁面使用相同 Title",
         "每頁的 Title 應說明各自的主題，避免搜尋結果無法區分。"),
        ("description", "notice", "多個頁面使用相同 Description", "為重要頁面寫各自的摘要。"),
    ):
        groups: dict[str, list[dict]] = {}
        for audit in audits:
            if audit["status_code"] == 200 and audit[field]:
                groups.setdefault(audit[field], []).append(audit)
        for text, members in groups.items():
            if len(members) > 1:
                for audit in members:
                    add(f"duplicate_{field}", level, title, advice,
                        page_meta[audit["page_id"]]["detected_at"], audit,
                        f"「{text[:80]}」（{len(members)} 頁相同）")

    by_page = {a["page_id"]: a for a in audits}
    for row in link_rows:
        if row["verdict"] not in {"broken", "error", "loop", "redirect"}:
            continue
        if row["verdict"] == "redirect" and row["type"] != "internal":
            continue  # 站外連結轉址很常見，只有站內轉址值得處理
        level, title, advice = {
            "broken": ("critical" if row["type"] == "internal" else "warning",
                       "站內失效連結" if row["type"] == "internal" else "站外／子網域失效連結",
                       "修正連結網址，或改連到仍存在的頁面。"),
            "error": ("notice", "連結無法連線", "目標網站逾時或拒絕連線；稍後重掃確認是否持續。"),
            "loop": ("warning", "連結轉址過多", "轉址超過 5 次，直接連到最終網址。"),
            "redirect": ("notice", "站內連結經過轉址",
                         "轉址後正常、不算失效；把連結改成最終網址可少一次往返。"),
        }[row["verdict"]]
        for source in row["sources"]:
            chain = " → ".join(f"{hop['status'] or '—'}" for hop in row["chain"])
            add(f"link_{row['verdict']}", level, title, advice, links_checked_at,
                by_page.get(source["page_id"]),
                f"{row['url']}（{chain or row['note']}）；錨文字：{source['anchor'] or '（無）'}",
                {"target": row["url"], "chain": row["chain"]}, source="links")

    for item in anchor_issues:
        empty = item["problem"] == "empty"
        add("anchor_" + item["problem"], "warning" if empty else "notice",
            "連結沒有可讀文字" if empty else "連結文字不具描述性",
            "連結要有能說明目的地的文字（純圖片連結請給圖片 alt）。" if empty
            else "把「點此」「更多」改成說明目的地的文字，例如「查看報名方式」。",
            page_meta[item["page_id"]]["detected_at"], by_page.get(item["page_id"]),
            f"→ {item['target']}；錨文字：{item['anchor'] or '（無）'}",
            {"target": item["target"]}, source="links")

    for check in seo_report.get("site_checks") or []:
        if check["level"] != "pass":
            add(f"site_{check['key']}", check["level"], f"{check['label']}：需要處理",
                check["advice"], links_checked_at, None, check["value"], check["evidence"],
                source="site")

    return sorted(
        issues.values(), key=lambda i: (LEVEL_ORDER[i["level"]], -i["count"], i["title"])
    )


def _analysis(scan: ScanJob) -> dict:
    """單次掃描的分析結果（不含關鍵字與 GSC），以掃描與連結檢查時間為鍵快取。"""
    seo_report = scan.seo_report or {}
    key = f"argus:seo:{CACHE_VERSION}:{scan.id}:{seo_report.get('checked_at', '')}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    site_host = urlsplit(scan.normalized_url or scan.original_url).hostname or ""
    disallow = (seo_report.get("robots") or {}).get("disallow") or []
    audits, page_meta, pages_by_url = [], {}, {}
    for page in _pages(scan):
        audit = audit_page(page)
        rule = robots_blocks(urlsplit(audit["final_url"]).path or "/", disallow)
        if rule:
            audit["not_indexable_reasons"].append(f"robots.txt Disallow: {rule}")
            audit["indexable"] = False
        audits.append(audit)
        page_meta[page.id] = {"detected_at": _iso(page.created_at)}
        pages_by_url[page.url] = {"status_code": page.status_code, "final_url": page.final_url}

    links_checked_at = seo_report.get("checked_at")
    link_rows, anchor_issues = _link_rows(audits, pages_by_url, seo_report, site_host)
    issues = _issues(audits, page_meta, link_rows, anchor_issues, seo_report, links_checked_at)

    affected = {
        page["page_id"]
        for issue in issues if issue["level"] in {"critical", "warning"}
        for page in issue["pages"] if page["page_id"]
    }
    link_counts = {kind: 0 for kind in ("internal", "subdomain", "external")}
    for row in link_rows:
        link_counts[row["type"]] += 1
    result = {
        "pages": [_lean_page(audit, page_meta) for audit in audits],
        "keyword_index": [
            {k: audit[k] for k in ("page_id", "final_url", "status_code", "title",
                                   "description", "h1", "headings")}
            | {"main_text": audit["main_text"][:50_000]}
            for audit in audits
        ],
        "issues": issues,
        "links": {
            "checked_at": links_checked_at,
            "unchecked": seo_report.get("unchecked", 0),
            "limit": seo_report.get("limit"),
            "counts": link_counts,
            "rows": link_rows,
            "anchor_issues": anchor_issues,
        },
        "site_checks": seo_report.get("site_checks") or [],
        "robots": seo_report.get("robots") or {},
        "overview": {
            "pages_scanned": len(audits),
            "pages_affected": len(affected),
            "critical": sum(i["count"] for i in issues if i["level"] == "critical"),
            "warnings": sum(i["count"] for i in issues if i["level"] == "warning"),
            "notices": sum(i["count"] for i in issues if i["level"] == "notice"),
            "indexable": sum(1 for a in audits if a["indexable"]),
            "broken_links": sum(1 for r in link_rows if r["verdict"] == "broken"),
            "priorities": [
                {k: issue[k] for k in ("key", "level", "title", "advice", "count", "source")}
                | {"example": issue["pages"][0] if issue["pages"] else None}
                for issue in issues if issue["level"] in {"critical", "warning"}
            ][:6],
        },
    }
    cache.set(key, result, CACHE_SECONDS)
    return result


def _lean_page(audit: dict, page_meta: dict) -> dict:
    return {
        "page_id": audit["page_id"],
        "url": audit["final_url"],
        "status_code": audit["status_code"],
        "title": audit["title"],
        "description": audit["description"],
        "h1": audit["h1"],
        "heading_counts": {
            f"h{n}": sum(1 for h in audit["headings"] if h["level"] == n) for n in range(1, 7)
        },
        "canonical": audit["canonical"],
        "robots": audit["robots"],
        "indexable": audit["indexable"],
        "not_indexable_reasons": audit["not_indexable_reasons"],
        "content": audit["content"],
        "image_total": audit["image_total"],
        "images_missing_alt": sum(1 for img in audit["images"] if img["alt"] is None),
        "load_time_ms": audit["load_time_ms"],
        "link_total": audit["link_total"],
        "checks": audit["checks"],
        "detected_at": page_meta[audit["page_id"]]["detected_at"],
    }


def project_seo(project: SiteProject, scan: ScanJob | None) -> dict:
    scans = scan_choices(project)
    base = {
        "project_id": project.id,
        "scans": scans,
        "keywords": project.target_keywords or [],
    }
    if scan is None:
        return {**base, "scan": None}
    analysis = _analysis(scan)
    return {
        **base,
        "scan": {
            "id": scan.id,
            "created_at": _iso(scan.created_at),
            "completed_at": _iso(scan.completed_at),
            "seo_checked": "seo" in scan.effective_categories,
        },
        "overview": analysis["overview"],
        "pages": analysis["pages"],
        "issues": analysis["issues"],
        "links": analysis["links"],
        "site_checks": analysis["site_checks"],
        "robots": analysis["robots"],
        "keyword_report": keyword_report(project.target_keywords or [], analysis["keyword_index"]),
    }


def page_detail(scan: ScanJob, page: Page) -> dict:
    """單頁證據：完整標題清單、圖片、連結（含檢查結果）。"""
    audit = audit_page(page)
    site_host = urlsplit(scan.normalized_url or scan.original_url).hostname or ""
    results = (scan.seo_report or {}).get("links") or {}
    disallow = ((scan.seo_report or {}).get("robots") or {}).get("disallow") or []
    rule = robots_blocks(urlsplit(audit["final_url"]).path or "/", disallow)
    if rule:
        audit["not_indexable_reasons"].append(f"robots.txt Disallow: {rule}")
        audit["indexable"] = False
    links = []
    for link in audit["links"]:
        status = results.get(link["url"])
        links.append({
            "url": link["url"],
            "anchor": link["text"] or link["label"],
            "type": classify_link(link["url"], site_host),
            "nofollow": "nofollow" in link["rel"],
            "verdict": status["verdict"] if status else "unchecked",
            "status": status["status"] if status else None,
            "chain": status["chain"] if status else [],
        })
    return {
        "page_id": page.id,
        "url": audit["final_url"],
        "requested_url": audit["url"],
        "detected_at": _iso(page.created_at),
        "status_code": audit["status_code"],
        "title": audit["title"],
        "description": audit["description"],
        "headings": audit["headings"],
        "canonical": audit["canonical"],
        "robots": audit["robots"],
        "indexable": audit["indexable"],
        "not_indexable_reasons": audit["not_indexable_reasons"],
        "lang": audit["lang"],
        "content": audit["content"],
        "images": audit["images"],
        "image_total": audit["image_total"],
        "open_graph": audit["open_graph"],
        "hreflang": audit["hreflang"],
        "has_favicon": audit["has_favicon"],
        "has_viewport": audit["has_viewport"],
        "html_bytes": audit["html_bytes"],
        "load_time_ms": audit["load_time_ms"],
        "links": links,
        "link_total": audit["link_total"],
        "checks": audit["checks"],
        "excerpt": audit["main_text"][:600],
    }
