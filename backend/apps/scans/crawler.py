import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from config.egress import playwright_launch_kwargs
from django.conf import settings
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from apps.scans.accessibility import run_axe
from apps.scans.cancellation import ScanCancelled
from apps.scans.scanners import is_binary_resource
from apps.scans.services import (
    PublicScanTargetError,
    assert_public_http_url,
    assert_public_websocket_url,
)

# 會被視為「被阻擋」的 HTTP 狀態碼與對應的中文原因
BLOCKED_STATUS_REASONS = {
    401: "需要登入才能存取",
    403: "伺服器拒絕存取",
    429: "請求頻率過高被限流",
}

# Cloudflare Managed Challenge（Turnstile 攔截頁）特徵字串：只出現在 CF 擋下請求時回的攔截頁。
# 這類驗證需要使用者互動（點擊勾選框），headless 瀏覽器無法自動通過。
CF_TURNSTILE_MARKERS = (
    "cf-chl-bypass",
    "challenge-running",
)

# Turnstile 元件特徵：網站自己的登入、聯絡表單內嵌 Turnstile 時也會出現（`cf-turnstile`
# 容器、`cf-turnstile-response` 隱藏欄位），單獨出現不代表頁面被攔截，只用來在確定是
# 攔截頁時決定原因文字。2026-10-11 掃 Argus 自己的網站時，登入、商業合作等 3 個正常頁面
# 因此被判成被阻擋、完全沒有分析。
CF_TURNSTILE_WIDGET_MARKERS = (
    "cf-turnstile",
    "turnstile-wrapper",
)

# Cloudflare JavaScript challenge 特徵字串。
# CF 邊緣注入的 challenge 載入器，body 出現這些字串代表此頁是攔截頁，不是真實內容。
# 不收錄「Just a moment」短語，避免正常網站文章正文恰好出現該短語的 false positive。
# 不收錄裸字串 "challenge-platform"：開啟 Bot 偵測的站，CF 會在「每一個正常頁面」尾端插入
# /cdn-cgi/challenge-platform/scripts/（jsd、precursor）背景腳本；攔截頁才會載入 /h/ 下的
# orchestrate 並帶 _cf_chl_opt。2026-10-02 實測站台 首頁因此被誤判、整站只爬到 1 頁。
CF_JS_CHALLENGE_MARKERS = (
    "/cdn-cgi/challenge-platform/h/",
    "_cf_chl_opt",
    "cf-browser-verification",
    "cf_captcha",
)



def compute_min_interval(scan_mode: str, *, active_rps: int, passive_rps: int) -> float:
    """依掃描模式計算兩次請求之間的最小間隔秒數。

    主動模式套用較嚴格的 RPS 上限，確保不超過授權允許的請求頻率。
    """
    rps = active_rps if scan_mode == "active" else passive_rps
    return 1.0 / max(rps, 1)


def classify_blocked(status_code: int | None) -> str:
    """判斷 HTTP 狀態碼是否代表被阻擋，回傳中文原因；未被阻擋則回傳空字串。"""
    if status_code is None:
        return ""
    return BLOCKED_STATUS_REASONS.get(status_code, "")


# 單頁回應體上限（防止巨大回應撐爆 Chromium/worker 記憶體）
# 一般 HTML < 500KB；30MB 覆蓋絕大多數合理情境，仍能攔下 PDF/影片/惡意 gzip bomb
_MAX_RESPONSE_BYTES = 30 * 1024 * 1024


def classify_oversized(headers: dict | None, body: str | None = None) -> str:
    """檢查回應是否超過 _MAX_RESPONSE_BYTES，超過回中文原因，否則空字串。

    優先看 Content-Length header（免下載 body 就能判斷）；
    沒有 header 時（chunked encoding）用實際 body 長度 fallback。
    """
    if headers:
        cl = headers.get("content-length") or headers.get("Content-Length")
        if cl:
            try:
                size = int(cl)
            except (TypeError, ValueError):
                size = 0
            if size > _MAX_RESPONSE_BYTES:
                return (
                    f"回應過大（Content-Length {size:,} bytes 超過上限 "
                    f"{_MAX_RESPONSE_BYTES:,}）"
                )
    if body is not None:
        # 用 len(body) 而非 encode，避免大字串複製一份；str 本身足以判斷量級
        if len(body) > _MAX_RESPONSE_BYTES:
            return (
                f"回應過大（實際 body {len(body):,} chars 超過上限 "
                f"{_MAX_RESPONSE_BYTES:,}）"
            )
    return ""


def classify_cf_challenge(html: str | None) -> str:
    """偵測頁面是否為 Cloudflare challenge 攔截頁，回傳中文原因；非 challenge 回傳空字串。

    只有出現攔截頁才有的特徵時才算被阻擋；頁面只是內嵌 Turnstile 表單元件（登入、聯絡表單）
    是正常頁面，照常分析。是攔截頁時，有 Turnstile 特徵的回報 Turnstile（需使用者互動，必擋），
    否則回報 JavaScript 驗證。
    CF challenge 經常回 200 status code 但 body 是攔截頁，若交給 scanners 分析
    會誤判為「H1 缺失、meta 缺失」等假 finding，因此須在爬蟲層攔下並設為 blocked。
    """
    if not html:
        return ""
    managed = any(marker in html for marker in CF_TURNSTILE_MARKERS)
    js_challenge = any(marker in html for marker in CF_JS_CHALLENGE_MARKERS)
    if not (managed or js_challenge):
        return ""
    if managed or any(marker in html for marker in CF_TURNSTILE_WIDGET_MARKERS):
        return "Cloudflare Turnstile 驗證，需使用者互動才能通過"
    return "Cloudflare JavaScript 驗證，自動掃描無法通過"


def normalize_crawl_url(url: str) -> str:
    clean_url, _fragment = urldefrag(url)
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}{path}{query}"


def url_origin(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    # IPv6 主機需用中括號包起來，比照 services.py::_host_for_url() 產生 ScanJob.origin
    # 時的格式；否則 urlparse().hostname 對 IPv6 回傳不含中括號的裸位址，會跟
    # ScanJob.origin 永遠對不上，讓 IPv6 目標的每一頁都被誤判成跨網域導向。
    host = f"[{hostname}]" if ":" in hostname else hostname
    target_origin = f"{parsed.scheme}://{host}"
    if parsed.port:
        target_origin = f"{target_origin}:{parsed.port}"
    return target_origin


def same_origin(url: str, origin: str) -> bool:
    return url_origin(url) == origin


def load_robot_parser(origin: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.set_url(urljoin(origin, "/robots.txt"))
    # robots.txt 由受控的 Playwright request context 讀取，避免 urllib 自動轉址旁路。
    parser.parse([])
    return parser


async def probe_site_signals(context, origin: str, robot_parser: RobotFileParser) -> dict:
    """檢查站台層級訊號：llms.txt 是否存在、robots.txt 是否阻擋 AI 爬蟲、robots Disallow 清單。

    robots_disallow 供資安層判斷「robots.txt 是否把敏感路徑當地圖洩露」（被動）。
    """
    from apps.scans.ai_bots import analyze_policy, blocked
    from apps.scans.security.exposure_scanner import parse_robots_disallow

    signals: dict = {
        "llms_txt_found": False,
        "blocked_ai_crawlers": [],
        "robots_disallow": [],
        "robots_sitemaps": [],
        # 原文留給 robots／sitemap／noindex 一致性檢查（seo/site_findings.py）；
        # Google 只讀前 500 KiB
        "robots_text": None,
        # 已取得的站台檔案 {網址: HTTP 狀態}（不跟隨轉址）；SEO 連結檢查與站台檢查沿用，
        # 同一次掃描不再對同一網址送第二次請求（roadmap §11 第 1 項）
        "fetched": {},
    }
    try:
        llms_url = assert_public_http_url(f"{origin}/llms.txt")
        response = await context.request.get(llms_url, timeout=10000, max_redirects=0)
        signals["fetched"][llms_url] = response.status
        signals["llms_txt_found"] = response.ok
    except Exception:
        signals["llms_txt_found"] = False
    robots_text = None
    try:
        robots_url = assert_public_http_url(f"{origin}/robots.txt")
        resp = await context.request.get(robots_url, timeout=10000, max_redirects=0)
        signals["fetched"][robots_url] = resp.status
        if resp.ok:
            robots_text = (await resp.text())[:512_000]
            signals["robots_text"] = robots_text
            robot_parser.parse(robots_text.splitlines())
            signals["robots_disallow"] = parse_robots_disallow(robots_text)
            signals["robots_sitemaps"] = parse_robots_sitemaps(robots_text)
    except Exception:
        signals["robots_disallow"] = []
    # AI 爬蟲的 robots.txt 政策（ai_bots.py）：依用途分訓練／AI 搜尋／使用者觸發，
    # 只讀已取得的 robots.txt
    signals["ai_bot_policy"] = analyze_policy(robots_text)
    signals["blocked_ai_crawlers"] = [b["agent"] for b in blocked(signals["ai_bot_policy"])]
    return signals


# sitemap 只當「網站自己列出的頁面清單」補爬取種子：讀取上限避免超大或惡意檔案撐爆記憶體，
# sitemap index 最多再展開幾個子 sitemap；壓縮檔（.gz）不處理。
_SITEMAP_MAX_BYTES = 2_000_000
_SITEMAP_MAX_CHILDREN = 3
_SITEMAP_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


def parse_robots_sitemaps(robots_text: str) -> list[str]:
    """robots.txt 的 `Sitemap:` 宣告（不分大小寫）。"""
    sitemaps = []
    for line in robots_text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "sitemap" and value.strip():
            sitemaps.append(value.strip())
    return sitemaps


def is_crawl_trap(url: str) -> bool:
    """Cloudflare 保留路徑（/cdn-cgi/）：其中 /cdn-cgi/content?id=… 是給機器人的陷阱連結，
    每次 id 都不同、可無限產生，跟進去只會用垃圾頁吃掉頁數上限。"""
    return urlparse(url).path.startswith("/cdn-cgi/")


def to_scan_origin(url: str, origin: str) -> str:
    """sitemap 網址與掃描網址只差 `www.` 前綴時，改寫成掃描的 origin；其他情況原樣回傳。

    網站常同時服務 example.com 與 www.example.com，sitemap 卻只寫其中一種；只認完全同源
    的話整份 sitemap 都用不到。改寫後仍走同源爬取，實際不存在的頁面照常記錄。
    """
    parsed, target = urlparse(url), urlparse(origin)
    host, target_host = parsed.hostname or "", target.hostname or ""
    if (
        parsed.scheme != target.scheme
        or parsed.port != target.port
        or host == target_host
        or host.removeprefix("www.") != target_host.removeprefix("www.")
    ):
        return url
    return parsed._replace(netloc=target.netloc).geturl()


def sitemap_page_urls(locs: list[str], origin: str) -> list[str]:
    """sitemap 的 <loc> 轉成可爬取的同源頁面網址（去重保序、排除二進位檔與陷阱路徑）。"""
    urls: list[str] = []
    for loc in locs:
        normalized = normalize_crawl_url(to_scan_origin(loc.replace("&amp;", "&"), origin))
        if (
            not normalized
            or not same_origin(normalized, origin)
            or is_binary_resource(normalized)
            or is_crawl_trap(normalized)
        ):
            continue
        if normalized not in urls:
            urls.append(normalized)
    return urls


async def _fetch_sitemap(context, url: str, origin: str, fetched: dict | None = None) -> str:
    """抓單一 sitemap（同源、公開位址、不跟隨轉址）；失敗或過大回空字串。

    fetched 有值時記下 {網址: HTTP 狀態}，給 SEO 站台檢查沿用。
    """
    try:
        if not same_origin(url, origin) or url.lower().endswith(".gz"):
            return ""
        safe_url = assert_public_http_url(url)
        response = await context.request.get(safe_url, timeout=10000, max_redirects=0)
        if fetched is not None:
            fetched[safe_url] = response.status
        if not response.ok:
            return ""
        body = await response.body()
        if len(body) > _SITEMAP_MAX_BYTES:
            return ""
        return body.decode("utf-8", errors="replace")
    except Exception:
        return ""


async def discover_sitemap_urls(
    context, origin: str, declared: list[str], limit: int, fetched: dict | None = None
) -> list[str]:
    """從 robots.txt 宣告的 sitemap（沒有就 /sitemap.xml）取出同源頁面網址，最多 limit 個。

    被動、只讀網站公開給搜尋引擎的清單：只靠 <a> 連結 BFS 時，連結稀疏或以 JavaScript
    導覽的網站在有限深度內常找不到足夠頁面，整站掃描到不了頁數上限。
    """
    declared = [to_scan_origin(url, origin) for url in declared]
    pending = [url for url in declared if same_origin(url, origin)] or [f"{origin}/sitemap.xml"]
    urls: list[str] = []
    children_left = _SITEMAP_MAX_CHILDREN
    seen: set[str] = set()
    while pending and len(urls) < limit:
        sitemap_url = pending.pop(0)
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)
        text = await _fetch_sitemap(context, sitemap_url, origin, fetched)
        if not text:
            continue
        locs = _SITEMAP_LOC.findall(text)
        if "<sitemapindex" in text.lower():
            for child in locs:
                if children_left <= 0:
                    break
                children_left -= 1
                pending.append(to_scan_origin(child.replace("&amp;", "&"), origin))
            continue
        for url in sitemap_page_urls(locs, origin):
            if url not in urls:
                urls.append(url)
    return urls[:limit]


async def collect_element_boxes(page) -> dict[str, dict]:
    selectors = ["h1", "img:not([alt])", "form", "main"]
    boxes: dict[str, dict] = {}
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0:
                box = await locator.bounding_box(timeout=1000)
                if box:
                    boxes[selector] = box
        except Exception:
            continue
    return boxes


# 行動版量測的視窗寬度。375 是主流手機的 CSS 寬度（iPhone 6 以降的多數機型），
# 破版在這個寬度看得最清楚。
# ---------- 渲染就緒（roadmap「爬取」第 1 項） ----------
# 不等 networkidle（分析工具、客服 widget、長輪詢讓網路永遠不安靜）；改看 DOM 是否穩定：
# 每 250ms 量一次正文字數與元素數，至少等 _RENDER_GRACE_SECONDS（給前端框架 hydration），
# 連續兩次幾乎不變就算就緒。輪播、跑馬燈會讓字數小幅變動，所以容許少量差異。
_RENDER_POLL_MS = 250
_RENDER_GRACE_SECONDS = 0.5
_DOM_SAMPLE = """() => [
    document.body ? document.body.innerText.length : 0,
    document.getElementsByTagName("*").length,
]"""


def _dom_stable(previous: list, current: list) -> bool:
    text_before, nodes_before = previous
    text_now, nodes_now = current
    return (
        text_now > 0
        and abs(text_now - text_before) <= max(20, text_before * 0.005)
        and abs(nodes_now - nodes_before) <= 2
    )


async def wait_for_render_ready(page, max_seconds: float) -> dict:
    """等頁面內容穩定，最多 max_seconds；回傳 {"status": ready|timeout|error, "ms": 等待毫秒}。

    逾時不是失敗：照樣擷取當下的 DOM 與截圖，只記錄這頁可能還沒渲染完整。
    """
    started = time.perf_counter()
    previous = None

    def result(status: str) -> dict:
        return {"status": status, "ms": round((time.perf_counter() - started) * 1000)}

    while True:
        try:
            current = await page.evaluate(_DOM_SAMPLE)
        except Exception:
            return result("error")
        elapsed = time.perf_counter() - started
        if (
            previous is not None
            and elapsed >= _RENDER_GRACE_SECONDS
            and _dom_stable(previous, current)
        ):
            return result("ready")
        if elapsed >= max_seconds:
            return result("timeout")
        previous = current
        await page.wait_for_timeout(_RENDER_POLL_MS)


# 版面位移只回報位移最多的幾個元素
_MAX_LAYOUT_SHIFT_ELEMENTS = 5


async def collect_layout_shift(page) -> dict:
    """量這頁載入與捲動期間的累計版面位移（CLS），並找出位移的元素（roadmap §4 第 3 項）。

    用瀏覽器的 layout-shift 紀錄（buffered，含載入期間已發生的位移），依 Google 的 CLS 定義
    取最大的工作階段視窗（位移間隔 <1 秒、整段 ≤5 秒）；使用者操作後 0.5 秒內的位移不算。
    包含 scroll_to_bottom 往下捲動時的位移（延遲載入的圖片），但不含它最後瞬間跳回頂端之後的位移。
    **在截圖之前呼叫**：整頁截圖會改變視窗大小，可能產生不是使用者會看到的位移。

    這是單次、桌面視窗、無使用者操作的量測，數值會與 Lighthouse／真實使用者不同。
    失敗或瀏覽器不支援回傳 {}（＝沒量到，不是沒有位移）。
    """
    try:
        return await asyncio.wait_for(
            page.evaluate(
                r"""
                async (maxElements) => {
                    const types = (window.PerformanceObserver
                        && PerformanceObserver.supportedEntryTypes) || [];
                    if (!types.includes("layout-shift")) return {};
                    const entries = await new Promise((resolve) => {
                        const list = [];
                        const observer = new PerformanceObserver(
                            (l) => list.push(...l.getEntries())
                        );
                        observer.observe({ type: "layout-shift", buffered: true });
                        setTimeout(() => {
                            list.push(...observer.takeRecords());
                            observer.disconnect();
                            resolve(list);
                        }, 100);
                    });
                    let best = 0, bestWindow = [], current = 0, currentWindow = [];
                    let first = 0, last = 0, total = 0;
                    const jumpedAt = window.__argusScrollTopAt ?? Infinity;
                    const counted = entries.filter(
                        (e) => !e.hadRecentInput && e.startTime < jumpedAt
                    );
                    for (const e of counted) {
                        total += e.value;
                        if (currentWindow.length && e.startTime - last < 1000
                            && e.startTime - first < 5000) {
                            current += e.value;
                            currentWindow.push(e);
                        } else {
                            current = e.value;
                            currentWindow = [e];
                            first = e.startTime;
                        }
                        last = e.startTime;
                        if (current > best) {
                            best = current;
                            bestWindow = currentWindow.slice();
                        }
                    }
                    const describe = (el) => {
                        const id = el.id ? `#${el.id}` : "";
                        const cls = (el.className && typeof el.className === "string")
                            ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
                            : "";
                        return (el.tagName.toLowerCase() + id + cls).slice(0, 120);
                    };
                    // 每次位移的分數記到這次位移中移動的元素上（一次位移可能有多個元素）；
                    // 同一次位移裡同名的元素只記一次，否則元素分數會大於整頁 CLS
                    const elements = new Map();
                    for (const e of bestWindow) {
                        const seen = new Set();
                        for (const source of e.sources || []) {
                            let node = source.node;
                            if (node && node.nodeType !== 1) node = node.parentElement;
                            if (!node || !node.tagName) continue;
                            const selector = describe(node);
                            const moved = Math.round(Math.max(
                                Math.abs(source.currentRect.y - source.previousRect.y),
                                Math.abs(source.currentRect.x - source.previousRect.x),
                            ));
                            const item = elements.get(selector)
                                || { selector, score: 0, moved_px: 0, shifts: 0 };
                            item.moved_px = Math.max(item.moved_px, moved);
                            if (!seen.has(selector)) {
                                seen.add(selector);
                                item.score += e.value;
                                item.shifts += 1;
                            }
                            elements.set(selector, item);
                        }
                    }
                    const top = [...elements.values()]
                        // 同一次位移裡的元素分數相同，移動距離大的排前面
                        .sort((a, b) => b.score - a.score || b.moved_px - a.moved_px)
                        .slice(0, maxElements)
                        .map((item) => ({ ...item, score: Math.round(item.score * 1000) / 1000 }));
                    // 常見原因：沒有標寬高的圖片／影片／iframe，載入後把下面的內容往下推
                    const unsized = [...document.querySelectorAll("img, video, iframe")].filter(
                        (el) => !el.getAttribute("width") || !el.getAttribute("height")
                    ).length;
                    return {
                        cls: Math.round(best * 1000) / 1000,
                        total: Math.round(total * 1000) / 1000,
                        shifts: counted.length,
                        elements: top,
                        unsized_media: unsized,
                    };
                }
                """,
                _MAX_LAYOUT_SHIFT_ELEMENTS,
            ),
            timeout=10,
        )
    except Exception:
        return {}


MOBILE_VIEWPORT = {"width": 375, "height": 812}
# 只回報最嚴重的幾個元素。一個溢出的子元素會讓所有祖先都超寬，全記等於洗版，
# 而這份資料每頁都要進 DB。
_MAX_OVERFLOW_OFFENDERS = 5


async def collect_mobile_layout(page) -> dict:
    """切到行動版視窗量一次水平溢出。

    **必須在所有其他擷取完成之後才呼叫**：這裡會改動 viewport，跑在截圖或
    內容擷取之前會讓那些結果變成行動版的。

    失敗一律吞掉回傳 {}：這是加值資訊，不值得讓整頁擷取失敗。專案踩過同型
    的坑——截圖寫入失敗曾導致整頁被丟進 failed_urls、掃描變成 0 頁。
    """
    try:
        await page.set_viewport_size(MOBILE_VIEWPORT)
        # 換寬度後要讓 layout 重算，否則量到的是舊值
        await page.wait_for_timeout(300)
        return await asyncio.wait_for(
            page.evaluate(
                # raw string：JS 的 \s 在非 raw 的 Python 字串裡是無效跳脫序列
                # （目前是 SyntaxWarning，未來的 Python 版本會直接報錯）
                r"""
                (maxOffenders) => {
                    const doc = document.documentElement;
                    const viewport = doc.clientWidth;
                    const scrollWidth = Math.max(
                        doc.scrollWidth, document.body ? document.body.scrollWidth : 0
                    );
                    // 1px 容差：瀏覽器的次像素捨入常造成 1px 誤差，不是真破版
                    const overflow = Math.max(0, scrollWidth - viewport - 1);
                    const result = {
                        viewport_width: viewport,
                        scroll_width: scrollWidth,
                        overflow_px: overflow,
                        offenders: [],
                    };
                    if (!overflow || !document.body) return result;
                    // 文件座標（含捲動位移），對得上行動版整頁截圖，可直接框出元素
                    const boxOf = (rect) => ({
                        x: Math.round(rect.left + window.scrollX),
                        y: Math.round(rect.top + window.scrollY),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                    });

                    const describe = (el) => {
                        const id = el.id ? `#${el.id}` : "";
                        const cls = (el.className && typeof el.className === "string")
                            ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
                            : "";
                        return (el.tagName.toLowerCase() + id + cls).slice(0, 120);
                    };
                    const seen = new Set();
                    const found = [];
                    for (const el of document.body.querySelectorAll("*")) {
                        const rect = el.getBoundingClientRect();
                        if (!rect.width || !rect.height) continue;
                        const right = rect.right + window.scrollX;
                        if (right <= viewport + 1) continue;
                        const selector = describe(el);
                        if (seen.has(selector)) continue;
                        seen.add(selector);
                        found.push({
                            selector,
                            overflow_px: Math.round(right - viewport),
                            width_px: Math.round(rect.width),
                            box: boxOf(rect),
                        });
                    }
                    found.sort((a, b) => b.overflow_px - a.overflow_px);
                    result.offenders = found.slice(0, maxOffenders);
                    return result;
                }
                """,
                _MAX_OVERFLOW_OFFENDERS,
            ),
            timeout=10,
        )
    except Exception:
        return {}


# 觸控目標的最小建議尺寸（Argus 易用性建議，非 WCAG 合規門檻）。
# WCAG 2.2 的 2.5.5（AAA）建議 44×44 CSS px、2.5.8（AA）最低 24×24 且有間距例外；
# 這裡取 40px 當門檻，避免把邊界值一律當缺陷洗版。
# 查詢參數裡的語系鍵：`?Lang=zh-tw`／`?lang=en`／`?locale=ja` 只是同一篇內容的語言版
_LANGUAGE_QUERY_KEYS = frozenset({"lang", "language", "locale", "hl", "lng"})
_MIN_TAP_TARGET_PX = 40
_WCAG_AA_TAP_TARGET_PX = 24  # WCAG 2.2 AA（2.5.8）：短邊達 24 且長邊夠長的橫條不算過小
_MAX_UX_OFFENDERS = 8


async def collect_ux_signals(page) -> dict:
    """在行動版視窗量互動可用性訊號：觸控目標過小、表單欄位缺少可及標籤。

    **必須在 collect_mobile_layout 之後、仍是行動版視窗時呼叫**：觸控目標尺寸
    要用手機視窗判斷才有意義。與 collect_mobile_layout 同樣的容錯策略——
    失敗一律回 {}，不讓整頁擷取失敗。
    """
    try:
        return await asyncio.wait_for(
            page.evaluate(
                r"""
                ({ minTap, minAa, maxOffenders }) => {
                    const result = { small_tap_targets: [], unlabeled_fields: [] };
                    if (!document.body) return result;
                    // 文件座標（含捲動位移），對得上行動版整頁截圖，可直接框出元素
                    const boxOf = (rect) => ({
                        x: Math.round(rect.left + window.scrollX),
                        y: Math.round(rect.top + window.scrollY),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                    });

                    const describe = (el) => {
                        const id = el.id ? `#${el.id}` : "";
                        const cls = (el.className && typeof el.className === "string")
                            ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
                            : "";
                        return (el.tagName.toLowerCase() + id + cls).slice(0, 120);
                    };
                    const isVisible = (el, rect) => {
                        if (!rect.width || !rect.height) return false;
                        // 收在畫面左右兩側外的抽屜選單（transform 移出視窗）使用者看不到也點不到，
                        // 不是觸控目標問題（2026-10-06 實測：x=395 的「首頁」在 375px 視窗外）
                        if (rect.right <= 0 || rect.left >= window.innerWidth) return false;
                        const style = getComputedStyle(el);
                        return style.visibility !== "hidden" && style.display !== "none";
                    };

                    // 1) 觸控目標過小：可點元素（連結／按鈕／表單控制項）在手機上
                    //    寬或高小於門檻，手指不易點準。
                    const tapSel = 'a[href], button, [role="button"], '
                        + 'input:not([type="hidden"]), select, textarea';
                    const tapSeen = new Set();
                    // 句子中的文字連結（段落裡夾著其他文字）大小由行高決定，WCAG 2.5.8
                    // 明列為例外，不算觸控目標問題（2026-10-12 Argus 自掃：「請透過聯絡我們頁面」）
                    const inlineInSentence = (el) => {
                        if (el.tagName !== "A") return false;
                        if (getComputedStyle(el).display !== "inline") return false;
                        const parent = el.parentElement;
                        if (!parent) return false;
                        const own = (el.textContent || "").trim().length;
                        const around = (parent.textContent || "").trim().length;
                        return around - own >= 10;
                    };
                    // 包在 <label> 裡的勾選框／選項鈕：點文字也會勾選，可點範圍是整個 label
                    const tapRect = (el) => {
                        const type = (el.getAttribute("type") || "").toLowerCase();
                        const isToggle = type === "checkbox" || type === "radio";
                        const label = isToggle && el.closest("label");
                        return (label || el).getBoundingClientRect();
                    };
                    for (const el of document.body.querySelectorAll(tapSel)) {
                        const rect = tapRect(el);
                        if (!isVisible(el, el.getBoundingClientRect())) continue;
                        if (inlineInSentence(el)) continue;
                        // 寬高都達 40 才算夠大；但短邊 ≥ 24（WCAG 2.5.8）且長邊 ≥ 40 的橫條
                        //（345×39 的標題連結）手指點得到，不列（2026-10-19 實掃差 1px 被列）
                        const shortSide = Math.min(rect.width, rect.height);
                        const longSide = Math.max(rect.width, rect.height);
                        if (shortSide >= minTap) continue;
                        if (shortSide >= minAa && longSide >= minTap) continue;
                        const rawLabel =
                            el.innerText || el.value || el.getAttribute("aria-label") || "";
                        const label = rawLabel.trim().slice(0, 40);
                        const selector = describe(el);
                        if (tapSeen.has(selector)) continue;
                        tapSeen.add(selector);
                        result.small_tap_targets.push({
                            selector,
                            label,
                            width_px: Math.round(rect.width),
                            height_px: Math.round(rect.height),
                            box: boxOf(rect),
                        });
                        if (result.small_tap_targets.length >= maxOffenders) break;
                    }

                    // 2) 表單欄位缺少可及名稱：<input>／<select>／<textarea> 沒有
                    //    對應 <label>、aria-label、aria-labelledby，也沒有 title／
                    //    placeholder，螢幕報讀者與部分使用者無從得知欄位用途。
                    const fieldSel = 'input:not([type="hidden"]):not([type="submit"])'
                        + ':not([type="button"]):not([type="reset"]), select, textarea';
                    const fieldSeen = new Set();
                    for (const el of document.body.querySelectorAll(fieldSel)) {
                        const rect = el.getBoundingClientRect();
                        if (!isVisible(el, rect)) continue;
                        const id = el.getAttribute("id");
                        const hasLabelFor = id && document.querySelector(
                            'label[for="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]'
                        );
                        const wrapped = el.closest("label");
                        const aria =
                            el.getAttribute("aria-label") || el.getAttribute("aria-labelledby");
                        const fallback = el.getAttribute("title") || el.getAttribute("placeholder");
                        if (hasLabelFor || wrapped || aria || fallback) continue;
                        const selector = describe(el);
                        if (fieldSeen.has(selector)) continue;
                        fieldSeen.add(selector);
                        result.unlabeled_fields.push({
                            selector,
                            type: (el.getAttribute("type") || el.tagName.toLowerCase()),
                            name: (el.getAttribute("name") || "").slice(0, 60),
                            box: boxOf(rect),
                        });
                        if (result.unlabeled_fields.length >= maxOffenders) break;
                    }
                    return result;
                }
                """,
                {"minTap": _MIN_TAP_TARGET_PX, "minAa": _WCAG_AA_TAP_TARGET_PX,
                 "maxOffenders": _MAX_UX_OFFENDERS},
            ),
            timeout=10,
        )
    except Exception:
        return {}


async def extract_links(page, base_url: str, origin: str) -> list[str]:
    hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
    links: list[str] = []
    for href in hrefs:
        normalized = normalize_crawl_url(urljoin(base_url, href))
        if not normalized or not same_origin(normalized, origin):
            continue
        # 二進位/媒體檔案（.apk、.pdf、字型、圖片等）不是 HTML 頁面，
        # 加進爬蟲 queue 只會浪費請求並產生無意義的 finding。
        if is_binary_resource(normalized) or is_crawl_trap(normalized):
            continue
        links.append(normalized)
    return sorted(set(links))


async def scroll_to_bottom(page) -> None:
    try:
        await asyncio.wait_for(
            page.evaluate(
                """
                async () => {
                    await new Promise((resolve) => {
                        let totalHeight = 0;
                        let iterations = 0;
                        // 無限捲動頁面（電商列表/社群 feed）的 scrollHeight 會隨捲動持續增長，
                        // 永遠追不上就永遠不會 resolve；上限 100 次（約 60,000px）保底跳出。
                        const maxIterations = 100;
                        const distance = 600;
                        const timer = setInterval(() => {
                            window.scrollBy(0, distance);
                            totalHeight += distance;
                            iterations += 1;
                            const done = totalHeight >= document.body.scrollHeight
                                || iterations >= maxIterations;
                            if (done) {
                                clearInterval(timer);
                                resolve();
                            }
                        }, 80);
                    });
                    // 記下跳回頂端的時間：之後的版面位移（例如捲動後縮小的固定標頭又展開）
                    // 是這個瞬間跳轉造成的，不是讀者會遇到的，collect_layout_shift 不計
                    window.__argusScrollTopAt = performance.now();
                    window.scrollTo(0, 0);
                }
                """
            ),
            timeout=15,
        )
    except TimeoutError:
        # 極端狀況（例如捲動中觸發頁面重新導向）evaluate 本身卡住：放棄捲動，
        # 用目前畫面繼續截圖/分析，不讓單頁拖垮整個掃描。
        pass


_CONTEXT_RECYCLE_EVERY = 15
_PAGE_RETRY_LIMIT = 1
# 被動收集的 same-origin XHR/fetch 端點上限（去重後）；預防長輪詢/socket.io
# 之類的高頻端點把清單撐爆
_MAX_API_ENDPOINTS = 80
# 被動 API 檢查（security/api_scanner）用的回應摘要：每個「方法＋路徑」只記第一次，不含查詢字串
# （可能夾帶 token）；只有錯誤回應另讀前 _API_BODY_LIMIT 字元，判斷是否洩漏堆疊追蹤（2026-10-11）
_MAX_API_OBSERVATIONS = 80
_API_BODY_LIMIT = 4000
_API_HEADER_KEYS = (
    "content-type",
    "access-control-allow-origin",
    "access-control-allow-credentials",
    "x-content-type-options",
)

# 靜態資源：不是 API 呼叫，不該進 api_observations／api_endpoints（否則 Next.js 用 fetch
# 預取的 /_next/static/*.css 會被列進「API 端點清單」，前綴推導也會拿它去推，2026-10-16）。
_STATIC_ASSET_EXTS = (
    ".css", ".js", ".mjs", ".map", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".mp4", ".webm", ".mp3", ".wav", ".pdf",
)
_STATIC_ASSET_PREFIXES = ("/_next/static/", "/static/", "/assets/", "/_nuxt/")


def is_static_asset_path(path: str) -> bool:
    """路徑看起來是靜態資源（JS／CSS／字型／圖片／打包產物目錄）就回 True。

    只看路徑本身（已去查詢字串）：副檔名或已知打包目錄前綴命中即算。
    """
    low = (path or "").split("?", 1)[0].lower()
    if any(low.startswith(prefix) for prefix in _STATIC_ASSET_PREFIXES):
        return True
    return any(low.endswith(ext) for ext in _STATIC_ASSET_EXTS)


# JS bundle 靜態端點發現（2026-10-16）：爬蟲載入頁面時瀏覽器已抓下同源 JS chunk，
# 直接讀內容用 regex 抽出網站自己寫死的 API 路徑／rewrite 前綴——繞得過 Cloudflare
# （主動重抓會被 challenge 擋），補上 Katana／被動攔截都看不到的登入後端點。
# 實測站台的代理前綴就明文寫在 _buildManifest.js。
_MAX_JS_BODIES = 80  # 每次掃描最多讀幾個 JS 檔的內容（不限重抓，放寬以提高涵蓋）
_MAX_JS_BODY_BYTES = 2 * 1024 * 1024
_MAX_JS_API_PATHS = 60
_MAX_JS_SECRETS = 40  # 外部 JS bundle 累積的秘鑰筆數上限
# 絕對路徑字串：以 / 開頭、只含路徑安全字元（含 Next.js rewrite 的 :param／* 動態段，
# 下面會截到第一個動態段之前）。原本字元類不含 : *，碰到 "/api_proxy/:path*" 整段比對失敗、
# 抽不到 /api_proxy——這是 2026-10-16 實站漏抓的直接原因。
_JS_PATH_RE = re.compile(r"""['"`](/[A-Za-z0-9_][A-Za-z0-9._~:*\-/]{1,120})['"`]""")


def _static_prefix_of(path: str) -> str:
    """截到第一個含動態參數（`:` 或 `*`，Next.js rewrite 語法）的路徑段之前。

    `/api_proxy/:path*` → `/api_proxy`；`/api/v1/users` → 原樣；`/:locale/x` → ``（整段動態）。
    """
    kept: list[str] = []
    for seg in path.split("/"):
        if not seg:
            continue
        if ":" in seg or "*" in seg:
            break
        kept.append(seg)
    return "/" + "/".join(kept) if kept else ""
# 看起來像 API／後端的路徑才留（避免把 /about、/_next 這類頁面與資源路徑灌進來）
_API_PATH_HINT = re.compile(
    r"(?:^|/)(?:api|api[_-]?proxy|backend|rest|graphql|gateway|service|services|"
    r"v[0-9]+|api-docs|openapi|swagger|rpc|ajax|internal)(?:/|$)",
    re.IGNORECASE,
)


def extract_api_paths_from_js(text: str) -> set[str]:
    """從一段 JS 原始碼抽出看起來像 API 的絕對路徑（去查詢字串、去重）。純解析、不連線。"""
    found: set[str] = set()
    for match in _JS_PATH_RE.finditer(text or ""):
        # 先截到動態段之前：Next.js rewrite 寫成 /api_proxy/:path*，要的是 /api_proxy
        path = _static_prefix_of(match.group(1).split("?", 1)[0])
        if not path or path == "/":
            continue
        if is_static_asset_path(path) or path.startswith("/_next/"):
            continue
        if _API_PATH_HINT.search(path):
            found.add(path)
            if len(found) >= _MAX_JS_API_PATHS:
                break
    return found


async def _close_playwright_resources(*resources) -> None:
    """盡力關閉故障的 Playwright 資源，不讓 cleanup 蓋掉原本狀態或重試。"""
    for resource in resources:
        if resource is None:
            continue
        try:
            await resource.close()
        except Exception:
            pass


async def _enforce_public_request(route, request, origin: str | None = None):
    """在送出前阻擋非公開目標，以及主 frame 的跨 origin navigation。"""
    try:
        target_url = assert_public_http_url(request.url)
    except PublicScanTargetError:
        await route.abort("blockedbyclient")
        return
    if origin and request.is_navigation_request():
        try:
            is_main_frame = request.frame == request.frame.page.main_frame
        except Exception:
            is_main_frame = True
        if is_main_frame and url_origin(target_url) != origin:
            await route.abort("blockedbyclient")
            return
    await route.continue_()


async def _enforce_public_websocket(websocket_route, origin: str | None = None):
    """禁止頁面透過 WebSocket 連往內網、保留位址或未授權 origin。"""
    try:
        target_url = assert_public_websocket_url(websocket_route.url)
    except PublicScanTargetError:
        await websocket_route.close(code=1008, reason="Blocked by scan target policy")
        return
    if origin:
        parsed = urlparse(target_url)
        http_scheme = "https" if parsed.scheme == "wss" else "http"
        if url_origin(parsed._replace(scheme=http_scheme).geturl()) != origin:
            await websocket_route.close(
                code=1008,
                reason="Blocked by scan origin policy",
            )
            return
    websocket_route.connect_to_server()


async def _make_context(browser, origin: str, har_path: Path | None = None):
    """建立標準 scanner 瀏覽器 context（user-agent + viewport）。

    har_path：給 ZAP 被動分析用（security/zap_passive.py），只錄同 origin 的請求與回應，
    在 context 關閉時寫檔；不會多發任何請求。
    """
    har_kwargs = {}
    if har_path is not None:
        har_kwargs = {
            "record_har_path": str(har_path),
            "record_har_content": "embed",
            "record_har_url_filter": re.compile("^" + re.escape(origin) + "(?:[/?#]|$)"),
        }
    context = await browser.new_context(
        user_agent=settings.ARGUS_SCANNER_USER_AGENT,
        viewport={"width": 1440, "height": 1000},
        service_workers="block",
        **har_kwargs,
    )
    async def _request_handler(route, request):
        await _enforce_public_request(route, request, origin)

    async def _websocket_handler(websocket_route):
        await _enforce_public_websocket(websocket_route, origin)

    await context.route("**/*", _request_handler)
    await context.route_web_socket("**/*", _websocket_handler)
    return context


def _prepare_screenshot_dir(screenshot_dir: Path, warnings: dict) -> Path | None:
    """建立截圖目錄；失敗回 None 而不是往上拋。

    磁碟寫滿或唯讀掛載時，舊版會讓 mkdir 的例外冒出 crawl_site，整次掃描在
    還沒爬第一頁就失敗。截圖是輔助資料，不該有這種殺傷力。
    """
    try:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        return screenshot_dir
    except Exception as exc:  # noqa: BLE001
        warnings.setdefault("screenshot_failures", []).append(
            {"url": "(screenshot_dir)", "reason": exc.__class__.__name__}
        )
        return None


async def wait_for_images_settled(page, max_seconds: float) -> None:
    """截圖前等「目前 DOM 裡尚未載完的 <img> 與 web font」完成（有上限，不等 networkidle）。

    `wait_for_render_ready` 只看文字／元素數穩定，圖片與字型可能還在載就截圖，使用者會看到
    半成品畫面（圖片空白、字型跳動）。這裡只等已經存在於 DOM 的資源，上限 max_seconds
    （分析工具／長輪詢不影響），逾時或出錯就直接截圖、不卡住掃描。scroll_to_bottom 已先觸發
    延遲載入的圖片，這一步確保它們在整頁截圖前畫出來。
    """
    if max_seconds <= 0:
        return
    try:
        await asyncio.wait_for(
            page.evaluate(
                """
                async () => {
                    const pending = Array.from(document.images || [])
                        .filter((img) => !img.complete)
                        .map((img) => new Promise((res) => {
                            img.addEventListener('load', res, { once: true });
                            img.addEventListener('error', res, { once: true });
                        }));
                    if (document.fonts && document.fonts.ready) {
                        pending.push(Promise.resolve(document.fonts.ready).catch(() => {}));
                    }
                    await Promise.all(pending);
                }
                """
            ),
            timeout=max_seconds,
        )
    except Exception:  # noqa: BLE001 — 截圖是盡力而為，等不到就直接拍
        pass


async def _capture_screenshot(page, target: Path, url: str, warnings: dict) -> Path | None:
    """拍頁面截圖；失敗回 None 而不是往上拋。

    這一步在 pages.append() **之前**執行；舊版讓例外冒出去會被外層的
    except Exception 接住，整頁被丟進 failed_urls——連帶 Page 紀錄與該頁的
    SEO/AEO 分析一起消失。磁碟寫滿時整次掃描會變成「0 頁」，使用者看到的是
    「截圖空白、SEO 分析也不見」（2026-08-31 正式站事故）。

    失敗記進 screenshot_failures 而不是 failed_urls：那一頁其實抓到了，
    記進 failed_urls 會讓報告誤報成「頁面擷取失敗」。
    """
    try:
        # 先等已在 DOM 的圖片／字型載完（有上限），避免截到半成品畫面
        await wait_for_images_settled(page, settings.ARGUS_SCREENSHOT_SETTLE_SECONDS)
        await page.screenshot(path=str(target), full_page=True)
        return target
    except Exception as exc:  # noqa: BLE001
        warnings.setdefault("screenshot_failures", []).append(
            {"url": url, "reason": exc.__class__.__name__}
        )
        return None


_CROSS_ORIGIN_REASON = "跨網域導向，超出授權範圍"


@dataclass
class _CrawlState:
    """一次爬取的佇列、結果與速率限制狀態。"""

    start_url: str
    origin: str
    max_depth: int
    max_pages: int
    warnings: dict = field(default_factory=lambda: {"blocked_urls": [], "failed_urls": []})
    visited: set[str] = field(default_factory=set)
    queue: deque = field(default_factory=deque)
    pages: list[dict] = field(default_factory=list)
    api_endpoints: set[str] = field(default_factory=set)
    api_observations: dict[str, dict] = field(default_factory=dict)
    # 同源 JS bundle 靜態抽出的 API 路徑（_buildManifest.js、chunks），2026-10-16
    js_api_paths: set[str] = field(default_factory=set)
    js_bodies_read: int = 0
    # 同源 JS bundle 偵測到的秘鑰（每筆 {kind,label,severity,masked,source}），2026-10-17
    # ADR-0005 §1：外部 .js 的秘鑰原本沒人掃（只有 Katana，CF 後歸零）；crawler 已握有 bytes
    js_secrets: list[dict] = field(default_factory=list)
    js_secret_keys: set[tuple[str, str]] = field(default_factory=set)
    page_retry_counts: dict[str, int] = field(default_factory=dict)
    last_request_at: float = 0.0
    # axe-core 無障礙檢查：勾 UX 才開；最多檢查 ARGUS_AXE_MAX_PAGES 頁
    run_accessibility: bool = False
    accessibility_runs: int = 0
    # 爬取預算（roadmap「爬取」第 2 項）：種子來源、略過原因、節流、每頁耗時，結束時整理成
    # warnings["crawl_budget"]，讓「為什麼只爬到這些頁」可以回答
    seeds: dict = field(default_factory=lambda: {"start": 1, "sitemap": 0})
    links_queued: int = 0
    links_dropped_limit: int = 0
    skipped_depth: int = 0
    throttle_waits: int = 0
    throttle_wait_seconds: float = 0.0
    page_seconds: list = field(default_factory=list)  # [(秒數, 網址)]
    # 同路徑只差語系參數的網址：先記鍵，其他語言版延後（2026-10-20）
    variant_keys: set[str] = field(default_factory=set)
    language_variants: deque = field(default_factory=deque)
    render_ready: list = field(default_factory=list)  # [(狀態, 毫秒, 網址)]

    def take_accessibility_slot(self) -> bool:
        if not self.run_accessibility or self.accessibility_runs >= settings.ARGUS_AXE_MAX_PAGES:
            return False
        self.accessibility_runs += 1
        return True

    def __post_init__(self) -> None:
        self.queue.append((self.start_url, 0))

    def next_target(self, robot_parser: RobotFileParser, respect_robots: bool):
        """取下一個要爬的 (url, depth)；已造訪、超過深度或被 robots.txt 禁止的直接略過。"""
        while (self.queue or self.language_variants) and len(self.pages) < self.max_pages:
            if not self.queue:
                # 新內容都爬完了，才輪到其他語言版
                self.queue.append(self.language_variants.popleft())
                self.links_queued += 1
            url, depth = self.queue.popleft()
            if url in self.visited:
                continue
            if depth > self.max_depth:
                self.skipped_depth += 1
                continue
            self.visited.add(url)
            if respect_robots and not robot_parser.can_fetch(
                settings.ARGUS_SCANNER_USER_AGENT,
                url,
            ):
                self.warnings["blocked_urls"].append({"url": url, "reason": "robots.txt"})
                continue
            return url, depth
        return None

    def seed(self, urls: list[str], depth: int = 1) -> int:
        """把 sitemap 等來源的網址放進佇列（不超過頁數上限）；回傳實際加入的數量。"""
        queued = {url for url, _ in self.queue}
        added = 0
        for url in urls:
            if len(self.queue) >= self.max_pages:
                break
            if url in queued or url in self.visited:
                continue
            self.queue.append((url, depth))
            queued.add(url)
            added += 1
        self.seeds["sitemap"] += added
        return added

    def _variant_key(self, url: str) -> str:
        """去掉語系查詢參數後的網址：`?Lang=zh-tw` 與 `?Lang=en` 是同一篇內容的兩個語言版。"""
        parts = urlsplit(url)
        kept = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _LANGUAGE_QUERY_KEYS
        ]
        if len(kept) == len(parse_qsl(parts.query, keep_blank_values=True)):
            return ""
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))

    def enqueue_links(self, links: list[str], depth: int) -> None:
        # 已在佇列裡的不重複排入：重複項目會佔掉頁數上限的名額，把沒排到的新頁面擠掉
        # （2026-10-08 爬取預算紀錄發現 sitemap 已排入的頁面又被首頁連結排一次）
        # 同一篇內容的其他語言版（只差 Lang／lang／locale 參數）排在所有新內容之後：
        # 2026-10-19 實掃 50 頁額度有一半花在 zh-tw／en 兩份一樣的頁面，389 個新頁面沒排到
        queued = {url for url, _ in self.queue}
        for link in links:
            if link in self.visited or link in queued:
                continue
            queued.add(link)
            variant = self._variant_key(link)
            if variant and variant in self.variant_keys:
                self.language_variants.append((link, depth + 1))
                continue
            if variant:
                self.variant_keys.add(variant)
            if len(self.pages) + len(self.queue) < self.max_pages:
                self.queue.append((link, depth + 1))
                self.links_queued += 1
            else:
                self.links_dropped_limit += 1

    def budget_summary(self, stop_reason: str, elapsed_seconds: float) -> dict:
        """爬取預算摘要（寫進 warning_summary["crawl_budget"]）。"""
        timings = sorted(self.page_seconds, key=lambda item: -item[0])
        return {
            "stop_reason": stop_reason,
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "pages": len(self.pages),
            "seeds": dict(self.seeds),
            "links_queued": self.links_queued,
            "links_dropped_limit": self.links_dropped_limit,
            "language_variants_deferred": len(self.language_variants),
            "skipped_depth": self.skipped_depth,
            "skipped_robots": sum(
                1 for row in self.warnings["blocked_urls"] if row.get("reason") == "robots.txt"
            ),
            "failed": len(self.warnings["failed_urls"]),
            "throttle_waits": self.throttle_waits,
            "throttle_wait_ms": round(self.throttle_wait_seconds * 1000),
            "elapsed_ms": round(elapsed_seconds * 1000),
            "page_ms_avg": (
                round(sum(s for s, _ in timings) / len(timings) * 1000) if timings else None
            ),
            "slowest_pages": [
                {"url": url, "ms": round(seconds * 1000)} for seconds, url in timings[:3]
            ],
            "render_readiness": self._render_summary(),
        }

    def _render_summary(self) -> dict | None:
        if not self.render_ready:
            return None
        counts = {status: 0 for status in ("ready", "timeout", "error")}
        for status, _ms, _url in self.render_ready:
            counts[status] = counts.get(status, 0) + 1
        return {
            **counts,
            "avg_ms": round(sum(ms for _s, ms, _u in self.render_ready) / len(self.render_ready)),
            "timeout_urls": [
                url for status, _ms, url in self.render_ready if status == "timeout"
            ][:5],
        }

    def progress(self) -> tuple[int, int]:
        done = len(self.visited)
        return done, min(len(self.visited) + len(self.queue), self.max_pages)


class _PageStage:
    """目前做到哪一步（失敗時寫進 failed_urls 的 reason，例如 "navigation:TimeoutError"）。"""

    def __init__(self) -> None:
        self.name = "new_page"


def _empty_capture(js_errors: list[str]) -> dict:
    """被阻擋／跨網域／過大的頁面：不保留任何內容，只留紀錄。"""
    js_errors.clear()
    return {
        "title": "",
        "html": "",
        "html_only": "",
        "links": [],
        "element_boxes": {},
        "layout_metrics": {},
        "ux_signals": {},
        "a11y": {},
        "screenshot_path": None,
        "mobile_screenshot_path": None,
    }


async def _throttle(state: _CrawlState, min_interval: float) -> None:
    """per-origin 速率限制：主動模式 RPS <= 2。"""
    wait_seconds = min_interval - (time.perf_counter() - state.last_request_at)
    if wait_seconds > 0:
        state.throttle_waits += 1
        state.throttle_wait_seconds += wait_seconds
        await asyncio.sleep(wait_seconds)
    state.last_request_at = time.perf_counter()


def _observe_api_response(resp, sink: dict[str, dict], body_tasks: list) -> None:
    """記下一個 same-origin API 回應的摘要（方法、路徑、狀態、少數標頭）；錯誤回應另讀內容。"""
    if len(sink) >= _MAX_API_OBSERVATIONS:
        return
    method = (resp.request.method or "GET").upper()
    path = urlparse(resp.url).path or "/"
    if path.startswith("/cdn-cgi/"):
        # Cloudflare 注入的量測／驗證端點（/cdn-cgi/rum 等），不是網站自己的 API
        return
    key = f"{method} {path}"
    if key in sink:
        return
    headers = resp.headers or {}
    observation = {
        "method": method,
        "path": path,
        "status": resp.status,
        "headers": {k: str(headers[k])[:200] for k in _API_HEADER_KEYS if headers.get(k)},
    }
    sink[key] = observation
    content_type = str(headers.get("content-type", "")).lower()
    if resp.status >= 400 and any(t in content_type for t in ("json", "text", "html", "xml")):
        body_tasks.append(asyncio.ensure_future(_read_api_error_body(resp, observation)))


async def _read_api_error_body(resp, observation: dict) -> None:
    try:
        observation["error_body"] = (await resp.text())[:_API_BODY_LIMIT]
    except Exception:
        pass


async def _finish_api_body_tasks(body_tasks: list) -> None:
    """關閉分頁前等錯誤回應內容讀完（最多 2 秒，讀不到就算了）。"""
    if body_tasks:
        await asyncio.wait(body_tasks, timeout=2)


def _collect_js_api_paths(resp, sink: set[str], body_tasks: list, state=None) -> None:
    """同源 JS 回應：讀內容抽 API 路徑進 sink（繞過 Cloudflare 的確定性端點發現）。

    只讀 script 資源、同源、數量與大小有上限；body 讀完即丟，只留抽出的路徑。
    """
    if state is not None:
        if state.js_bodies_read >= _MAX_JS_BODIES or len(sink) >= _MAX_JS_API_PATHS:
            return
        state.js_bodies_read += 1

    async def _read() -> None:
        try:
            headers = resp.headers or {}
            length = headers.get("content-length")
            if length and int(length) > _MAX_JS_BODY_BYTES:
                return
            body = (await resp.text())[:_MAX_JS_BODY_BYTES]
            for path in extract_api_paths_from_js(body):
                if len(sink) >= _MAX_JS_API_PATHS:
                    break
                sink.add(path)
            if state is not None:
                _collect_js_secrets(body, resp.url, state)
        except Exception:
            pass

    body_tasks.append(asyncio.ensure_future(_read()))


def _collect_js_secrets(body: str, url: str, state) -> None:
    """外部 JS bundle 的秘鑰偵測（ADR-0005 §1）：crawler 已把 bytes 讀進來，順手掃。

    與 Argus 既有「HTML／inline script 秘鑰」互補——那只掃頁面本身，不掃外部 .js。
    跨檔以 (kind, masked) 去重（同一把金鑰出現在多個 chunk 只記一次）。
    """
    from apps.scans.security.secret_scanner import detect_secrets_in_text

    if len(state.js_secrets) >= _MAX_JS_SECRETS:
        return
    for secret in detect_secrets_in_text(body):
        dedupe_key = (secret.get("kind", ""), secret.get("masked", ""))
        if dedupe_key in state.js_secret_keys:
            continue
        state.js_secret_keys.add(dedupe_key)
        state.js_secrets.append({**secret, "source": url})
        if len(state.js_secrets) >= _MAX_JS_SECRETS:
            break


def _attach_page_listeners(
    page, origin: str, api_endpoints: set[str],
    api_observations: dict[str, dict] | None = None, body_tasks: list | None = None,
    js_api_paths: set[str] | None = None, state=None,
) -> list[str]:
    """掛上被動監聽：same-origin XHR/fetch 端點、本頁 JavaScript 執行期錯誤。回傳錯誤清單。

    SPA 的 API 呼叫只存在於真實瀏覽器流量：被動攔截 same-origin 端點，供 Nuclei／sqlmap／
    Agent 作為攻擊面輸入；這裡不發任何新請求，只是觀察頁面自己發出的流量。
    未捕捉的 JS 例外會中斷該頁腳本，常導致按鈕沒反應、內容載不出來：只收錯誤訊息首行
    （去重、設上限），作為 UX 可用性訊號。
    """

    def _on_response(resp, _origin=origin, _sink=api_endpoints):
        try:
            rtype = resp.request.resource_type
            if url_origin(resp.url) != _origin:
                return
            # 同源 JS：讀內容抽 API 路徑（確定性端點發現；瀏覽器已載入，不另發請求）
            if (
                js_api_paths is not None
                and body_tasks is not None
                and (rtype == "script" or urlparse(resp.url).path.lower().endswith(".js"))
            ):
                _collect_js_api_paths(resp, js_api_paths, body_tasks, state)
                return
            if rtype not in {"xhr", "fetch"}:
                return
            # 靜態資源（Next.js 用 fetch 預取的 CSS 等）不是 API 呼叫，不收進端點清單
            if is_static_asset_path(urlparse(resp.url).path):
                return
            if len(_sink) < _MAX_API_ENDPOINTS:
                _sink.add(resp.url)
            if api_observations is not None and body_tasks is not None:
                _observe_api_response(resp, api_observations, body_tasks)
        except Exception:
            pass

    page_js_errors: list[str] = []

    def _on_page_error(exc, _sink=page_js_errors):
        try:
            msg = str(exc).strip().splitlines()[0][:200]
            if msg and msg not in _sink and len(_sink) < _MAX_UX_OFFENDERS:
                _sink.append(msg)
        except Exception:
            pass

    page.on("response", _on_response)
    page.on("pageerror", _on_page_error)
    return page_js_errors


async def _capture_content(
    page,
    response,
    *,
    url: str,
    final_url: str,
    origin: str,
    headers: dict,
    status_code,
    screenshot_target: Path | None,
    warnings: dict,
    stage: _PageStage,
    js_errors: list[str],
    run_accessibility: bool = False,
) -> tuple[dict, str]:
    """擷取同源頁面的內容、截圖、連結與量測；回傳 (capture, blocked_reason)。

    超大回應（PDF／影片／gzip bomb）在 Content-Length 就攔下，跳過 scroll／content／
    screenshot 等耗記憶體操作，避免 worker 被單頁撐爆。
    """
    oversized_reason = classify_oversized(headers)
    if oversized_reason:
        return _empty_capture(js_errors), oversized_reason

    stage.name = "content"
    await scroll_to_bottom(page)
    capture = {"title": await page.title(), "html": await page.content()}
    try:
        capture["html_only"] = await response.text() if response else ""
    except Exception:
        capture["html_only"] = ""
    # 二次檢查：無 Content-Length 時用實際 body 大小 fallback；再看 body 是否為 CF
    # challenge——CF 常回 200 但 body 是攔截頁，必須在 status code 判斷之前先攔下，
    # 否則 scanners 會誤判為真實內容。
    blocked_reason = (
        classify_oversized(None, capture["html"])
        or classify_cf_challenge(capture["html"])
        or classify_blocked(status_code)
    )
    # 版面位移要在截圖前量：整頁截圖會改變視窗大小。被阻擋的錯誤頁不量。
    stage.name = "layout_shift"
    capture["layout_shift"] = {} if blocked_reason else await collect_layout_shift(page)
    # 被阻擋的頁面仍拍截圖供人工核對；截圖失敗只讓這一頁沒有圖，不影響其餘分析。
    stage.name = "screenshot"
    capture["screenshot_path"] = (
        await _capture_screenshot(page, screenshot_target, url, warnings)
        if screenshot_target is not None
        else None
    )
    # 被阻擋的頁面不再往下擷取連結，避免在錯誤頁上繼續爬取
    stage.name = "links"
    capture["links"] = [] if blocked_reason else await extract_links(page, final_url, origin)
    stage.name = "element_boxes"
    capture["element_boxes"] = await collect_element_boxes(page)
    # axe-core：在桌面版視窗、內容與截圖都擷取完之後跑（會注入腳本，不能影響已保存的 HTML），
    # 且必須在行動版量測之前（那一步會改 viewport）。被阻擋的錯誤頁不檢查。
    capture["a11y"] = {}
    if run_accessibility and not blocked_reason:
        stage.name = "accessibility"
        capture["a11y"] = await run_axe(page, timeout_seconds=settings.ARGUS_AXE_TIMEOUT_SECONDS)
    # 一定要放最後：會改 viewport，跑在截圖或內容擷取之前會讓那些結果變成行動版的
    stage.name = "mobile_layout"
    capture["layout_metrics"] = await collect_mobile_layout(page)
    # 仍在行動版視窗時量互動可用性訊號（觸控目標、表單標籤）
    stage.name = "ux_signals"
    capture["ux_signals"] = await collect_ux_signals(page)
    # 有行動版 UX 問題時另拍一張行動版截圖，問題標註才能框住真正的元素
    # （觸控目標是在 375px 寬量的，桌面版截圖上的位置與大小都對不上）
    capture["mobile_screenshot_path"] = None
    if screenshot_target is not None and _has_mobile_offenders(capture):
        stage.name = "mobile_screenshot"
        capture["mobile_screenshot_path"] = await _capture_screenshot(
            page, screenshot_target.with_name(f"{screenshot_target.stem}-mobile.png"), url, warnings
        )
    return capture, blocked_reason


def _has_mobile_offenders(capture: dict) -> bool:
    signals = capture.get("ux_signals") or {}
    layout = capture.get("layout_metrics") or {}
    return bool(
        signals.get("small_tap_targets")
        or signals.get("unlabeled_fields")
        or layout.get("offenders")
    )


async def _capture_same_origin_page(page, response, **kwargs) -> tuple[dict, str]:
    """在「擷取期間沒有被 JS 導去其他網域」的保護下擷取內容。

    只在 goto 完成時檢查一次 page.url 不夠：setTimeout、meta refresh 可能在之後的
    scroll／content／screenshot 期間才導轉（TOCTOU）。framenavigated 事件會即時標記，
    擷取結束後若曾離開授權網域，就丟棄內容與截圖。
    """
    origin = kwargs["origin"]
    navigated_off_origin = {"flag": False}

    def _on_frame_navigated(frame, _page=page, _origin=origin, _flag=navigated_off_origin):
        if frame != _page.main_frame:
            return
        try:
            if frame.url and url_origin(frame.url) != _origin:
                _flag["flag"] = True
        except Exception:
            pass

    page.on("framenavigated", _on_frame_navigated)
    try:
        capture, blocked_reason = await _capture_content(page, response, **kwargs)
    finally:
        page.remove_listener("framenavigated", _on_frame_navigated)

    if navigated_off_origin["flag"] and not blocked_reason:
        for key in ("screenshot_path", "mobile_screenshot_path"):
            if capture.get(key) is not None:
                capture[key].unlink(missing_ok=True)
        return _empty_capture(kwargs["js_errors"]), _CROSS_ORIGIN_REASON
    return capture, blocked_reason


def _page_record(
    *,
    url: str,
    depth: int,
    final_url: str,
    final_url_origin: str,
    status_code,
    headers: dict,
    capture: dict,
    blocked_reason: str,
    js_errors: list[str],
    load_time_ms: int,
) -> dict:
    """crawl_site 回傳的單頁資料（tasks.py 落地成 Page，並交給各 scanner 分析）。"""
    screenshot_path = capture["screenshot_path"]
    layout_metrics = dict(capture["layout_metrics"] or {})
    if capture.get("layout_shift"):
        layout_metrics["layout_shift"] = capture["layout_shift"]
    if capture.get("mobile_screenshot_path") is not None:
        layout_metrics["mobile_screenshot"] = str(
            capture["mobile_screenshot_path"].relative_to(settings.BASE_DIR)
        )
    return {
        "url": url,
        "final_url": final_url,
        "origin": final_url_origin,
        "status_code": status_code,
        "title": capture["title"],
        "html": capture["html"],
        "rendered_dom": capture["html"],
        "html_only": capture["html_only"],
        "screenshot_path": (
            str(screenshot_path.relative_to(settings.BASE_DIR))
            if screenshot_path is not None
            else ""
        ),
        "load_time_ms": load_time_ms,
        "depth": depth,
        "blocked_reason": blocked_reason,
        "outgoing_links": capture["links"],
        "headers": headers,
        "element_boxes": capture["element_boxes"],
        "layout_metrics": layout_metrics,
        "ux_signals": capture["ux_signals"],
        "a11y": capture.get("a11y") or {},
        "js_errors": list(js_errors),
    }


async def _visit_page(
    context,
    state: _CrawlState,
    url: str,
    depth: int,
    *,
    screenshot_dir: Path | None,
    stage: _PageStage,
) -> dict:
    """開一個分頁造訪單一網址並回傳單頁資料；Playwright 例外交給呼叫端處理。"""
    started_at = time.perf_counter()
    origin = state.origin
    page = None
    body_tasks: list = []
    try:
        # new_page() 在 try 裡：context/browser 偶發損壞時只讓這一頁失敗
        page = await context.new_page()
        js_errors = _attach_page_listeners(
            page, origin, state.api_endpoints, state.api_observations, body_tasks,
            state.js_api_paths, state,
        )
        stage.name = "navigation"
        # 不等 networkidle：分析工具、客服 widget、長輪詢常讓網路永遠無法完全安靜；
        # 之後由 wait_for_render_ready 等 DOM 穩定（有上限），scroll_to_bottom 再觸發延遲載入。
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        stage.name = "response_headers"
        headers = await response.all_headers() if response else {}
        status_code = response.status if response else None
        stage.name = "final_url"
        final_url = normalize_crawl_url(assert_public_http_url(page.url))
        final_url_origin = url_origin(final_url) if final_url else origin

        ready_ms = 0
        if final_url_origin != origin:
            # 伺服器端 redirect 導去公開但非授權的網域：不分析其內容
            capture, blocked_reason = _empty_capture(js_errors), _CROSS_ORIGIN_REASON
        else:
            stage.name = "render_ready"
            readiness = await wait_for_render_ready(
                page, settings.ARGUS_RENDER_READY_MAX_SECONDS
            )
            state.render_ready.append((readiness["status"], readiness["ms"], url))
            ready_ms = readiness["ms"]
            capture, blocked_reason = await _capture_same_origin_page(
                page,
                response,
                url=url,
                final_url=final_url,
                origin=origin,
                headers=headers,
                status_code=status_code,
                screenshot_target=(
                    screenshot_dir / f"page-{len(state.pages) + 1}.png"
                    if screenshot_dir is not None
                    else None
                ),
                warnings=state.warnings,
                stage=stage,
                js_errors=js_errors,
                run_accessibility=state.take_accessibility_slot(),
            )
        return _page_record(
            url=url,
            depth=depth,
            final_url=final_url,
            final_url_origin=final_url_origin,
            status_code=status_code,
            headers=headers,
            capture=capture,
            blocked_reason=blocked_reason,
            js_errors=js_errors,
            # 等內容穩定的時間是 Argus 的量測動作，不算進頁面載入時間（SEO「載入慢」依此判斷）
            load_time_ms=round((time.perf_counter() - started_at) * 1000) - ready_ms,
        )
    finally:
        await _finish_api_body_tasks(body_tasks)
        await _close_playwright_resources(page)


def _record_page_failure(
    state: _CrawlState, url: str, depth: int, exc: Exception, stage: _PageStage
) -> None:
    """Playwright 錯誤先重試（排回佇列最前面），超過上限才記為失敗；其他例外直接記失敗。"""
    if isinstance(exc, PlaywrightError):
        retry_count = state.page_retry_counts.get(url, 0)
        if retry_count < _PAGE_RETRY_LIMIT:
            state.page_retry_counts[url] = retry_count + 1
            state.visited.discard(url)
            state.queue.appendleft((url, depth))
            return
        reason = (
            "timeout"
            if isinstance(exc, PlaywrightTimeoutError)
            else f"{stage.name}:{exc.__class__.__name__}"
        )
    else:
        reason = f"{stage.name}:{exc.__class__.__name__}"
    state.warnings["failed_urls"].append({"url": url, "reason": reason})


async def _recycle_context(
    browser, context, origin: str, state: _CrawlState, url: str, har_path: Path | None = None
):
    """每爬 _CONTEXT_RECYCLE_EVERY 頁換一個 browser context（釋放記憶體）。

    回傳新的 context；browser process 已死、開不出新 context 時回 None，
    呼叫端以目前已收集的頁面正常結束，不讓例外害已爬到的頁面全部遺失。
    """
    try:
        await context.close()
        return await _make_context(browser, origin, har_path)
    except Exception as exc:
        state.warnings["failed_urls"].append(
            {"url": url, "reason": f"context_recycle_failed:{exc.__class__.__name__}"}
        )
        return None


async def _report_progress(state: _CrawlState, progress_callback) -> None:
    """回報進度（同時是取消檢查點）：ScanCancelled 往上拋，其他 callback 錯誤不影響爬蟲。"""
    if progress_callback is None:
        return
    done, total = state.progress()
    try:
        await progress_callback(done, total)
    except ScanCancelled:
        raise
    except Exception:
        pass


async def crawl_site(
    *,
    start_url: str,
    origin: str,
    scan_job_id: int,
    scan_mode: str,
    max_depth: int,
    max_pages: int,
    respect_robots: bool,
    progress_callback=None,
    run_accessibility: bool = False,
    har_dir: Path | None = None,
) -> tuple[list[dict], dict, dict, list[str]]:
    """爬整站（同網域 BFS）。

    progress_callback：可選的 async callable，每爬完一頁（含失敗/被擋）就會呼叫
    `await progress_callback(pages_done, pages_total_estimated)`，
    讓上層即時寫進 ScanJob.progress 供前端輪詢顯示百分比與 ETA。
    callback 失敗不影響爬蟲本身。

    回傳第四個值 discovered_endpoints：爬取過程中瀏覽器**被動發出**的
    same-origin XHR/fetch 端點（SPA 的 API 呼叫不在 <a href> 裡，只有
    攔截真實流量才看得到）。僅觀察既有請求，不新增任何連線。

    每頁的流程：_throttle（速率限制）→ _visit_page（導覽、擷取、組單頁資料）→
    enqueue_links；失敗走 _record_page_failure（重試或記錄），每頁結束後視需要
    _recycle_context 並 _report_progress。

    har_dir：有值時每個 browser context 各錄一個 HAR（`context-N.har`，只含同 origin 流量），
    供 ZAP 被動分析；呼叫端負責刪除。
    """
    state = _CrawlState(start_url, origin, max_depth, max_pages)
    state.run_accessibility = run_accessibility
    robot_parser = load_robot_parser(origin)
    min_interval = compute_min_interval(
        scan_mode,
        active_rps=settings.ARGUS_ACTIVE_MAX_RPS,
        passive_rps=settings.ARGUS_PASSIVE_MAX_RPS,
    )
    screenshot_dir = _prepare_screenshot_dir(
        Path(settings.MEDIA_ROOT) / "scans" / str(scan_job_id), state.warnings
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            **playwright_launch_kwargs(),
        )
        # 結果可重現：記下實際使用的瀏覽器版本（渲染結果與 axe-core 判定都依賴它）
        state.warnings["tools"] = {"Chromium": browser.version}
        har_count = 0

        def _next_har() -> Path | None:
            nonlocal har_count
            if har_dir is None:
                return None
            har_count += 1
            return har_dir / f"context-{har_count}.har"

        context = await _make_context(browser, origin, _next_har())
        pages_in_context = 0
        crawl_started = time.perf_counter()
        stop_reason = "queue_exhausted"
        try:
            site_signals = await probe_site_signals(context, origin, robot_parser)
            if max_pages > 1:
                sitemap_urls = await discover_sitemap_urls(
                    context, origin, site_signals.get("robots_sitemaps") or [], max_pages,
                    site_signals.get("fetched"),
                )
                site_signals["sitemap_seeded"] = state.seed(sitemap_urls)
                site_signals["sitemap_urls"] = sitemap_urls
            while (target := state.next_target(robot_parser, respect_robots)) is not None:
                url, depth = target
                await _throttle(state, min_interval)
                stage = _PageStage()
                context_broken = False
                page_started = time.perf_counter()
                try:
                    record = await _visit_page(
                        context, state, url, depth, screenshot_dir=screenshot_dir, stage=stage
                    )
                    state.page_seconds.append((time.perf_counter() - page_started, url))
                    state.pages.append(record)
                    if record["blocked_reason"]:
                        state.warnings["blocked_urls"].append(
                            {"url": url, "reason": record["blocked_reason"]}
                        )
                    state.enqueue_links(record["outgoing_links"], depth)
                except Exception as exc:
                    _record_page_failure(state, url, depth, exc, stage)
                finally:
                    pages_in_context += 1
                    if pages_in_context >= _CONTEXT_RECYCLE_EVERY:
                        new_context = await _recycle_context(
                            browser, context, origin, state, url, _next_har()
                        )
                        if new_context is None:
                            context_broken = True
                        else:
                            context = new_context
                            pages_in_context = 0
                    if not context_broken:
                        await _report_progress(state, progress_callback)
                # break 特意放在 finally 外：ruff B012 禁止在 finally 裡 break
                # （若當時有例外正在傳遞，finally 裡的 break 會把它悄悄吞掉）。
                if context_broken:
                    stop_reason = "browser_failed"
                    break
            if stop_reason == "queue_exhausted" and len(state.pages) >= max_pages:
                stop_reason = "max_pages"
        finally:
            await _close_playwright_resources(context, browser)
            state.warnings["crawl_budget"] = state.budget_summary(
                stop_reason, time.perf_counter() - crawl_started
            )
    site_signals["api_observations"] = list(state.api_observations.values())
    # JS bundle 靜態抽出的 API 路徑（供敏感檔案探測推 API 前綴；繞過 Cloudflare）
    site_signals["js_api_paths"] = sorted(state.js_api_paths)
    site_signals["js_secrets"] = state.js_secrets
    return state.pages, state.warnings, site_signals, sorted(state.api_endpoints)
