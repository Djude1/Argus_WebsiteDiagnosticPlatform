"""連結檢查覆蓋與健康度趨勢（roadmap §11 第 2、3 項）。

- 覆蓋：每個連結歸到一種狀態——已確認（有明確結果）、對方限制檢查、逾時、無法連線、
  非公開位址、超過數量上限、時間用完。「沒檢查到」不能當成「沒有失效」。
- 趨勢：和同一個網站專案上一次完成的掃描比，標記失效連結是新壞掉、持續失效、已確認恢復，
  或本次無法確認。只有這次真的檢查過、而且正常（含轉址後正常），才算恢復；這次沒檢查、
  逾時、被拒絕或頁面上已經找不到這個連結，都只能說「無法確認」。

爬蟲已直接造訪的頁面不會再做連結檢查（`seo/collect.py`），所以兩次掃描都要把爬蟲量到的
HTTP 狀態併進來，才不會把「這次由爬蟲確認正常」誤判成「無法確認」。
"""

from __future__ import annotations

# 有明確結果的判定
CHECKED_VERDICTS = {"ok", "redirect", "broken", "loop", "other"}
BROKEN_VERDICTS = {"broken", "loop"}
HEALTHY_VERDICTS = {"ok", "redirect"}

COVERAGE_LABELS = {
    "checked": "已確認",
    "restricted": "對方限制檢查",
    "timeout": "逾時",
    "error": "無法連線",
    "skipped": "非公開位址",
    "over_limit": "超過數量上限",
    "budget_exhausted": "時間用完",
}
TREND_LABELS = {
    "new": "新壞掉",
    "persisting": "持續失效",
    "recovered": "已確認恢復",
    "unconfirmed": "本次無法確認",
}


def link_coverage(report: dict) -> dict[str, int]:
    """連結檢查結果依覆蓋狀態計數（舊報告沒有未檢查原因時，未檢查數全算超過數量上限）。"""
    counts = dict.fromkeys(COVERAGE_LABELS, 0)
    for row in (report.get("links") or {}).values():
        verdict = row.get("verdict")
        if verdict in CHECKED_VERDICTS:
            counts["checked"] += 1
        elif verdict in counts:
            counts[verdict] += 1
        else:
            counts["error"] += 1
    reasons = report.get("unchecked_reasons")
    if reasons is None:
        counts["over_limit"] = report.get("unchecked", 0)
    else:
        counts["over_limit"] = reasons.get("over_limit", 0)
        counts["budget_exhausted"] = reasons.get("budget_exhausted", 0)
    return counts


def coverage_text(counts: dict[str, int]) -> str:
    """覆蓋摘要：只列沒有明確結果的狀態，例如「逾時 2、超過數量上限 30」。"""
    return "、".join(
        f"{label} {counts[key]}"
        for key, label in COVERAGE_LABELS.items()
        if key != "checked" and counts.get(key)
    )


def crawled_verdicts(pages) -> dict[str, str]:
    """爬蟲已直接造訪、沒有轉址的頁面：依 HTTP 狀態換成連結判定（與 seo/report 相同規則）。

    pages 是 [(url, final_url, status_code)]。
    """
    verdicts = {}
    for url, final_url, status in pages:
        if status is None or (final_url or url) != url:
            continue
        verdicts[url] = "ok" if status < 300 else ("broken" if status >= 400 else "other")
    return verdicts


def effective_verdicts(report: dict | None, crawled: dict[str, str]) -> dict[str, str]:
    verdicts = dict(crawled)
    for url, row in ((report or {}).get("links") or {}).items():
        verdicts[url] = row.get("verdict", "")
    return verdicts


def link_trend(
    current: dict[str, str], previous: dict[str, str], *, previous_scan_id: int,
    previous_checked_at: str | None,
) -> dict:
    """失效連結的趨勢。current／previous 是 effective_verdicts 的結果。"""
    items: dict[str, str] = {}
    for url, verdict in current.items():
        if verdict in BROKEN_VERDICTS:
            items[url] = "persisting" if previous.get(url) in BROKEN_VERDICTS else "new"
    for url, verdict in previous.items():
        if verdict in BROKEN_VERDICTS and url not in items:
            items[url] = "recovered" if current.get(url) in HEALTHY_VERDICTS else "unconfirmed"
    return {
        "previous_scan_id": previous_scan_id,
        "previous_checked_at": previous_checked_at,
        "items": dict(sorted(items.items())),
        "counts": {key: sum(1 for v in items.values() if v == key) for key in TREND_LABELS},
    }
