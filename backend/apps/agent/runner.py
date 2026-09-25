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

import asyncio
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
from .tools import ToolExecutor, build_tool_schemas

DEFAULT_TASK_PROMPT_TEMPLATE = """你正在測試 {origin} 這個網站，已開啟頁面 {url}。
請執行以下測試：
1. 先呼叫 get_dom_summary 取得頁面互動元素摘要。
2. 找出最重要的呼叫行動按鈕（如「立即購買」、「免費試用」、「註冊」），嘗試點擊。
3. 若進入表單或結帳流程，請嘗試填入示意資料（test@example.com），並送出觀察結果。
4. 過程中任何 UX 問題（按鈕無反應、流程斷裂、文案歧義、看不到必要回饋），請呼叫 report_ux_issue。
5. 完成或無法繼續時呼叫 finish，並附短總結。

請不要操作他站資源、不要繞過驗證、不要送出破壞性 payload。"""

# 僅在 deep_mode（active + authorized）使用：雙 session 分工滲透（pentest-ai-agents
# 的 role 化概念）。單 session 塞全部工作會互相搶步數（#17~#22 實測：recon 的
# probe 序列與 auth 的登入後測試擠在同一 context，token 上限先爆），拆成
# 偵察／認證攻擊兩個角色，各自專屬提示詞與乾淨 context，序列執行後合併結果。
# 只描述「可用什麼工具觀察到什麼」，不給特定端點答案。
RECON_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（偵察角色），
已開啟頁面 {url}。
你只負責「未登入狀態」的偵察與驗證；不要註冊或登入帳號（那是另一位 agent 的工作）。

1. 呼叫 get_network_requests 取得本頁瀏覽器實際發出的 API 請求（XHR/fetch）；
   也可用 get_dom_summary 觀察互動元素。SPA 的後端 API 端點通常只出現在
   網路流量裡，不出現在頁面連結裡。
2. 從觀察到的端點中，自行判斷哪些「本站同源、且帶 query 參數（URL 含 ?xxx=）」
   最可能存在注入風險（例如接受使用者輸入的查詢、搜尋、篩選端點），對每一個
   呼叫 probe_sql_injection(url) 進行 SQL injection 主動驗證。系統會自動判定，
   確認可注入時記錄為 critical 漏洞（確認後你無需再 report）。
3. 對看起來「應該需要登入才能存取」的端點（個人資料、訂單、購物車、後台管理、
   內部 API 等），呼叫 probe_unauthorized_access(url) 以匿名請求重放：若匿名
   仍取得實質資料（非 401/403、非空回應），這就是未授權存取漏洞——用
   report_security_issue 回報，evidence 附上你觀察到的回應內容。
4. 過程中觀察到的其他資安線索（敏感資料顯示在頁面、錯誤訊息洩漏內部路徑、
   回應中的敏感欄位等）也用 report_security_issue 回報並附證據；不要臆測。
5. 完成、或已系統性覆蓋以上三類後，呼叫 finish 附短總結。

限制：只對本站同源 URL 使用 probe 工具；跨站 URL、無 query 參數的 SQLi
目標會被系統拒絕。"""

AUTH_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（認證攻擊角色），
已開啟頁面 {url}。
你負責「登入後」的存取控制與 business logic 驗證。

1. 若網站有註冊／登入功能：**優先直接打 API 而不是操作 UI 表單**——從
   network log 找到註冊與登入端點，用 replay_request 先 POST 註冊一個測試
   帳號（test 類信箱與隨機密碼），再 POST 登入並以 store_token_key 把回應
   token 存進瀏覽器。登入後再次 get_network_requests，觀察新出現的授權
   端點（購物車、訂單、個人資料等常帶數字 id）。
2. 跨帳號存取（IDOR）：把 URL 中的 id 改成鄰近數字或 1 重放——若 200 且回傳
   **不屬於此帳號**的資料，即為讀取型 IDOR。讀取型之外，更新類端點
   （PUT/PATCH，如修改購物車項目、個人資料）也以同法改 id 測試——若能成功
   修改**他人**的資源，這是更嚴重的寫入型 IDOR。兩種發現都立即
   report_security_issue，附上請求與回應證據。
3. Business logic：觀察到的數量／金額類欄位，送負值或極端值——若被接受
   （200 且資料寫入），這是 business logic 漏洞；寫入後重新 GET 該資源
   確認資料真的變了，連同驗證結果一起 report_security_issue。
4. 登入繞過：登入端點本身以 replay_request 送標準的 SQL injection 登入繞過
   探測值（如信箱欄填 ' OR 1=1-- 之類的無害查詢型 payload）——若回應異常
   成功（回傳 token／登入成功），即為登入繞過漏洞，report 時附請求與回應。
5. 完成、或已系統性覆蓋以上後呼叫 finish 附短總結。

注意：寫入型測試先用**你自己的**資源 id——登入回應或 whoami 類端點通常會
回傳你帳號的 id 與購物車／資源 id（例如 bid 欄位），用那個值，不要猜；
對「他人」的寫入測試只在更新端點（PUT/PATCH）上做，不要對他人資源做
建立或刪除。
限制：只對本站同源 URL 操作；不要操作他站資源。"""

INJECT_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（注入攻擊角色），
已開啟頁面 {url}。
你專責「輸入點注入」類驗證；不負責 IDOR／未授權存取（其他角色已涵蓋）。

1. **登入繞過（SQL injection in authentication）**：從 network log 找登入
   端點，用 replay_request 送標準的無害登入繞過 payload——常見型如
   信箱欄填 ' OR 1=1-- 、admin'-- ，密碼欄填任意值。若回應 200 且含
   token／authentication（對照：用亂填的假帳密登入會得到 401），即為
   登入繞過漏洞——report_security_issue 附上完整請求 body 與回應。
   多試幾種變形（' OR '1'='1 、" )) OR ((" 1 "=" 1 等）再下結論。
2. **XSS 反射／儲存探測**：對頁面上看得見的輸入框（搜尋、留言、評論、
   姓名欄等）以 type_text 輸入無害的 XSS 探測字串（如 <img src=x
   onerror=alert(1)> 或 <script>print(1)</script>），送出後用
   get_dom_summary／get_visible_text 檢查該字串是否以「未跳脫的 HTML」
   出現在頁面（例如元素屬性或 innerHTML 中出現完整標籤）——若原樣
   進入 DOM 屬性，即為反射／儲存型 XSS，report 附前後對照證據；
   若被跳脫成純文字顯示，屬正常防護，不要回報。
3. **其他輸入點異常**：CAPTCHA／OTP／驗證碼類端點——重放同一請求兩次，
   若舊碼可重用或回應可直接給出答案，即為設計缺陷；觀察回應中的錯誤
   訊息是否洩漏內部資訊（堆疊、SQL 片段、內部路徑），有就 report。
4. 完成或已系統性覆蓋後 finish 附短總結。

限制：payload 一律用無害查詢型（alert/print 級），不要嘗試刪除、修改
資料的 payload；只對本站同源操作。"""

LOGIC_ABUSE_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（商業邏輯濫用角色），
已開啟頁面 {url}。
你專責 business logic 類漏洞；不負責 IDOR／SQLi（其他角色已涵蓋）。

1. 先取得登入態：從 network log 找註冊／登入端點，replay_request 打 API
   註冊測試帳號並登入（store_token_key 存 token）；登入回應／whoami 類
   端點會給你自己的資源 id（例如 bid），後續寫入測試用它。
2. **數值邊界**：對數量／金額／折扣／庫存類欄位（加購物車、結帳、優惠券），
   以 replay_request 送負值、零、極大值、小數——被接受（200 且寫入）即為
   business logic 漏洞；**寫入後重新 GET 該資源確認資料真的變了**，
   連同驗證結果 report_security_issue。
3. **流程順序**：觀察到的多步驟流程（結帳、付款、密碼重設）——嘗試跳步
   重放（例如直接打結帳端點而未經過前置步驟），被接受即為流程繞過。
4. **重用性**：CAPTCHA／OTP／一次性 token 類端點——同一值重放兩次，
   第二次仍成功即為重用缺陷。
5. 完成或已系統性覆蓋後 finish 附短總結。

限制：只在**你自己的**資源上做寫入；payload 不具破壞性；只對本站同源操作。"""

# deep_mode 的 specialist 角色庫——orchestrator 依偵察情報動態挑選派工
# （pentest-ai-agents 的 swarm-orchestrator 概念：角色是工具箱，不是固定清單）
SPECIALIST_ROLES: dict[str, dict[str, str]] = {
    "auth_idor": {
        "prompt": AUTH_AGENT_PROMPT,
        "desc": "認證與越權：API 註冊登入、跨帳號讀取／寫入（IDOR，含 PUT/PATCH 更新端點）",
    },
    "injection": {
        "prompt": INJECT_AGENT_PROMPT,
        "desc": "輸入點注入：登入繞過 SQLi payload、XSS 反射／儲存探測、錯誤訊息洩漏",
    },
    "logic_abuse": {
        "prompt": LOGIC_ABUSE_AGENT_PROMPT,
        "desc": "商業邏輯：負數／極端值寫入、流程順序繞過、CAPTCHA/OTP 重用",
    },
}

ORCHESTRATOR_PROMPT = """你是滲透測試指揮官。先遣偵察 agent 已完成對目標 {origin} 的初步測試，
以下是它的情報。你的工作：決定派哪些專家角色進行第二波深入測試，
並給每位專家一句針對本次情況的任務提示（brief）——brief 可以引用你看到的
具體線索（可疑端點、未覆蓋的面相），讓專家不用從零探索。

【偵察總結】
{recon_summary}

【偵察已回報的發現】
{findings_list}

【掃描期間被動觀察到的同源 API 端點（部分）】
{endpoints}

【可用專家角色】
{roles_desc}

規則：依情報挑選真正需要的角色（可全部、可部分；無價值的角色不派）；
brief 一到三句、指向具體線索；不指定攻擊細節，讓專家自行判斷。
只回 JSON，格式：{{"dispatch": [{{"role": "角色名", "brief": "任務提示"}}]}}"""


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
    recon_intel: list[str] | None = None,
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

    async def _run_session(role_prompt: str) -> AgentRunResult:
        """單一 role session：獨立 browser context（乾淨 localStorage／cookie）
        與獨立 LLM messages——兩個 role 互不污染、各自完整預算上限。"""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                **playwright_launch_kwargs(),
            )
            try:
                context = await _make_agent_context(browser, scan_job.origin)
                page = await context.new_page()
                await page.goto(
                    target_url, wait_until="domcontentloaded", timeout=30000
                )
                executor = ToolExecutor(
                    page=page, screenshot_dir=str(media_dir), scan_job=scan_job
                )
                agent = HermesAgent(
                    scan_job=scan_job,
                    executor=executor,
                    chain=chain,
                    tool_schemas=build_tool_schemas(deep_mode),
                )
                return await agent.run(task_prompt=role_prompt)
            finally:
                await browser.close()

    def _merge(results: list[AgentRunResult]) -> AgentRunResult:
        """合併多 role 的結果：issues/findings 串聯（persist 層依 description
        去重）；status 只要有一個 completed 就算 completed；error 串聯標注角色。"""
        if len(results) == 1:
            return results[0]
        return AgentRunResult(
            session_id=results[0].session_id,
            status=(
                "completed"
                if any(r.status == "completed" for r in results)
                else results[0].status
            ),
            steps=sum(r.steps for r in results),
            total_tokens=sum(r.total_tokens for r in results),
            issues=[i for r in results for i in r.issues],
            security_findings=[f for r in results for f in r.security_findings],
            final_summary=" || ".join(
                f"[{idx}] {r.final_summary[:200]}" for idx, r in enumerate(results)
            ),
            error="; ".join(
                f"role{idx}:{r.error}" for idx, r in enumerate(results) if r.error
            ),
        )

    if task_prompt is not None:
        prompts: list[str] = [task_prompt]
    elif deep_mode:
        # 指揮官模式：recon 固定先跑 → orchestrator 依情報動態挑 specialist
        # → 各自乾淨 session 深入 → 合併。序列執行（RPS 與 Kali 預算全域共享）。
        recon_prompt = RECON_AGENT_PROMPT.format(
            origin=scan_job.origin, url=target_url
        )
        recon_result = await _run_session(recon_prompt)

        dispatch = await _orchestrate_dispatch(
            chain=chain,
            scan_job=scan_job,
            recon_result=recon_result,
            recon_intel=recon_intel or [],
        )
        specialist_prompts = []
        for item in dispatch:
            role_def = SPECIALIST_ROLES.get(item["role"])
            if role_def is None:
                continue
            prompt = role_def["prompt"].format(
                origin=scan_job.origin, url=target_url
            )
            brief = (item.get("brief") or "").strip()
            if brief:
                prompt += f"\n\n【指揮官任務提示】{brief}"
            specialist_prompts.append(prompt)
        if not specialist_prompts:  # orchestrator 失效時的安全網：全派
            specialist_prompts = [
                role["prompt"].format(origin=scan_job.origin, url=target_url)
                for role in SPECIALIST_ROLES.values()
            ]

        results = [recon_result] + [
            await _run_session(p) for p in specialist_prompts
        ]
        result = _merge(results)

        if result and result.issues:
            await sync_to_async(persist_agent_issues)(scan_job, result.issues)
        if result and result.security_findings:
            await sync_to_async(persist_agent_security_findings)(
                scan_job, result.security_findings
            )
        return result
    else:
        prompts = [
            DEFAULT_TASK_PROMPT_TEMPLATE.format(
                origin=scan_job.origin, url=target_url
            )
        ]

    results = [await _run_session(p) for p in prompts]
    result = _merge(results)

    if result and result.issues:
        await sync_to_async(persist_agent_issues)(scan_job, result.issues)
    if result and result.security_findings:
        await sync_to_async(persist_agent_security_findings)(
            scan_job, result.security_findings
        )
    return result


async def _orchestrate_dispatch(
    *,
    chain: ProviderChain,
    scan_job: ScanJob,
    recon_result: AgentRunResult,
    recon_intel: list[str],
) -> list[dict[str, str]]:
    """指揮官決策：recon 情報 → 挑 specialist＋各別 brief。

    單輪結構化生成（chain.chat_text）；JSON 解析失敗回空清單，呼叫端
    有全派的安全網。情報全部來自本次掃描的觀察，黑箱合規。
    """

    def _decide() -> list[dict[str, str]]:
        findings_titles = [
            f.title
            for f in scan_job.findings.filter(
                rule_id__in=("agent-observed-security", "kali-sqlmap-sqli")
            )[:20]
        ]
        prompt = ORCHESTRATOR_PROMPT.format(
            origin=scan_job.origin,
            recon_summary=(recon_result.final_summary or "（無）")[:1500],
            findings_list=("\n".join(f"- {t}" for t in findings_titles) or "（無）"),
            endpoints=("\n".join(f"- {u}" for u in recon_intel[:15]) or "（無）"),
            roles_desc="\n".join(
                f"- {name}: {defn['desc']}" for name, defn in SPECIALIST_ROLES.items()
            ),
        )
        response = chain.chat_text(prompt=prompt, temperature=0.1, max_tokens=1200)
        import json as _json

        try:
            data = _json.loads(
                (response.content or "").strip().removeprefix("```json").removesuffix("```")
            )
        except (ValueError, AttributeError):
            return []
        dispatch = data.get("dispatch") if isinstance(data, dict) else None
        if not isinstance(dispatch, list):
            return []
        return [
            {"role": str(d.get("role", "")), "brief": str(d.get("brief", ""))}
            for d in dispatch
            if isinstance(d, dict) and d.get("role") in SPECIALIST_ROLES
        ]

    try:
        return await asyncio.to_thread(_decide)
    except Exception:  # noqa: BLE001 — orchestrator 失敗交由安全網全派
        return []


def _pick_starting_page(scan_job: ScanJob):
    return (
        scan_job.pages.filter(blocked_reason="")
        .exclude(final_url="")
        .order_by("depth", "id")
        .first()
    )
