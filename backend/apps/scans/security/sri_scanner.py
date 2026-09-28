"""SRI 缺失偵測：外部跨來源 <script>/<link rel=stylesheet> 缺 integrity 屬性。
任何例外 silent-fail 回 []。沿用 stdlib html.parser，不引入 BeautifulSoup。"""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from apps.scans.scanners import make_finding


class _SriParser(HTMLParser):
    """收集缺少 integrity 的 <script src> 與 <link rel=stylesheet href>。"""

    def __init__(self) -> None:
        super().__init__()
        # 每筆 = (resource_url, tag_name)
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        normalized = tag.lower()
        if normalized == "script":
            src = attributes.get("src", "").strip()
            if src and "integrity" not in attributes:
                self.refs.append((src, "script"))
        elif normalized == "link":
            rel = attributes.get("rel", "").lower()
            href = attributes.get("href", "").strip()
            if rel == "stylesheet" and href and "integrity" not in attributes:
                self.refs.append((href, "link"))


# 這些服務的腳本內容會隨時更新、網址不帶版本，官方也不提供 SRI hash；加上 integrity
# 反而會讓腳本在下一次更新後被瀏覽器擋掉。對它們建議 SRI 是做不到的建議，改由 CSP
# 限制可載入的來源，所以不列入 SRI 缺失。
_DYNAMIC_SCRIPT_HOSTS = (
    "googletagmanager.com",
    "google-analytics.com",
    "googleadservices.com",
    "googlesyndication.com",
    "connect.facebook.net",
    "static.cloudflareinsights.com",
    "www.google.com",
    "www.gstatic.com",
    "maps.googleapis.com",
    "js.stripe.com",
)


def _is_dynamic_third_party(resolved_url: str) -> bool:
    host = urlparse(resolved_url).hostname or ""
    return any(host == h or host.endswith("." + h) for h in _DYNAMIC_SCRIPT_HOSTS)


def _is_cross_origin(resource_url: str, page_url: str) -> bool:
    """解析後 host 與頁面 host 不同才算跨來源；相對路徑（無 host）視為同源。"""
    try:
        resolved_host = urlparse(urljoin(page_url, resource_url)).netloc.lower()
        page_host = urlparse(page_url).netloc.lower()
        if not resolved_host:
            return False
        return resolved_host != page_host
    except Exception:
        return False


def analyze_sri(pages: list[dict]) -> list[dict]:
    """掃所有頁面的外部無 integrity 資源，依解析後 URL 去重。"""
    try:
        seen: set[str] = set()
        out: list[dict] = []
        for page in pages:
            html = page.get("html") or ""
            if not html:
                continue
            page_url = page.get("final_url") or page.get("url") or ""
            parser = _SriParser()
            try:
                parser.feed(html)
            except Exception:
                continue
            for res_url, tag in parser.refs:
                if not _is_cross_origin(res_url, page_url):
                    continue
                resolved = urljoin(page_url, res_url)
                if _is_dynamic_third_party(resolved):
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                out.append(make_finding(
                    category="security", severity="low",
                    rule_id="sri-missing-integrity",
                    title="外部資源缺少 SRI 完整性驗證",
                    description=(
                        f"外部資源 {resolved} 未設定 integrity 屬性，"
                        "若該 CDN 遭竄改，惡意程式碼將直接於使用者瀏覽器執行。"
                    ),
                    remediation=(
                        "為外部 <script>/<link> 加上 integrity 與 crossorigin 屬性（SRI hash）。"
                    ),
                    evidence=f"<{tag} ...{res_url}>（無 integrity）",
                    impact_area="vulnerability",
                ))
        return out
    except Exception:
        return []
