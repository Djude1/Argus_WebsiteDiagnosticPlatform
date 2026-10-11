"""報告第 5 章「網站效能、搜尋與架構」的資料（2026-10-11）。

把網頁上已有、但報告原本沒有的資訊收進報告：PageSpeed 效能分數、SEO 分析頁的連結
（站內／子網域／站外與失效連結）、Search Console 實際搜尋詞，以及網站拓撲。
都是既有資料的整理，不重新量測、不影響分數；沒有資料的段落寫明原因。
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from django.utils import timezone

from apps.scans.models import ScanJob, SearchConsoleConnection
from apps.scans.pagespeed import CATEGORIES, CATEGORY_LABELS
from apps.scans.security.redaction import redact_pii_in_text
from apps.scans.topology import build_topology

logger = logging.getLogger(__name__)

# 報告篇幅上限：完整清單在網頁版
MAX_BROKEN_LINKS = 15
MAX_EXTERNAL_LINKS = 10
MAX_QUERIES = 15
MAX_TOPOLOGY_NODES = 60
GSC_DAYS = 28

REPORT_SCORE_LABELS = {"accessibility": "無障礙基本檢查", "seo": "SEO 基本檢查"}
LINK_TYPE_LABELS = {"internal": "站內", "subdomain": "子網域", "external": "站外"}
# 連結檢查結果分成五組畫圖；順序即圖例順序
LINK_GROUPS = (
    ("ok", "正常", {"ok", "other"}),
    ("redirect", "轉址後正常", {"redirect"}),
    ("broken", "失效", {"broken"}),
    ("unknown", "無法確認", {"restricted", "error", "timeout", "loop", "skipped"}),
    ("unchecked", "未檢查", {"unchecked"}),
)


def site_metrics(scan_job: ScanJob) -> dict:
    return {
        "performance": _performance(scan_job),
        "links": _links(scan_job),
        "search": _search(scan_job),
        "topology": _topology(scan_job),
    }


def _rating(score) -> str:
    if not isinstance(score, (int, float)):
        return ""
    if score >= 0.9:
        return "良好"
    return "需改善" if score >= 0.5 else "不佳"


def _performance(scan_job: ScanJob) -> dict:
    report = scan_job.performance_report or {}
    lab = report.get("lab") or {}
    if not lab.get("scores"):
        reason = (lab.get("error") and f"Lighthouse 量測失敗（{lab['error']}）") or (
            "本次沒有效能量測：需要勾選「使用者體驗」，且平台已設定 Google PageSpeed 金鑰。"
        )
        return {"note": reason}
    out = {
        "url": lab.get("final_url", ""),
        # 與 Argus 分數同名的兩項標成「基本檢查」，避免讀者以為兩個 SEO 分數有一個算錯
        "pages": scan_job.pages.count(),
        "scores": [
            {"label": REPORT_SCORE_LABELS.get(key, CATEGORY_LABELS[key]),
             "score": lab["scores"][key]}
            for key in CATEGORIES if key in lab["scores"]
        ],
        "metrics": [
            {"label": m["label"], "value": m.get("display", ""), "rating": _rating(m.get("score"))}
            for m in (lab.get("metrics") or {}).values()
        ],
        "opportunities": [
            {"title": o["title"], "saving": o.get("display", "")}
            for o in lab.get("opportunities") or []
        ],
    }
    field = report.get("field") or {}
    if field.get("metrics"):
        out["field_scope"] = (
            "此網址" if field.get("scope") == "url" else "整個網站（此網址資料不足）"
        )
        out["field"] = [
            {"label": name, "value": _format_field(name, item["p75"]),
             "rating": item.get("category_label") or ""}
            for name, item in field["metrics"].items()
        ]
    elif field.get("reason"):
        out["field_note"] = field["reason"]
    return out


def _format_field(name: str, value) -> str:
    if name == "CLS":
        return f"{value:.2f}"
    return f"{value / 1000:.1f} 秒" if value >= 1000 else f"{value} 毫秒"


def _links(scan_job: ScanJob) -> dict:
    if not scan_job.seo_report:
        return {"note": "本次沒有連結檢查：需要勾選「SEO」。"}
    # 函式內匯入：seo.report 會匯入 scans 的其他模組，放頂層會循環
    from apps.scans.seo.report import _analysis

    try:
        links = _analysis(scan_job)["links"]
    except Exception:  # noqa: BLE001 — 連結統計只是補充，算不出來不影響整份報告
        logger.exception("報告連結統計失敗 scan_id=%s", scan_job.id)
        return {"note": "這次無法整理連結檢查結果，請到網頁版「SEO 分析」查看。"}
    rows = links.get("rows") or []
    matrix = []
    for key, label in LINK_TYPE_LABELS.items():
        typed = [r for r in rows if r["type"] == key]
        matrix.append({
            "type": label,
            "total": len(typed),
            "groups": {
                group: sum(1 for r in typed if r["verdict"] in verdicts)
                for group, _label, verdicts in LINK_GROUPS
            },
        })
    broken = [r for r in rows if r["verdict"] == "broken"]
    external = sorted(
        (r for r in rows if r["type"] == "external"),
        key=lambda r: (-r.get("source_count", 0), r["url"]),
    )
    checked_at = links.get("checked_at")
    return {
        "checked_at": _local(checked_at),
        "total": len(rows),
        "matrix": matrix,
        "group_labels": [{"key": key, "label": label} for key, label, _ in LINK_GROUPS],
        "broken": [_link_entry(r) for r in broken[:MAX_BROKEN_LINKS]],
        "broken_total": len(broken),
        "external": [_link_entry(r) for r in external[:MAX_EXTERNAL_LINKS]],
        "external_total": len(external),
        "unchecked": links.get("unchecked") or 0,
    }


def _link_entry(row: dict) -> dict:
    status = row.get("status")
    label = next(
        (label for _key, label, verdicts in LINK_GROUPS if row["verdict"] in verdicts), ""
    )
    sources = [s["url"] for s in row.get("sources") or []]
    return {
        "url": row["url"],
        "status": f"{status}　{label}" if status else label,
        "type": LINK_TYPE_LABELS.get(row["type"], row["type"]),
        "sources": "、".join(_path(u) for u in sources[:2])
        + (f" 等 {row['source_count']} 頁" if row.get("source_count", 0) > 2 else ""),
    }


def _path(url: str) -> str:
    parts = urlsplit(url)
    return parts.path or "/"


def _local(value) -> str:
    if not value:
        return ""
    try:
        from datetime import datetime

        moment = datetime.fromisoformat(str(value))
        return timezone.localtime(moment).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""


def _search(scan_job: ScanJob) -> dict:
    """Search Console 實際搜尋詞：產生報告當下向 Google 取過去 28 天的資料。"""
    # 函式內匯入：gsc 模組在沒有設定 OAuth 時也要能載入
    from apps.scans.seo import gsc

    project = scan_job.project
    if project is None:
        return {"note": ""}
    if project.is_demo:
        # 示範專案：與網頁「搜尋關鍵字」分頁同一份示範資料（demo/gsc.py）
        from apps.scans.demo.gsc import demo_performance

        return _search_payload(demo_performance(project, GSC_DAYS), demo=True)
    connection = (
        SearchConsoleConnection.objects.filter(project=project).exclude(property_url="").first()
    )
    if not gsc.is_enabled() or connection is None:
        return {"note": "這個網站專案尚未連接 Google Search Console；在「SEO 分析 → 搜尋關鍵字」"
                        "連接後，報告會列出實際搜尋詞、點擊與曝光。"}
    try:
        data = gsc.performance(connection, GSC_DAYS)
    except Exception:  # noqa: BLE001 — Google 暫時無法回應時報告照樣產生，只說明原因
        logger.warning("報告取得 Search Console 資料失敗 scan_id=%s", scan_job.id)
        return {"note": "產生報告時無法取得 Search Console 資料（授權失效或 Google 暫時無法回應），"
                        "請到網頁版「SEO 分析 → 搜尋關鍵字」重新連接後再下載報告。"}
    return _search_payload(data)


def _search_payload(data: dict, demo: bool = False) -> dict:
    totals = data.get("totals") or {}
    queries = data.get("queries") or []
    return {
        "property": data.get("property", "") + ("（示範資料）" if demo else ""),
        "period": f"{data.get('start', '')}～{data.get('end', '')}",
        "fetched_at": timezone.localtime().strftime("%Y-%m-%d %H:%M"),
        "totals": {
            "clicks": totals.get("clicks", 0),
            "impressions": totals.get("impressions", 0),
            "ctr": totals.get("ctr", 0),
            "queries": len(queries),
        },
        "trend": [
            {"date": t["date"], "clicks": t["clicks"], "impressions": t["impressions"]}
            for t in data.get("trend") or []
        ],
        "queries": [
            {
                # 搜尋詞是訪客輸入的文字，可能夾帶 Email、電話：與證據同樣先遮罩
                "query": redact_pii_in_text(q["query"]),
                "clicks": q["clicks"],
                "impressions": q["impressions"],
                "ctr": q["ctr"],
                "position": q["position"],
                "page": q.get("page", ""),
            }
            for q in queries[:MAX_QUERIES]
        ],
    }


def _topology(scan_job: ScanJob) -> dict:
    graph = build_topology(scan_job)
    nodes = sorted(graph["nodes"], key=lambda n: (n["depth"], n["id"]))[:MAX_TOPOLOGY_NODES]
    if len(nodes) < 2:
        return {"note": "本次只掃描了一個頁面，沒有可以畫的網站結構。"}
    kept = {n["id"] for n in nodes}
    return {
        "nodes": [
            {
                "id": n["id"],
                "label": _path(n["url"]),
                "depth": n["depth"],
                "tone": "blocked" if n["blocked"] or (n["status_code"] or 0) >= 400 else n["tone"],
                "findings": n["finding_count"],
            }
            for n in nodes
        ],
        "edges": [
            [e["source"], e["target"]] for e in graph["edges"]
            if e["source"] in kept and e["target"] in kept
        ],
        "total": len(graph["nodes"]),
    }
