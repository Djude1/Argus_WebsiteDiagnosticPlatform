import asyncio
import time
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

from config.egress import playwright_launch_kwargs
from django.conf import settings
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

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
CF_JS_CHALLENGE_MARKERS = (
    "challenge-platform",
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


def same_origin(url: str, origin: str) -> bool:
    parsed = urlparse(url)
    target_origin = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        target_origin = f"{target_origin}:{parsed.port}"
    return target_origin == origin


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

    signals: dict = {"llms_txt_found": False, "blocked_ai_crawlers": [], "robots_disallow": []}
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
    except Exception:
        signals["robots_disallow"] = []
    for agent in AI_CRAWLER_USER_AGENTS:
        if not robot_parser.can_fetch(agent, f"{origin}/"):
            signals["blocked_ai_crawlers"].append(agent)
    return signals


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


async def extract_links(page, base_url: str, origin: str) -> list[str]:
    hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(el => el.href)")
    links: list[str] = []
    for href in hrefs:
        normalized = normalize_crawl_url(urljoin(base_url, href))
        if not normalized or not same_origin(normalized, origin):
            continue
        # 二進位/媒體檔案（.apk、.pdf、字型、圖片等）不是 HTML 頁面，
        # 加進爬蟲 queue 只會浪費請求並產生無意義的 finding。
        if is_binary_resource(normalized):
            continue
        links.append(normalized)
    return sorted(set(links))


async def scroll_to_bottom(page) -> None:
    await page.evaluate(
        """
        async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 600;
                const timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 80);
            });
            window.scrollTo(0, 0);
        }
        """
    )


_CONTEXT_RECYCLE_EVERY = 15


async def _enforce_public_request(route, request):
    """在 Playwright 發出主文件、轉址或子資源請求前驗證目的地。"""
    try:
        assert_public_http_url(request.url)
    except PublicScanTargetError:
        await route.abort("blockedbyclient")
        return
    await route.continue_()


async def _enforce_public_websocket(websocket_route):
    """禁止頁面透過 WebSocket 連往內網或保留位址。"""
    try:
        assert_public_websocket_url(websocket_route.url)
    except PublicScanTargetError:
        await websocket_route.close(code=1008, reason="Blocked by scan target policy")
        return
    websocket_route.connect_to_server()


async def _make_context(browser):
    """建立標準 scanner 瀏覽器 context（user-agent + viewport）。"""
    context = await browser.new_context(
        user_agent=settings.ARGUS_SCANNER_USER_AGENT,
        viewport={"width": 1440, "height": 1000},
        service_workers="block",
    )
    await context.route("**/*", _enforce_public_request)
    await context.route_web_socket("**/*", _enforce_public_websocket)
    return context


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
) -> tuple[list[dict], dict, dict]:
    """爬整站。

    progress_callback：可選的 async callable，每爬完一頁（含失敗/被擋）就會呼叫
    `await progress_callback(pages_done, pages_total_estimated)`，
    讓上層即時寫進 ScanJob.progress 供前端輪詢顯示百分比與 ETA。
    callback 失敗不影響爬蟲本身。
    """
    warnings: dict = {"blocked_urls": [], "failed_urls": []}
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    pages: list[dict] = []
    robot_parser = load_robot_parser(origin)
    min_interval = compute_min_interval(
        scan_mode,
        active_rps=settings.ARGUS_ACTIVE_MAX_RPS,
        passive_rps=settings.ARGUS_PASSIVE_MAX_RPS,
    )
    last_request_at = 0.0
    screenshot_dir = Path(settings.MEDIA_ROOT) / "scans" / str(scan_job_id)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            **playwright_launch_kwargs(),
        )
        context = await _make_context(browser)
        pages_in_context = 0
        try:
            site_signals = await probe_site_signals(context, origin, robot_parser)
            while queue and len(pages) < max_pages:
                url, depth = queue.popleft()
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)
                if respect_robots and not robot_parser.can_fetch(
                    settings.ARGUS_SCANNER_USER_AGENT,
                    url,
                ):
                    warnings["blocked_urls"].append({"url": url, "reason": "robots.txt"})
                    continue

                # 套用 per-origin 速率限制：主動模式 RPS <= 2
                wait_seconds = min_interval - (time.perf_counter() - last_request_at)
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                last_request_at = time.perf_counter()

                page = await context.new_page()
                started_at = time.perf_counter()
                try:
                    response = await page.goto(url, wait_until="networkidle", timeout=30000)
                    headers = await response.all_headers() if response else {}
                    status_code = response.status if response else None
                    final_url = normalize_crawl_url(assert_public_http_url(page.url))

                    # 早期 Content-Length 檢查：超大回應（PDF/影片/gzip bomb）跳過 scroll/
                    # content/screenshot 等耗記憶體操作，防止 worker 被單頁撐爆
                    oversized_reason = classify_oversized(headers)
                    if oversized_reason:
                        blocked_reason = oversized_reason
                        title = ""
                        html = ""
                        html_only = ""
                        links = []
                        element_boxes = {}
                        screenshot_path = None
                    else:
                        await scroll_to_bottom(page)
                        title = await page.title()
                        html = await page.content()
                        try:
                            html_only = await response.text() if response else ""
                        except Exception:
                            html_only = ""
                        # 二次檢查：無 Content-Length 時用實際 body 大小 fallback
                        # 再看 body 是否為 CF challenge——CF 常回 200 但 body 是攔截頁，
                        # 必須在 status code 判斷之前先攔下，否則 scanners 會誤判為真實內容。
                        blocked_reason = (
                            classify_oversized(None, html)
                            or classify_cf_challenge(html)
                            or classify_blocked(status_code)
                        )
                        screenshot_path = screenshot_dir / f"page-{len(pages) + 1}.png"
                        # 被阻擋的頁面仍拍截圖供人工核對；oversized 已在前分支返回。
                        await page.screenshot(path=str(screenshot_path), full_page=True)
                        # 被阻擋的頁面不再往下擷取連結，避免在錯誤頁上繼續爬取
                        links = (
                            []
                            if blocked_reason
                            else await extract_links(page, final_url, origin)
                        )
                        element_boxes = await collect_element_boxes(page)
                    load_time_ms = round((time.perf_counter() - started_at) * 1000)
                    pages.append(
                        {
                            "url": url,
                            "final_url": final_url,
                            "origin": origin,
                            "status_code": status_code,
                            "title": title,
                            "html": html,
                            "rendered_dom": html,
                            "html_only": html_only,
                            "screenshot_path": (
                                str(screenshot_path.relative_to(settings.BASE_DIR))
                                if screenshot_path is not None
                                else ""
                            ),
                            "load_time_ms": load_time_ms,
                            "depth": depth,
                            "blocked_reason": blocked_reason,
                            "outgoing_links": links,
                            "headers": headers,
                            "element_boxes": element_boxes,
                        }
                    )
                    if blocked_reason:
                        warnings["blocked_urls"].append({"url": url, "reason": blocked_reason})
                    for link in links:
                        if link not in visited and len(pages) + len(queue) < max_pages:
                            queue.append((link, depth + 1))
                except PlaywrightTimeoutError:
                    warnings["failed_urls"].append({"url": url, "reason": "timeout"})
                except Exception as exc:
                    warnings["failed_urls"].append({"url": url, "reason": exc.__class__.__name__})
                finally:
                    await page.close()
                    pages_in_context += 1
                    if pages_in_context >= _CONTEXT_RECYCLE_EVERY:
                        await context.close()
                        context = await _make_context(browser)
                        pages_in_context = 0
                    if progress_callback is not None:
                        done = len(visited)
                        total = min(len(visited) + len(queue), max_pages)
                        try:
                            await progress_callback(done, total)
                        except ScanCancelled:
                            # 使用者按終止：立刻往上 propagate，不要被吞
                            raise
                        except Exception:
                            # 其他 callback 錯誤不影響爬蟲本身
                            pass
        finally:
            await context.close()
            await browser.close()
    return pages, warnings, site_signals
