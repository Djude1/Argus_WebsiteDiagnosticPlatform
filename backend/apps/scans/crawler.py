import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
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

# Cloudflare Turnstile / Managed Challenge 特徵字串。
# 這類驗證需要使用者互動（點擊勾選框），headless 瀏覽器無法自動通過。
CF_TURNSTILE_MARKERS = (
    "cf-turnstile",
    "turnstile-wrapper",
    "cf-chl-bypass",
    "challenge-running",
)

# Cloudflare JavaScript challenge 特徵字串。
# CF 邊緣注入的 challenge 載入器，body 出現這些字串代表此頁是攔截頁，不是真實內容。
# 不收錄「Just a moment」短語，避免正常網站文章正文恰好出現該短語的 false positive。
# 不收錄裸字串 "challenge-platform"：開啟 Bot 偵測的站，CF 會在「每一個正常頁面」尾端插入
# /cdn-cgi/challenge-platform/scripts/（jsd、precursor）背景腳本；攔截頁才會載入 /h/ 下的
# orchestrate 並帶 _cf_chl_opt。2026-10-02 ntubimdbirc.tw 首頁因此被誤判、整站只爬到 1 頁。
CF_JS_CHALLENGE_MARKERS = (
    "/cdn-cgi/challenge-platform/h/",
    "_cf_chl_opt",
    "cf-browser-verification",
    "cf_captcha",
)

# 用於診斷的主流 AI 爬蟲 User-Agent；僅檢查 robots.txt 規則，不繞過任何限制
AI_CRAWLER_USER_AGENTS = ("GPTBot", "ClaudeBot", "Google-Extended", "PerplexityBot")


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

    Turnstile 優先於一般 JS challenge：兩者並存時前者更嚴重（必擋）。
    CF challenge 經常回 200 status code 但 body 是攔截頁，若交給 scanners 分析
    會誤判為「H1 缺失、meta 缺失」等假 finding，因此須在爬蟲層攔下並設為 blocked。
    """
    if not html:
        return ""
    if any(marker in html for marker in CF_TURNSTILE_MARKERS):
        return "Cloudflare Turnstile 驗證，需使用者互動才能通過"
    if any(marker in html for marker in CF_JS_CHALLENGE_MARKERS):
        return "Cloudflare JavaScript 驗證，自動掃描無法通過"
    return ""


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
    from apps.scans.security.exposure_scanner import parse_robots_disallow

    signals: dict = {
        "llms_txt_found": False,
        "blocked_ai_crawlers": [],
        "robots_disallow": [],
        "robots_sitemaps": [],
    }
    try:
        llms_url = assert_public_http_url(f"{origin}/llms.txt")
        response = await context.request.get(llms_url, timeout=10000, max_redirects=0)
        signals["llms_txt_found"] = response.ok
    except Exception:
        signals["llms_txt_found"] = False
    try:
        robots_url = assert_public_http_url(f"{origin}/robots.txt")
        resp = await context.request.get(robots_url, timeout=10000, max_redirects=0)
        if resp.ok:
            robots_text = await resp.text()
            robot_parser.parse(robots_text.splitlines())
            signals["robots_disallow"] = parse_robots_disallow(robots_text)
            signals["robots_sitemaps"] = parse_robots_sitemaps(robots_text)
    except Exception:
        signals["robots_disallow"] = []
    for agent in AI_CRAWLER_USER_AGENTS:
        if not robot_parser.can_fetch(agent, f"{origin}/"):
            signals["blocked_ai_crawlers"].append(agent)
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


async def _fetch_sitemap(context, url: str, origin: str) -> str:
    """抓單一 sitemap（同源、公開位址、不跟隨轉址）；失敗或過大回空字串。"""
    try:
        if not same_origin(url, origin) or url.lower().endswith(".gz"):
            return ""
        response = await context.request.get(
            assert_public_http_url(url), timeout=10000, max_redirects=0
        )
        if not response.ok:
            return ""
        body = await response.body()
        if len(body) > _SITEMAP_MAX_BYTES:
            return ""
        return body.decode("utf-8", errors="replace")
    except Exception:
        return ""


async def discover_sitemap_urls(context, origin: str, declared: list[str], limit: int) -> list[str]:
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
        text = await _fetch_sitemap(context, sitemap_url, origin)
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
_MIN_TAP_TARGET_PX = 40
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
                ({ minTap, maxOffenders }) => {
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
                    for (const el of document.body.querySelectorAll(tapSel)) {
                        const rect = el.getBoundingClientRect();
                        if (!isVisible(el, rect)) continue;
                        if (rect.width >= minTap && rect.height >= minTap) continue;
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
                {"minTap": _MIN_TAP_TARGET_PX, "maxOffenders": _MAX_UX_OFFENDERS},
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


async def _make_context(browser, origin: str):
    """建立標準 scanner 瀏覽器 context（user-agent + viewport）。"""
    context = await browser.new_context(
        user_agent=settings.ARGUS_SCANNER_USER_AGENT,
        viewport={"width": 1440, "height": 1000},
        service_workers="block",
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
    page_retry_counts: dict[str, int] = field(default_factory=dict)
    last_request_at: float = 0.0
    # axe-core 無障礙檢查：勾 UX 才開；最多檢查 ARGUS_AXE_MAX_PAGES 頁
    run_accessibility: bool = False
    accessibility_runs: int = 0

    def take_accessibility_slot(self) -> bool:
        if not self.run_accessibility or self.accessibility_runs >= settings.ARGUS_AXE_MAX_PAGES:
            return False
        self.accessibility_runs += 1
        return True

    def __post_init__(self) -> None:
        self.queue.append((self.start_url, 0))

    def next_target(self, robot_parser: RobotFileParser, respect_robots: bool):
        """取下一個要爬的 (url, depth)；已造訪、超過深度或被 robots.txt 禁止的直接略過。"""
        while self.queue and len(self.pages) < self.max_pages:
            url, depth = self.queue.popleft()
            if url in self.visited or depth > self.max_depth:
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
        return added

    def enqueue_links(self, links: list[str], depth: int) -> None:
        for link in links:
            if link not in self.visited and len(self.pages) + len(self.queue) < self.max_pages:
                self.queue.append((link, depth + 1))

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
        await asyncio.sleep(wait_seconds)
    state.last_request_at = time.perf_counter()


def _attach_page_listeners(page, origin: str, api_endpoints: set[str]) -> list[str]:
    """掛上被動監聽：same-origin XHR/fetch 端點、本頁 JavaScript 執行期錯誤。回傳錯誤清單。

    SPA 的 API 呼叫只存在於真實瀏覽器流量：被動攔截 same-origin 端點，供 Nuclei／sqlmap／
    Agent 作為攻擊面輸入；這裡不發任何新請求，只是觀察頁面自己發出的流量。
    未捕捉的 JS 例外會中斷該頁腳本，常導致按鈕沒反應、內容載不出來：只收錯誤訊息首行
    （去重、設上限），作為 UX 可用性訊號。
    """

    def _on_response(resp, _origin=origin, _sink=api_endpoints):
        try:
            if resp.request.resource_type not in {"xhr", "fetch"}:
                return
            if url_origin(resp.url) != _origin:
                return
            if len(_sink) < _MAX_API_ENDPOINTS:
                _sink.add(resp.url)
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
    try:
        # new_page() 在 try 裡：context/browser 偶發損壞時只讓這一頁失敗
        page = await context.new_page()
        js_errors = _attach_page_listeners(page, origin, state.api_endpoints)
        stage.name = "navigation"
        # 不等 networkidle：分析工具、客服 widget、長輪詢常讓網路永遠無法完全安靜；
        # 後續 scroll_to_bottom 本身會讓動態內容有時間渲染。
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        stage.name = "response_headers"
        headers = await response.all_headers() if response else {}
        status_code = response.status if response else None
        stage.name = "final_url"
        final_url = normalize_crawl_url(assert_public_http_url(page.url))
        final_url_origin = url_origin(final_url) if final_url else origin

        if final_url_origin != origin:
            # 伺服器端 redirect 導去公開但非授權的網域：不分析其內容
            capture, blocked_reason = _empty_capture(js_errors), _CROSS_ORIGIN_REASON
        else:
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
            load_time_ms=round((time.perf_counter() - started_at) * 1000),
        )
    finally:
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


async def _recycle_context(browser, context, origin: str, state: _CrawlState, url: str):
    """每爬 _CONTEXT_RECYCLE_EVERY 頁換一個 browser context（釋放記憶體）。

    回傳新的 context；browser process 已死、開不出新 context 時回 None，
    呼叫端以目前已收集的頁面正常結束，不讓例外害已爬到的頁面全部遺失。
    """
    try:
        await context.close()
        return await _make_context(browser, origin)
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
        context = await _make_context(browser, origin)
        pages_in_context = 0
        try:
            site_signals = await probe_site_signals(context, origin, robot_parser)
            if max_pages > 1:
                sitemap_urls = await discover_sitemap_urls(
                    context, origin, site_signals.get("robots_sitemaps") or [], max_pages
                )
                site_signals["sitemap_seeded"] = state.seed(sitemap_urls)
            while (target := state.next_target(robot_parser, respect_robots)) is not None:
                url, depth = target
                await _throttle(state, min_interval)
                stage = _PageStage()
                context_broken = False
                try:
                    record = await _visit_page(
                        context, state, url, depth, screenshot_dir=screenshot_dir, stage=stage
                    )
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
                        new_context = await _recycle_context(browser, context, origin, state, url)
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
                    break
        finally:
            await _close_playwright_resources(context, browser)
    return state.pages, state.warnings, site_signals, sorted(state.api_endpoints)
