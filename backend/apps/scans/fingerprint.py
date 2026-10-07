"""網站特徵（fingerprint）：Smart Scan 階段 1，只記錄、不改任何掃描決策（ADR-0004 §2、§7）。

只消費爬取階段已經取得的訊號（Pre-scan Signals），**不發任何請求**：

- 每頁的 HTML、回應標頭、狀態碼（`crawl_site` 回傳的頁面）
- 爬蟲被動攔截的 same-origin XHR／fetch 端點（`discovered_endpoints`）

判斷不到的特徵一律是 `None`，並在 `completeness` 寫明原因，**不當成「沒有」**：
登入頁可能在沒爬到的頁面、API 可能只在登入後才呼叫。

completeness 的值：
- `complete`：有直接證據
- `not_observed`：已爬到的頁面完整分析過，但沒看到
- `partial`：沒看到，而且爬取不完整（有頁面擷取失敗或達頁數上限），或訊號來源本來就只有一部分
  （例如邊緣服務在這個階段只看標頭、沒查 DNS）
- `unavailable`：沒有任何可分析的頁面

信心值 `confidence` 只在有證據時出現（0–1）。階段 2 的動態加掃只會在高信心
（≥ 0.8 或兩個獨立證據）時觸發，所以這裡寧可給低分也不誇大。
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

from apps.scans.security.infra_scanner import detect_edge
from apps.scans.tech_stack import MAX_HTML_CHARS

VERSION = 1
MAX_URLS = 10

# CMS：標記必須出現在 src／href 屬性或 meta generator 裡，正文提到路徑（教學文章）不算
_ATTR = r"""(?:src|href)\s*=\s*["'][^"']*"""
_CMS_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("WordPress", (_ATTR + r"/wp-(?:content|includes)/", r"""rel=["']https://api\.w\.org/""")),
    ("Drupal", (_ATTR + r"/sites/(?:default|all)/(?:files|modules|themes)/",
                r"""data-drupal-selector=|drupalSettings""")),
    ("Joomla", (_ATTR + r"/media/(?:jui|system)/js/", _ATTR + r"/components/com_")),
    ("Shopify", (_ATTR + r"cdn\.shopify\.com/",)),
    ("Wix", (_ATTR + r"static\.wixstatic\.com/",)),
    ("Squarespace", (_ATTR + r"static1\.squarespace\.com/",)),
)
_GENERATOR = re.compile(
    r"""<meta[^>]+name=["']generator["'][^>]+content=["']([^"']{2,60})["']""", re.IGNORECASE
)
_FRAMEWORK_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("Next.js", _ATTR + r"/_next/static/|id=[\"']__NEXT_DATA__[\"']"),
    ("Nuxt", _ATTR + r"/_nuxt/|window\.__NUXT__"),
    ("Gatsby", r"id=[\"']___gatsby[\"']"),
    ("Angular", r"\sng-version=[\"']"),
    ("Vue.js", r"\sdata-v-[0-9a-f]{6,8}[\s=>]"),
    ("React", r"\sdata-reactroot[\s=>]"),
)
_POWERED_BY = {"php": "PHP", "asp.net": "ASP.NET", "express": "Express", "next.js": "Next.js"}
_SERVER_PRODUCTS = (
    "nginx", "apache", "microsoft-iis", "litespeed", "openresty", "caddy", "gunicorn",
    "cloudflare", "vercel", "netlify",
)

_INPUT = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
_TYPE_PASSWORD = re.compile(r"""\btype\s*=\s*["']?password\b""", re.IGNORECASE)
_TYPE_FILE = re.compile(r"""\btype\s*=\s*["']?file\b""", re.IGNORECASE)
_HIDDEN_CONTAINER = re.compile(r"<template\b.*?</template>", re.IGNORECASE | re.DOTALL)

# 看起來是 API 的端點路徑（XHR 也可能是載入 HTML 片段，那種不算 API 證據）
_API_PATH = re.compile(
    r"(?:^|/)(?:api|graphql|wp-json|rest|v\d+)(?:/|$)|\.json$|/odata/", re.IGNORECASE
)
_AUTH_SCHEMES = ("basic", "bearer", "digest", "negotiate", "ntlm")


@dataclass(frozen=True)
class SiteFingerprint:
    cms: str | None = None
    frameworks: tuple[str, ...] = ()
    server: str | None = None
    edge: str | None = None
    has_login: bool | None = None
    login_urls: tuple[str, ...] = ()
    has_api: bool | None = None
    api_urls: tuple[str, ...] = ()
    has_upload: bool | None = None
    auth_scheme: str | None = None
    confidence: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    completeness: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, tuple):
                data[key] = list(value)
        data["evidence"] = {k: list(v) for k, v in self.evidence.items()}
        return data


def _usable(page: dict) -> bool:
    status = page.get("status_code") or 0
    return 0 < status < 400 and not page.get("blocked_reason")


def _html(page: dict) -> str:
    text = (page.get("rendered_dom") or page.get("html") or "")[:MAX_HTML_CHARS]
    # <template> 裡的元素不會顯示，不算頁面上真的有登入或上傳表單
    return _HIDDEN_CONTAINER.sub("", text)


def _headers(page: dict) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (page.get("headers") or {}).items()}


def _pages_conf(count: int, strong: float = 0.9, weak: float = 0.7) -> float:
    """同一個標記出現在幾頁：兩頁以上算兩個獨立證據。"""
    return strong if count >= 2 else weak


class _Collector:
    def __init__(self) -> None:
        self.evidence: dict[str, list[str]] = {}
        self.confidence: dict[str, float] = {}

    def add(self, key: str, text: str, confidence: float) -> None:
        bucket = self.evidence.setdefault(key, [])
        if text not in bucket and len(bucket) < 5:
            bucket.append(text)
        self.confidence[key] = round(max(self.confidence.get(key, 0.0), confidence), 2)


def _detect_cms(pages: list[dict], out: _Collector) -> str | None:
    hits: dict[str, list[str]] = {}
    generator_hit: dict[str, str] = {}
    for page in pages:
        html = _html(page)
        for name, patterns in _CMS_SIGNATURES:
            if any(re.search(p, html, re.IGNORECASE) for p in patterns):
                hits.setdefault(name, []).append(page.get("final_url") or page.get("url", ""))
        generator = _GENERATOR.search(html)
        if generator:
            product = generator.group(1).strip()
            for name, _patterns in _CMS_SIGNATURES:
                if product.lower().startswith(name.lower()):
                    generator_hit.setdefault(name, product)
    candidates = set(hits) | set(generator_hit)
    if not candidates:
        return None
    # 多個 CMS 同時出現時（例如嵌入別人的內容），取證據最多的
    best = max(candidates, key=lambda n: (len(hits.get(n, [])) + 2 * (n in generator_hit), n))
    count = len(hits.get(best, []))
    if count:
        out.add("cms", f"{count} 頁引用 {best} 特有的路徑（例如 {hits[best][0]}）",
                _pages_conf(count))
    if best in generator_hit:
        # meta generator 加上路徑標記＝兩個獨立證據
        out.add("cms", f"meta generator：{generator_hit[best]}", 0.95 if count else 0.8)
    return best


def _detect_frameworks(pages: list[dict], out: _Collector) -> tuple[str, ...]:
    found: dict[str, int] = {}
    for page in pages:
        html = _html(page)
        for name, pattern in _FRAMEWORK_SIGNATURES:
            if re.search(pattern, html, re.IGNORECASE):
                found[name] = found.get(name, 0) + 1
        powered = _headers(page).get("x-powered-by", "").lower()
        for marker, name in _POWERED_BY.items():
            if marker in powered:
                found[name] = found.get(name, 0) + 1
    for name, count in found.items():
        out.add(f"framework:{name}", f"{count} 頁有 {name} 的特徵", _pages_conf(count))
    return tuple(sorted(found))


def _detect_server(pages: list[dict], out: _Collector) -> str | None:
    for page in pages:
        server = _headers(page).get("server", "").lower()
        for product in _SERVER_PRODUCTS:
            if product in server:
                out.add("server", "回應標頭 Server", 0.9)
                return product
    return None


def _detect_edge(pages: list[dict], out: _Collector) -> str | None:
    for page in pages:
        edge = detect_edge(page.get("headers") or {}, [], [])
        if edge:
            for line in edge["evidence"]:
                out.add("edge", line, 0.9)
            return edge["provider"]
    return None


def _detect_forms(pages: list[dict], kind: str, pattern: re.Pattern, out: _Collector):
    urls: list[str] = []
    for page in pages:
        html = _html(page)
        if any(pattern.search(tag) for tag in _INPUT.findall(html)):
            urls.append(page.get("final_url") or page.get("url", ""))
    if urls:
        label = "密碼欄位" if kind == "login" else "檔案上傳欄位"
        out.add(kind, f"{len(urls)} 頁有{label}（例如 {urls[0]}）", 0.95)
    return tuple(urls[:MAX_URLS])


def _detect_api(endpoints: list[str], pages: list[dict], out: _Collector) -> tuple[str, ...]:
    api = [url for url in endpoints if _API_PATH.search(urlsplit(url).path)]
    if api:
        out.add("api", f"瀏覽器在爬取時呼叫了 {len(api)} 個 API 端點（例如 {api[0]}）",
                _pages_conf(len(api)))
    for page in pages:
        if re.search(r"""rel=["']https://api\.w\.org/""", _html(page), re.IGNORECASE):
            out.add("api", "頁面宣告 WordPress REST API（api.w.org）", 0.8)
            break
    return tuple(api[:MAX_URLS])


def _detect_auth_scheme(all_pages: list[dict], out: _Collector) -> str | None:
    for page in all_pages:
        if page.get("status_code") != 401:
            continue
        challenge = _headers(page).get("www-authenticate", "").strip().lower()
        scheme = next((s for s in _AUTH_SCHEMES if challenge.startswith(s)), None)
        if scheme:
            out.add("auth_scheme", f"{page.get('url', '')} 回應 401，要求 {scheme} 驗證", 0.95)
            return scheme
    return None


def build_fingerprint(
    crawled_pages: list[dict], discovered_endpoints: list[str] | None = None,
    *, crawl_complete: bool = True,
) -> SiteFingerprint:
    """以爬取階段已有的訊號組出網站特徵；不發任何請求。"""
    pages = [p for p in crawled_pages if _usable(p)]
    out = _Collector()
    if not pages:
        keys = ("cms", "frameworks", "server", "edge", "has_login", "has_api", "has_upload",
                "auth_scheme")
        auth = _detect_auth_scheme(crawled_pages, out)
        completeness = dict.fromkeys(keys, "unavailable")
        if auth:
            completeness["auth_scheme"] = "complete"
        return SiteFingerprint(
            auth_scheme=auth, completeness=completeness,
            evidence={k: tuple(v) for k, v in out.evidence.items()}, confidence=out.confidence,
        )

    cms = _detect_cms(pages, out)
    frameworks = _detect_frameworks(pages, out)
    server = _detect_server(pages, out)
    edge = _detect_edge(pages, out)
    login_urls = _detect_forms(pages, "login", _TYPE_PASSWORD, out)
    upload_urls = _detect_forms(pages, "upload", _TYPE_FILE, out)
    api_urls = _detect_api(discovered_endpoints or [], pages, out)
    auth_scheme = _detect_auth_scheme(crawled_pages, out)
    has_api = True if "api" in out.evidence else None

    absent = "not_observed" if crawl_complete else "partial"
    completeness = {
        "cms": "complete" if cms else absent,
        "frameworks": "complete" if frameworks else absent,
        "server": "complete" if server else absent,
        # 這個階段只看標頭；IP 網段、CNAME 要等 site_profile（階段 2 的 enrichment）
        "edge": "complete" if edge else "partial",
        "has_login": "complete" if login_urls else absent,
        # API 只在瀏覽器實際執行到的流程裡看得到，沒看到不代表沒有
        "has_api": "complete" if has_api else "partial",
        "has_upload": "complete" if upload_urls else absent,
        "auth_scheme": "complete" if auth_scheme else absent,
    }
    return SiteFingerprint(
        cms=cms,
        frameworks=frameworks,
        server=server,
        edge=edge,
        has_login=True if login_urls else None,
        login_urls=login_urls,
        has_api=has_api,
        api_urls=api_urls,
        has_upload=True if upload_urls else None,
        auth_scheme=auth_scheme,
        confidence=out.confidence,
        evidence={k: tuple(v) for k, v in out.evidence.items()},
        completeness=completeness,
    )


def fingerprint_snapshot(
    crawled_pages: list[dict], discovered_endpoints: list[str] | None = None,
    *, crawl_complete: bool = True,
) -> dict:
    """存進 `ScanJob.fingerprint` 的格式：特徵＋版本、階段、頁數與耗時。"""
    started = time.perf_counter()
    fingerprint = build_fingerprint(
        crawled_pages, discovered_endpoints, crawl_complete=crawl_complete
    )
    return {
        "version": VERSION,
        "phase": "pre_scan",
        "pages_considered": sum(1 for p in crawled_pages if _usable(p)),
        "endpoints_considered": len(discovered_endpoints or []),
        "crawl_complete": crawl_complete,
        "elapsed_ms": round(1000 * (time.perf_counter() - started), 2),
        **fingerprint.as_dict(),
    }
