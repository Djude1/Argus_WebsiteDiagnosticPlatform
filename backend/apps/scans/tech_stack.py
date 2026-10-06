"""網站使用的技術（被動辨識）：只看爬蟲已取得的首頁 HTML 與回應標頭，不另發請求。

給掃描結果的「網站架構」分頁用（2026-10-06 使用者需求）：讓網站主一眼看到網站是
用什麼框架、CMS、分析工具與伺服器組成的。每一項都附判斷依據；看不出來的就不列，
不從版本號或片段字串猜。
"""

from __future__ import annotations

import re

MAX_HTML_CHARS = 400_000

# (名稱, 類別, HTML 正規式) —— 標記必須是該技術特有的路徑或屬性，不用一般單字
_HTML_SIGNATURES: tuple[tuple[str, str, str], ...] = (
    ("Next.js", "網站框架", r"/_next/static/|id=\"__NEXT_DATA__\""),
    ("Nuxt", "網站框架", r"/_nuxt/|window\.__NUXT__"),
    ("Gatsby", "網站框架", r"id=\"___gatsby\""),
    ("Angular", "網站框架", r"\sng-version=\""),
    ("Vue.js", "前端函式庫", r"\sdata-v-[0-9a-f]{6,8}[\s=>]"),
    ("WordPress", "內容管理系統", r"/wp-content/|/wp-includes/"),
    ("Drupal", "內容管理系統", r"/sites/default/files/|Drupal\.settings"),
    ("Joomla", "內容管理系統", r"/media/jui/|content=\"Joomla"),
    ("Shopify", "電商平台", r"cdn\.shopify\.com"),
    ("Wix", "網站建置平台", r"static\.wixstatic\.com"),
    ("Squarespace", "網站建置平台", r"static1\.squarespace\.com"),
    ("jQuery", "前端函式庫", r"jquery(?:\.min)?\.js|jquery-\d"),
    ("Bootstrap", "前端函式庫", r"bootstrap(?:\.min)?\.(?:css|js)"),
    ("Google Tag Manager", "分析與行銷", r"googletagmanager\.com/gtm\.js"),
    ("Google Analytics", "分析與行銷", r"googletagmanager\.com/gtag/js|google-analytics\.com"),
    ("Meta Pixel", "分析與行銷", r"connect\.facebook\.net/[^\"']*/fbevents\.js"),
    ("Google Fonts", "字型與資源", r"fonts\.googleapis\.com"),
    ("Cloudflare Web Analytics", "分析與行銷", r"static\.cloudflareinsights\.com"),
)
_GENERATOR = re.compile(
    r"<meta[^>]+name=[\"']generator[\"'][^>]+content=[\"']([^\"']{2,60})[\"']", re.IGNORECASE
)
# 回應標頭：只取產品名稱，不回報版本號（版本屬於資安發現的範疇，這裡只描述架構）
_SERVER_PRODUCTS = {
    "nginx": "Nginx",
    "apache": "Apache",
    "microsoft-iis": "Microsoft IIS",
    "litespeed": "LiteSpeed",
    "cloudflare": "Cloudflare",
    "openresty": "OpenResty",
    "caddy": "Caddy",
    "gunicorn": "Gunicorn",
    "vercel": "Vercel",
    "netlify": "Netlify",
}
_POWERED_BY = {
    "php": "PHP",
    "asp.net": "ASP.NET",
    "express": "Express",
    "next.js": "Next.js",
}


def _add(found: dict, name: str, category: str, evidence: str) -> None:
    found.setdefault(name, {"name": name, "category": category, "evidence": evidence})


def detect_technologies(
    html: str, headers: dict | None, extra: list[str] | None = None
) -> list[dict]:
    """回傳 [{name, category, evidence}]，依類別與名稱排序；extra 是 Katana 已辨識的技術名稱。"""
    found: dict[str, dict] = {}
    text = (html or "")[:MAX_HTML_CHARS]
    for name, category, pattern in _HTML_SIGNATURES:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            _add(found, name, category, f"頁面含 {match.group(0)[:60]}")
    generator = _GENERATOR.search(text)
    if generator:
        product = re.split(r"\s\d", generator.group(1).strip())[0]
        _add(found, product, "內容管理系統", "meta generator")
    lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    server = lowered.get("server", "").lower()
    for marker, product in _SERVER_PRODUCTS.items():
        if marker in server:
            _add(found, product, "伺服器與託管", "回應標頭 Server")
            break
    powered = lowered.get("x-powered-by", "").lower()
    for marker, product in _POWERED_BY.items():
        if marker in powered:
            _add(found, product, "伺服器與託管", "回應標頭 X-Powered-By")
    if "x-vercel-id" in lowered:
        _add(found, "Vercel", "伺服器與託管", "回應標頭 x-vercel-id")
    for name in extra or []:
        clean = str(name).strip()
        if clean and not any(clean.lower() == key.lower() for key in found):
            _add(found, clean, "其他", "Katana 主動探索")
    return sorted(found.values(), key=lambda item: (item["category"], item["name"].lower()))
