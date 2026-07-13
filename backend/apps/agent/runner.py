"""把 HermesAgent 跑成 async function，給 Celery task 在掃描流程中呼叫。

入場策略：
- 從本次掃描已成功爬到（blocked_reason 空）的 Page 中挑第一個作為起點。
- 沒有可用 Page → 直接 return None，不視為失敗。
- ARGUS_AGENT_ENABLED=False（預設）時 return None，向下相容既有掃描流程。

安全：
- 所有請求先套用 public target policy，主文件與 WebSocket 再強制 same-origin；
  Service Worker 停用，避免繞過 Playwright request interception。
- 沿用專案 User-Agent（SiteSense-AI-Scanner）。
- Playwright Chromium 路徑由 settings 已注入環境變數的 PLAYWRIGHT_BROWSERS_PATH 決定。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from asgiref.sync import sync_to_async
from config.egress import playwright_launch_kwargs
from django.conf import settings
from playwright.async_api import async_playwright

from apps.scans.models import ScanJob
from apps.scans.services import (
    PublicScanTargetError,
    assert_public_http_url,
    assert_public_websocket_url,
)

from .findings import persist_agent_issues, persist_agent_security_findings
from .loop import AgentRunResult, HermesAgent
from .providers import ProviderChain, build_default_chain
from .tools import ToolExecutor

DEFAULT_TASK_PROMPT_TEMPLATE = """你正在測試 {origin} 這個網站，已開啟頁面 {url}。
請執行以下測試：
1. 先呼叫 get_dom_summary 取得頁面互動元素摘要。
2. 找出最重要的呼叫行動按鈕（如「立即購買」、「免費試用」、「註冊」），嘗試點擊。
3. 若進入表單或結帳流程，請嘗試填入示意資料（test@example.com），並送出觀察結果。
4. 過程中任何 UX 問題（按鈕無反應、流程斷裂、文案歧義、看不到必要回饋），請呼叫 report_ux_issue。
5. 完成或無法繼續時呼叫 finish，並附短總結。

請不要操作他站資源、不要繞過驗證、不要送出破壞性 payload。"""

# 僅在 deep_mode（active + authorized）使用：資安優先的任務指示，讓 agent 先做 SQLi 主動驗證。
# 置於任務最前面（第一優先），避免 agent 把 token 預算耗在 UX 探索上而沒機會 probe。
SECURITY_FIRST_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】，已開啟頁面 {url}。

請**最優先**完成以下資安驗證步驟（在任何 UX 測試之前）：
1. 呼叫 get_dom_summary，找出頁面上所有帶 query 參數（URL 含 ?xxx=）的連結或端點
   （特別留意搜尋、商品查詢類，如 /api/products/search?q=、?id= 等）。
2. 對每一個「本站同源、且帶參數」的可疑端點，呼叫 probe_sql_injection(url) 進行
   SQL injection 主動驗證。系統會自動判定並在確認可注入時記錄為 critical 漏洞
   （確認後你無需再 report_ux_issue）。
3. 完成資安驗證後，若還有 token 額度，再簡單做基本 UX 觀察並 report_ux_issue。
4. 全部完成或無法繼續時呼叫 finish 並附短總結。

限制：只對本站同源 URL 使用 probe_sql_injection；跨站或無參數 URL 會被系統拒絕。
不要繞過驗證、不要操作他站資源。"""


def _origin_key(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, (parsed.hostname or "").lower(), parsed.port or default_port


async def _enforce_agent_request(route, request, origin: str):
    try:
        normalized = assert_public_http_url(request.url)
        if request.resource_type == "document" and _origin_key(normalized) != _origin_key(origin):
            raise PublicScanTargetError("Agent 主文件禁止跨 origin 導覽")
    except PublicScanTargetError:
        await route.abort("blockedbyclient")
        return
    await route.continue_()


async def _enforce_agent_websocket(websocket_route, origin: str):
    try:
        normalized = assert_public_websocket_url(websocket_route.url)
        if _origin_key(normalized) != _origin_key(origin):
            raise PublicScanTargetError("Agent WebSocket 禁止跨 origin")
    except PublicScanTargetError:
        await websocket_route.close(code=1008, reason="Blocked by scan target policy")
        return
    websocket_route.connect_to_server()


async def _make_agent_context(browser, origin: str):
    context = await browser.new_context(
        user_agent=settings.ARGUS_SCANNER_USER_AGENT,
        ignore_https_errors=True,
        service_workers="block",
    )
    await context.route(
        "**/*",
        lambda route, request: _enforce_agent_request(route, request, origin),
    )
    await context.route_web_socket(
        "**/*",
        lambda websocket_route: _enforce_agent_websocket(websocket_route, origin),
    )
    return context


async def run_agent_for_scan(
    scan_job: ScanJob,
    chain: ProviderChain | None = None,
    task_prompt: str | None = None,
) -> AgentRunResult | None:
    """對已完成爬取的 ScanJob 啟動 Hermes-Agent 動態 UX 測試。

    回傳 AgentRunResult，或 None 表示未啟動（功能關閉或無可用 Page）。
    """
    if not settings.ARGUS_AGENT_ENABLED:
        return None

    page_obj = await sync_to_async(_pick_starting_page)(scan_job)
    if page_obj is None:
        return None

    target_url = page_obj.final_url or page_obj.url
    chain = chain or build_default_chain()

    media_dir = Path(settings.MEDIA_ROOT) / "agent" / f"scan_{scan_job.id}"
    media_dir.mkdir(parents=True, exist_ok=True)

    # 僅在授權的主動掃描（deep_mode）才把 SQLi 主動驗證能力交給 agent 並列為第一優先；
    # 授權鎖最終仍由 kali_tools.run_sqlmap 的三重鎖把關，此處只影響提示。
    deep_mode = (
        scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
        and scan_job.active_testing_authorized
    )
    if task_prompt is not None:
        prompt = task_prompt
    elif deep_mode:
        prompt = SECURITY_FIRST_PROMPT.format(origin=scan_job.origin, url=target_url)
    else:
        prompt = DEFAULT_TASK_PROMPT_TEMPLATE.format(
            origin=scan_job.origin, url=target_url
        )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            **playwright_launch_kwargs(),
        )
        try:
            context = await _make_agent_context(browser, scan_job.origin)
            page = await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

            executor = ToolExecutor(
                page=page, screenshot_dir=str(media_dir), scan_job=scan_job
            )
            agent = HermesAgent(scan_job=scan_job, executor=executor, chain=chain)
            result = await agent.run(task_prompt=prompt)
        finally:
            await browser.close()

    if result and result.issues:
        await sync_to_async(persist_agent_issues)(scan_job, result.issues)
    if result and result.security_findings:
        await sync_to_async(persist_agent_security_findings)(
            scan_job, result.security_findings
        )
    return result


def _pick_starting_page(scan_job: ScanJob):
    return (
        scan_job.pages.filter(blocked_reason="")
        .exclude(final_url="")
        .order_by("depth", "id")
        .first()
    )
