"""自家被動檢查（ADR-0005 §2）：把 ZAP 被動的獨有規則移植成 Argus 原生檢查。

退掉 `zap_passive` 階段後，這幾條原本只有 ZAP 會報的被動問題改由這裡產出——全部只讀爬蟲
已抓到的頁面 HTML／回應，零新增請求：

- `analyze_mixed_content`：HTTPS 頁面載入 http:// 子資源（ZAP 10040）。
- `analyze_sensitive_url_params`：網址查詢字串帶 password／token／apikey 等敏感參數（ZAP 10024）。
- `analyze_error_disclosure`：頁面回應含堆疊追蹤／框架除錯頁（ZAP 10023／90022；重用 api_scanner
  的堆疊特徵，但對象是一般頁面 HTML，api_scanner 只看 API 回應）。

Permissions-Policy 缺失（ZAP 10063）移植到 `header_scanner`（屬標頭檢查）。
ZAP 10027「註解可疑字詞」刻意不移植：低訊號、高誤報，秘鑰已由 secret_scanner 覆蓋。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from apps.scans.scanners import make_finding
from apps.scans.security.api_scanner import _stack_kind
from apps.scans.security.redaction import redact_pii_in_text, redact_url_query_values

_MAX_LISTED = 10

# 子資源標籤分類：active（會執行／套用，風險高）vs passive（僅顯示）
_ACTIVE_TAGS = {"script", "iframe", "object", "embed"}
_PASSIVE_TAGS = {"img", "audio", "video", "source", "track"}
_URL_ATTRS = ("src", "href", "data", "poster")


class _MixedContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.active: list[str] = []
        self.passive: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        url = next((a[k] for k in _URL_ATTRS if a.get(k, "").lower().startswith("http://")), "")
        if not url:
            return
        if tag in _ACTIVE_TAGS:
            self.active.append(url)
        elif tag == "link":
            # 樣式表是 active mixed content（會被套用）；icon／preconnect 等當 passive
            rel = a.get("rel", "").lower()
            (self.active if "stylesheet" in rel else self.passive).append(url)
        elif tag in _PASSIVE_TAGS:
            self.passive.append(url)


def _https_pages(pages: list[dict]) -> list[dict]:
    out = []
    for page in pages or []:
        url = page.get("final_url") or page.get("url") or ""
        if url.lower().startswith("https://") and page.get("html"):
            out.append(page)
    return out


def analyze_mixed_content(pages: list[dict]) -> list[dict]:
    """HTTPS 頁面載入 http:// 子資源（混合內容）。整站合併成一筆，active 有命中就中風險。"""
    active: list[str] = []
    passive: list[str] = []
    for page in _https_pages(pages):
        parser = _MixedContentParser()
        try:
            parser.feed(page["html"])
        except Exception:  # noqa: BLE001 — 解析失敗略過該頁
            continue
        active.extend(parser.active)
        passive.extend(parser.passive)
    active = list(dict.fromkeys(active))
    passive = list(dict.fromkeys(passive))
    if not active and not passive:
        return []
    severity = "medium" if active else "low"
    listed = (active + passive)[:_MAX_LISTED]
    evidence = "\n".join(f"• {redact_url_query_values(u)}" for u in listed)
    extra = len(active) + len(passive) - len(listed)
    if extra > 0:
        evidence += f"\n…另 {extra} 個"
    return [make_finding(
        category="security",
        severity=severity,
        rule_id="security-mixed-content",
        title="HTTPS 頁面載入 HTTP 資源（混合內容）",
        description=(
            f"在 HTTPS 頁面偵測到 {len(active) + len(passive)} 個以 http:// 載入的資源"
            f"（其中 {len(active)} 個是腳本／樣式表等會執行或套用的資源）。"
            "混合內容會讓這些資源以未加密方式傳輸，可被中間人竄改或竊聽；"
            "瀏覽器通常會封鎖 active 類資源，導致頁面功能壞掉。"
        ),
        remediation="把這些資源網址改成 https://（或相對路徑），確保全站只走加密連線。",
        evidence=evidence,
        evidence_source="rule_engine",
        impact_area="vulnerability",
        confidence=0.95,
        priority_score=35.0 if severity == "medium" else 20.0,
    )]


# 網址查詢字串裡不該出現的敏感參數名（只比對參數名稱，值一律遮罩）
_SENSITIVE_PARAM = re.compile(
    r"^(?:password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|api[_-]?key|apikey"
    r"|secret|client[_-]?secret|session[_-]?id|sessionid|auth|authorization|jwt)$",
    re.I,
)
# 可能出現網址的屬性（頁面本身網址＋連結＋GET 表單 action）
_HREF_RE = re.compile(r"""(?:href|action|src)\s*=\s*["']([^"']+)["']""", re.I)


def _sensitive_params(url: str) -> list[str]:
    try:
        query = urlsplit(url).query
    except ValueError:
        return []
    if not query:
        return []
    return [k for k in parse_qs(query, keep_blank_values=True) if _SENSITIVE_PARAM.match(k)]


def analyze_sensitive_url_params(pages: list[dict]) -> list[dict]:
    """網址查詢字串帶 password／token／apikey 等敏感參數——會被記進伺服器日誌、瀏覽紀錄、Referer。"""
    hits: dict[str, str] = {}  # 遮罩後網址 → 命中的參數名
    for page in pages or []:
        candidates = [page.get("final_url") or page.get("url") or ""]
        html = page.get("html") or ""
        if html:
            candidates.extend(_HREF_RE.findall(html)[:200])
        for raw in candidates:
            if "?" not in raw:
                continue
            params = _sensitive_params(raw)
            if params:
                safe = redact_pii_in_text(redact_url_query_values(raw))
                hits.setdefault(safe, ", ".join(sorted(set(params))))
            if len(hits) >= _MAX_LISTED:
                break
        if len(hits) >= _MAX_LISTED:
            break
    if not hits:
        return []
    evidence = "\n".join(f"• {url}（參數：{names}）" for url, names in hits.items())
    return [make_finding(
        category="security",
        severity="medium",
        rule_id="security-sensitive-url-param",
        title="網址查詢字串含敏感參數",
        description=(
            "偵測到把密碼／權杖／金鑰等敏感值放在網址查詢字串裡。網址會被記進伺服器存取日誌、"
            "瀏覽器歷史、CDN 快取，並透過 Referer 標頭洩漏給第三方網站，等於把機密攤在多處。"
        ),
        remediation="敏感值改用 POST 請求內容或標頭傳遞，不要放在網址參數；並撤換已外洩的權杖。",
        evidence=evidence,
        evidence_source="rule_engine",
        impact_area="information_exposure",
        confidence=0.85,
        priority_score=40.0,
    )]


def analyze_error_disclosure(pages: list[dict]) -> list[dict]:
    """頁面回應含堆疊追蹤／框架除錯頁（重用 api_scanner 的堆疊特徵，對象是一般頁面 HTML）。"""
    hits: list[tuple[str, str]] = []  # (遮罩後網址, 框架)
    seen: set[str] = set()
    for page in pages or []:
        html = page.get("html") or ""
        if not html:
            continue
        framework, _snippet = _stack_kind(html)
        if not framework:
            continue
        url = page.get("final_url") or page.get("url") or ""
        safe = redact_url_query_values(url)
        if safe in seen:
            continue
        seen.add(safe)
        hits.append((safe, framework))
        if len(hits) >= _MAX_LISTED:
            break
    if not hits:
        return []
    frameworks = ", ".join(sorted({f for _u, f in hits}))
    evidence = "\n".join(f"• {url}（{fw}）" for url, fw in hits)
    return [make_finding(
        category="security",
        severity="medium",
        rule_id="security-error-disclosure",
        title="頁面回應洩漏堆疊追蹤或除錯資訊",
        description=(
            f"偵測到頁面回應含 {frameworks} 的堆疊追蹤／除錯訊息。這類訊息會洩漏檔案路徑、"
            "框架版本與程式內部結構，替攻擊者省下偵察功夫，也常伴隨除錯模式開啟的其他風險。"
        ),
        remediation=(
            "正式環境關閉除錯模式（如 Django DEBUG=False、PHP display_errors=Off），"
            "錯誤頁只顯示一般訊息，詳細錯誤只寫進伺服器記錄。"
        ),
        evidence=evidence,
        evidence_source="rule_engine",
        impact_area="information_exposure",
        confidence=0.9,
        priority_score=40.0,
    )]


def analyze_passive_html(pages: list[dict]) -> list[dict]:
    """彙整本模組所有被動檢查。任何子檢查例外不影響其他。"""
    findings: list[dict] = []
    for fn in (analyze_mixed_content, analyze_sensitive_url_params, analyze_error_disclosure):
        try:
            findings.extend(fn(pages))
        except Exception:  # noqa: BLE001 — 單一檢查失敗不影響其他
            continue
    return findings
