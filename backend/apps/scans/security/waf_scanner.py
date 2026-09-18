"""WAF／防護機制封鎖偵測（被動）：統計已落地 Page 的 403/429 與 challenge 特徵。

當一次掃描有明顯被目標站防護機制（WAF、速率限制、CAPTCHA challenge）阻擋的
跡象時，產生「至多一則」info finding 向使用者說明結果可能不完整；
低於閾值視為正常雜訊不產出。純讀取既有資料、不發任何網路請求、例外 silent-fail。
"""
from apps.scans.models import Finding
from apps.scans.scanners import make_finding

RULE_ID = "waf_block_detected"

# title 特徵：防護／限流攔截頁的標題文案幾乎固定，誤判率極低。
# 刻意只在 title 比對這些短語——若掃進正文，正常文章提及同名短語會被誤判。
_TITLE_MARKERS = (
    "just a moment",       # Cloudflare challenge 頁標題「Just a moment...」
    "attention required",  # Cloudflare 封鎖頁標題「Attention Required! | Cloudflare」
    "access denied",       # AWS WAF / CloudFront 等封鎖頁標題「Access denied」
    "too many requests",   # 速率限制頁標題「Too Many Requests」
    "ddos protection",     # Cloudflare／Sucuri 等 DDoS 防護頁標題
)

# HTML 特徵：防護機制注入的技術標記（DOM class／載入器路徑），正常內容不會出現。
# 刻意不收純 "captcha"：正常網頁的表單常內嵌 reCAPTCHA，會把正常頁誤判成防護頁。
_BODY_MARKERS = (
    "cf-chl",              # Cloudflare challenge 相關 DOM（cf-chl-bypass 等）
    "challenge-platform",  # CF challenge 載入器路徑（/cdn-cgi/challenge-platform/）
    "cf_captcha",          # CF 舊式 captcha 標記（與 crawler.py 同款）
)

# 觸發閾值（兩者任一）：被 403/429 的頁面佔嘗試頁面 ≥ 30%；challenge 特徵頁 ≥ 2
_BLOCK_RATIO_THRESHOLD = 0.30
_CHALLENGE_PAGE_THRESHOLD = 2


def _has_challenge_signature(title: str | None, html: str | None) -> bool:
    """判斷單頁的 title／html 是否含防護機制攔截頁特徵。"""
    lowered_title = (title or "").lower()
    if any(marker in lowered_title for marker in _TITLE_MARKERS):
        return True
    lowered_html = (html or "").lower()
    return any(marker in lowered_html for marker in _BODY_MARKERS)


def _summarize(pages) -> dict:
    """統計被 403/429 與 challenge 特徵的頁數。

    pages 為 (status_code, title, html) 的 iterable（如 Page queryset 的
    values_list），純迭代計數、不依賴網路，方便單測。
    """
    stats = {"pages_total": 0, "pages_403": 0, "pages_429": 0, "pages_challenge": 0}
    for status_code, title, html in pages:
        stats["pages_total"] += 1
        if status_code == 403:
            stats["pages_403"] += 1
        elif status_code == 429:
            stats["pages_429"] += 1
        if _has_challenge_signature(title, html):
            stats["pages_challenge"] += 1
    stats["blocked_ratio"] = (
        (stats["pages_403"] + stats["pages_429"]) / stats["pages_total"]
        if stats["pages_total"]
        else 0.0
    )
    return stats


def _should_report(stats: dict) -> bool:
    """任一訊號達閾值即回 True；單頁被擋屬正常雜訊，不觸發。"""
    if not stats["pages_total"]:
        return False
    if stats["blocked_ratio"] >= _BLOCK_RATIO_THRESHOLD:
        return True
    return stats["pages_challenge"] >= _CHALLENGE_PAGE_THRESHOLD


def detect_waf_block(scan_job) -> dict | None:
    """偵測掃描是否遭目標網站防護機制部分阻擋。

    回傳單一 info finding dict（make_finding 格式，由 tasks.py 落地）；
    未達閾值、無頁面或本次掃描已產出過（冪等，同一掃描至多一則）回 None。
    不修改 ScanJob 狀態（狀態機僅在 tasks.py 推進）。
    """
    try:
        if Finding.objects.filter(scan_job=scan_job, rule_id=RULE_ID).exists():
            return None
        stats = _summarize(scan_job.pages.values_list("status_code", "title", "html"))
        if not _should_report(stats):
            return None
        ratio_pct = round(stats["blocked_ratio"] * 100)
        description = (
            f"本次掃描共嘗試 {stats['pages_total']} 個頁面，其中 "
            f"{stats['pages_403']} 頁回傳 HTTP 403、{stats['pages_429']} 頁回傳 "
            f"HTTP 429（合計佔 {ratio_pct}%），另有 {stats['pages_challenge']} 頁"
            "偵測到防護驗證頁特徵（如 Cloudflare challenge、CAPTCHA、速率限制頁）。"
            "這表示掃描請求已部分觸發目標網站的 WAF／防護機制，"
            "未被阻擋的頁面仍照常分析。"
        )
        remediation = (
            "本次掃描結果可能不完整，解讀報告時請留意。建議："
            "1) 降低掃描頻率或改於離峰時段重新掃描；"
            "2) 若您是網站管理員，可將本平台的掃描來源 IP／User-Agent "
            "加入 WAF／防火牆白名單後重新掃描；"
            "3) 被阻擋的頁面未納入分析，重新掃描可補齊涵蓋範圍。"
        )
        return make_finding(
            category="security",
            severity="info",
            rule_id=RULE_ID,
            title="掃描遭目標網站防護機制部分阻擋",
            description=description,
            remediation=remediation,
            evidence=(
                f"統計：嘗試 {stats['pages_total']} 頁；"
                f"HTTP 403={stats['pages_403']}、429={stats['pages_429']}"
                f"（合計佔 {ratio_pct}%）；challenge 特徵 {stats['pages_challenge']} 頁"
            ),
            evidence_json={
                "pages_total": stats["pages_total"],
                "pages_403": stats["pages_403"],
                "pages_429": stats["pages_429"],
                "blocked_ratio": round(stats["blocked_ratio"], 4),
                "pages_challenge": stats["pages_challenge"],
            },
            impact_area="crawl_coverage",
            confidence=1.0,
        )
    except Exception:
        return None
