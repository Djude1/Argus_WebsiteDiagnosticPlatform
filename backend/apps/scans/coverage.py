"""掃描覆蓋契約（Coverage Contract，docs/scan-upgrade-roadmap.md P0-A）。

每次掃描逐項記錄「哪些檢查實際跑完、哪些失敗或被略過」，存進 `ScanJob.coverage`：

```
{
  "version": 1,
  "checks": {"nuclei": {"status": "failed", "category": "security",
                        "reason": "TimeoutError", "keys": ["nuclei-xss", ...]}, ...},
  "categories": {"security": "partial", "seo": "completed", ...}
}
```

用途有三：
1. **計分**：某維度的檢查全部沒跑完時不評分（顯示未評估）；部分失敗時照常評分但標示「部分評估」，
   工具失敗不能被呈現成「0 項問題」。
2. **歷史比較**：前次有、這次沒有的問題，只有在「產生它的同一項檢查本次完整跑完、且受影響頁面
   本次有檢查到」時才標成已修好（`resolved`）；否則是本次未觀察到／未檢查／被阻擋／無法判定。
3. **報告與 API**：讓收件者看得到哪些檢查不完整。

只讀寫 JSON，不碰 `ScanJob.status`、不呼叫 billing。
"""

from __future__ import annotations

from collections.abc import Iterable

COVERAGE_VERSION = 1

COMPLETED = "completed"
PARTIAL = "partial"
FAILED = "failed"
BLOCKED = "blocked"
SKIPPED = "skipped"
NOT_APPLICABLE = "not_applicable"

# 檢查名稱 → 所屬維度（None＝不屬於單一維度，例如爬取）
CHECK_CATEGORIES: dict[str, str | None] = {
    "crawl": None,
    "page_seo": "seo",
    "page_aeo": "aeo",
    "page_geo": "geo",
    "page_ux": "ux",
    "page_security": "security",
    "aeo_answers": "aeo",
    "site_security": "security",
    "nuclei": "security",
    "katana": "security",
    "deep_security": "security",
    "exposure_robots": "security",
    "exposure_probe": "security",
    "geo_site": "geo",
    "seo_links": "seo",
    "agent": "security",
    "agent_ux": "ux",
    "axe": "ux",
    "kali": "security",
    # 外部指標不併入 Argus 分數，也不影響維度的覆蓋狀態；失敗時仍列在「未完整完成的檢查」
    "pagespeed": None,
    "zap_passive": "security",
}

CHECK_LABELS: dict[str, str] = {
    "crawl": "頁面爬取",
    "page_seo": "逐頁 SEO 分析",
    "page_aeo": "逐頁 AEO 分析",
    "page_geo": "逐頁 GEO 分析",
    "page_ux": "逐頁使用體驗分析",
    "page_security": "逐頁資安分析",
    "aeo_answers": "AEO 問答檢測",
    "site_security": "站台層級資安檢查",
    "nuclei": "Nuclei 主動弱點掃描",
    "katana": "Katana 端點探索",
    "deep_security": "深度被動資安檢查",
    "exposure_robots": "robots.txt 敏感路徑",
    "exposure_probe": "敏感檔案主動探測",
    "geo_site": "站台 GEO 訊號",
    "seo_links": "SEO 連結與網址檢查",
    "agent": "AI 深度資安測試",
    "agent_ux": "AI 擬真使用者測試",
    "axe": "axe-core 無障礙檢查",
    "pagespeed": "PageSpeed Insights（Lighthouse／CrUX）",
    "zap_passive": "OWASP ZAP 被動分析",
    "kali": "Kali 主動驗證",
}

# 「有跑但沒完整跑完」的狀態：維度標示部分評估，前次問題不能判定已修好
_INCOMPLETE = {PARTIAL, FAILED, BLOCKED}
# 沒有執行的狀態
_NOT_RUN = {SKIPPED, NOT_APPLICABLE}

# 不經 ScanRunContext.record 寫入的 finding（agent runner 直接落 DB），以規則前綴對回檢查
_KEY_PREFIX_CHECKS = (
    ("AGENT_UX_", "agent_ux"),
    ("agent-", "agent"),
    ("kali-", "kali"),
)


def issue_key(rule_id: str | None, category: str, title: str) -> str:
    """問題的追蹤單位：同一條規則；沒有規則代號就用「分類:標題」。

    projects.py 也從這裡匯入，問題的合併與歷史比較用同一個定義。
    """
    return rule_id or f"{category}:{title}"


class ScanCoverage:
    """一次掃描執行期間累積的覆蓋紀錄。"""

    def __init__(self) -> None:
        self._checks: dict[str, dict] = {}

    def mark(self, check: str, status: str, reason: str = "") -> None:
        """記錄某項檢查的結果；同一項檢查以最後一次為準，但已記錄的問題代號保留。"""
        entry = self._checks.setdefault(
            check, {"category": CHECK_CATEGORIES.get(check), "keys": set()}
        )
        entry["status"] = status
        entry["reason"] = reason

    def add_findings(self, check: str, findings: Iterable[dict]) -> None:
        """記下這項檢查產生了哪些問題（歷史比較時用來找回「是誰產生的」）。"""
        entry = self._checks.setdefault(
            check,
            {"category": CHECK_CATEGORIES.get(check), "keys": set(), "status": COMPLETED,
             "reason": ""},
        )
        for finding in findings:
            entry["keys"].add(
                issue_key(finding.get("rule_id"), finding.get("category", ""),
                          finding.get("title", ""))
            )

    def status_of(self, check: str) -> str | None:
        entry = self._checks.get(check)
        return entry.get("status") if entry else None

    def to_json(self, categories: Iterable[str]) -> dict:
        checks = {
            name: {
                "status": entry.get("status", COMPLETED),
                "category": entry["category"],
                "reason": entry.get("reason", ""),
                "keys": sorted(entry["keys"]),
            }
            for name, entry in sorted(self._checks.items())
        }
        return {
            "version": COVERAGE_VERSION,
            "checks": checks,
            "categories": {
                category: category_status(checks, category) for category in sorted(categories)
            },
        }


def category_status(checks: dict, category: str) -> str:
    """維度的覆蓋狀態：completed／partial／not_tested。

    爬取本身不完整（有頁面失敗或被阻擋）會讓逐頁分析的維度都只算部分評估。
    """
    statuses = [
        entry["status"] for entry in checks.values() if entry.get("category") == category
    ]
    ran = [status for status in statuses if status not in _NOT_RUN]
    if not ran or all(status in {FAILED, BLOCKED} for status in ran):
        return "not_tested"
    crawl = (checks.get("crawl") or {}).get("status")
    if any(status in _INCOMPLETE for status in ran) or crawl in _INCOMPLETE:
        return PARTIAL
    return COMPLETED


def incomplete_checks(coverage: dict | None) -> list[dict]:
    """沒有完整跑完的檢查（報告與前端提示用），依名稱排序。"""
    checks = (coverage or {}).get("checks") or {}
    return [
        {
            "check": name,
            "label": CHECK_LABELS.get(name, name),
            "status": entry["status"],
            "reason": entry.get("reason", ""),
        }
        for name, entry in sorted(checks.items())
        if entry.get("status") in _INCOMPLETE
    ]


# ---------------------------------------------------------------------------
# 歷史比較：前次有、這次沒有的問題是什麼狀態
# ---------------------------------------------------------------------------

RESOLVED = "resolved"
NOT_OBSERVED = "not_observed"
NOT_TESTED = "not_tested"
INCONCLUSIVE = "inconclusive"

ABSENT_STATUS_LABELS = {
    RESOLVED: "已修好",
    NOT_OBSERVED: "本次未觀察到",
    NOT_TESTED: "本次未檢查",
    BLOCKED: "本次被阻擋",
    INCONCLUSIVE: "無法判定",
}


def _check_for_key(coverage: dict | None, key: str) -> str | None:
    for name, entry in ((coverage or {}).get("checks") or {}).items():
        if key in (entry.get("keys") or []):
            return name
    for prefix, check in _KEY_PREFIX_CHECKS:
        if key.startswith(prefix):
            return check
    return None


def absent_issue_status(
    *,
    previous_coverage: dict | None,
    current_coverage: dict | None,
    key: str,
    category: str,
    urls: Iterable[str],
    analysed_urls: set[str],
) -> str:
    """前次有、本次沒出現的問題屬於哪一種狀態。

    只有「產生它的同一項檢查本次完整跑完」且「受影響頁面本次有完整分析到」才是 resolved。
    舊掃描沒有覆蓋紀錄時無從判斷，一律 not_observed（不能冒稱已修好）。
    """
    current_checks = (current_coverage or {}).get("checks")
    if not current_checks:
        return NOT_OBSERVED
    check = _check_for_key(previous_coverage, key)
    if check is not None:
        status = (current_checks.get(check) or {}).get("status")
        if status is None or status in _NOT_RUN:
            return NOT_TESTED
        if status == BLOCKED:
            return BLOCKED
        if status == FAILED:
            return INCONCLUSIVE
        if status == PARTIAL:
            return NOT_OBSERVED
    else:
        # 前次掃描沒有覆蓋紀錄：退回以維度判斷
        category_state = ((current_coverage or {}).get("categories") or {}).get(category)
        if category_state != COMPLETED:
            return NOT_TESTED if category_state == "not_tested" else NOT_OBSERVED
    url_list = [url for url in urls if url]
    if url_list and not analysed_urls.intersection(url_list):
        return NOT_OBSERVED
    return RESOLVED
