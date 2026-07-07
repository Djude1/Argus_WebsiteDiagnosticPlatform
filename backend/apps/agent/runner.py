"""把 HermesAgent 跑成 async function，給 Celery task 在掃描流程中呼叫。

入場策略：
- 從本次掃描已成功爬到（blocked_reason 空）的 Page 中挑第一個作為起點。
- 沒有可用 Page → 直接 return None，不視為失敗。
- ARGUS_AGENT_ENABLED=False（預設）時 return None，向下相容既有掃描流程。

安全：
- 強制 same-origin 啟動：只在 scan_job.origin 域內導覽，由 Playwright + Agent
  tool 自身的 URL/selector 操作隱含約束（agent 沒有 navigate(url) tool）。
- 沿用專案 User-Agent（SiteSense-AI-Scanner）。
- Playwright Chromium 路徑由 settings 已注入環境變數的 PLAYWRIGHT_BROWSERS_PATH 決定。
"""

from __future__ import annotations

from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from playwright.async_api import async_playwright

from apps.scans.models import ScanJob

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

# 僅在 deep_mode（active + authorized）附加：授權 agent 對同源帶參數端點做 SQLi 主動驗證。
SECURITY_PROBE_ADDENDUM = """

【已授權的主動資安驗證】本次為授權的主動測試。若你在頁面上發現帶 query 參數的端點
（例如搜尋框送出後的 ?q=、商品查詢 ?id= 等），且你合理懷疑後端可能未妥善處理輸入，
可呼叫 probe_sql_injection(url) 對「該同源、帶參數的 URL」發動一次 SQL injection 主動驗證。
系統會自動判定並在確認可注入時記錄為 critical 漏洞（你無需再 report_ux_issue）。
僅對本站同源 URL 使用；跨站或無參數 URL 會被系統拒絕。"""


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

    prompt = task_prompt or DEFAULT_TASK_PROMPT_TEMPLATE.format(
        origin=scan_job.origin, url=target_url
    )
    # 僅在授權的主動掃描（deep_mode）才把 SQLi 主動驗證能力交給 agent；
    # 授權鎖最終仍由 kali_tools.run_sqlmap 的三重鎖把關，此處只影響提示。
    deep_mode = (
        scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
        and scan_job.active_testing_authorized
    )
    if deep_mode and task_prompt is None:
        prompt += SECURITY_PROBE_ADDENDUM

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=settings.ARGUS_SCANNER_USER_AGENT,
                ignore_https_errors=True,
            )
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
