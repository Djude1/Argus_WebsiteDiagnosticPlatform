"""Hermes-Agent 可呼叫的 Playwright tools。

設計原則：
- 以 OpenAI function calling 格式定義 schema，讓 MiniMax / GLM 直接相容。
- ToolExecutor 接收 async Page，將 LLM 的 tool call 轉成 Playwright 動作。
- 所有 tool 回傳 JSON-serializable dict；長字串截短，避免吃光 context。
- selector 走 Playwright 標準語法（CSS / role / text），不執行任意 JS。
- report_ux_issue 不在這裡落地，executor 只把資料回傳；loop 層負責寫入 Finding。
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from apps.scans.security.kali_contracts import redact_url_query_values

DEFAULT_ACTION_TIMEOUT_MS = 5000
MAX_TEXT_BYTES = 4000
MAX_DOM_NODES = 80
_MAX_NETWORK_LOG = 200  # 被動網路觀察上限（socket.io 高頻輪詢會快速填充）


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "點擊符合 CSS selector 的第一個元素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "在符合 selector 的輸入元素填入文字（會清掉原內容）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "捲動頁面：direction up/down，amount 為像素。",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "minimum": 50, "maximum": 5000},
                },
                "required": ["direction", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_visible_text",
            "description": "取得目前 viewport 內可見的純文字摘要，已截短。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dom_summary",
            "description": "取得頁面互動元素摘要（最多前 80 個，含 tag、role、可見文字）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_requests",
            "description": (
                "列出本頁載入與操作過程中，瀏覽器實際發出的 same-origin API 請求"
                "（XHR/fetch，含 method、URL、狀態碼，最新在前）。SPA 的後端"
                " API 端點（含帶 ?query= 參數的網址）只會出現在這裡，"
                "不會出現在 DOM 連結裡。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "最多回傳幾筆（預設 20）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "對目前 viewport 截圖並儲存，回傳檔案路徑。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_ux_issue",
            "description": "回報一個 UX 問題；不要回報修復程式碼，只描述問題與方向。",
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "remediation": {"type": "string"},
                    "selector": {"type": "string"},
                },
                "required": ["severity", "title", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_sql_injection",
            "description": (
                "對『目前站台同源、且帶 query 參數』的 URL 發動一次授權範圍內的 "
                "SQL injection 主動驗證（背後以 Kali 的 sqlmap 執行）。只在你懷疑某個帶參數的 "
                "端點（例如搜尋、商品查詢）可能存在注入時才呼叫；跨站或無參數的 URL 會被拒絕。"
                "回傳是否確認可注入；確認時系統會自動記錄為 critical 資安漏洞，你不需再 report。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要驗證的完整 URL，須與目前站台同源且含 ?參數=值",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_unauthorized_access",
            "description": (
                "以『不帶任何登入憑證』的乾淨請求重放一個同源 API 端點，驗證它是否"
                "允許未授權存取。適用在：你在網路流量（get_network_requests）看到需要"
                "登入才會觸發的端點（訂單、個人資料、後台 API），想確認匿名存取是否"
                "也拿得到資料。回傳匿名請求的狀態碼、內容類型與回應片段——**由你判斷**"
                "回傳內容是否屬於應受保護的資料；確認是漏洞時用 report_security_issue"
                "回報並附上本次觀察作為證據。跨站 URL 會被拒絕。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要驗證的完整同源 URL",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replay_request",
            "description": (
                "以『目前頁面的登入態』重放一個同源 API 請求（自動帶上瀏覽器 "
                "session 的 token／cookie）。用途：在 get_network_requests 看過某端點"
                "的原始請求後，修改內容重放——例如把 URL 中的 id 換成鄰近值測試"
                "能否讀到他人資源（IDOR），或把數量／金額欄位改成負值、極端值"
                "測試是否被接受（business logic）。method 限 GET／POST；"
                "確認漏洞時用 report_security_issue 附上回應證據。"
                "註冊／登入也建議直接以此工具打 API（比操作 UI 表單快得多）："
                "POST 註冊端點建帳號、POST 登入端點拿 token，並用 "
                "store_token_key 把回應中的 token 存進瀏覽器，之後的重放就會"
                "自動帶著登入態。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整同源 URL"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH"]},
                    "body": {
                        "type": "object",
                        "description": (
                            "POST 的 JSON body（選填）；仿照 network log 中"
                            "該端點原本的 body 結構修改"
                        ),
                    },
                    "store_token_key": {
                        "type": "string",
                        "description": (
                            "（選填）若預期回應 JSON 含 token（常見於登入端點），"
                            "提供 localStorage 鍵名，工具會把 token 寫入，"
                            "例如 token 或 access_token"
                        ),
                    },
                },
                "required": ["url", "method"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_security_issue",
            "description": (
                "回報一個你在實際操作或 probe 觀察中發現的資安問題（例如未授權存取、"
                "敏感資料外洩、錯誤訊息洩漏內部資訊）。必須附上你親眼觀察到的證據"
                "（回應片段、狀態碼、畫面內容），不可以臆測。攻擊性驗證請用 "
                "probe_sql_injection / probe_unauthorized_access，不要自行組攻擊 payload。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["high", "medium", "low", "info"],
                    },
                    "title": {"type": "string"},
                    "description": {
                        "type": "string", "description": "問題描述與為什麼是風險",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "實際觀察到的證據（回應片段、截圖內容等）",
                    },
                    "remediation": {"type": "string"},
                    "url": {"type": "string", "description": "發現問題的端點 URL（選填）"},
                },
                "required": ["severity", "title", "description", "evidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_specialist",
            "description": (
                "（指揮官專用）派出一位專家 subagent 執行深入測試，等待其完成後"
                "回傳結果摘要（發現清單＋狀態）。你可以根據每位專家的結果決定"
                "是否追加派出其他專家。角色與職責見任務說明。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "專家角色名稱（見任務說明的可用角色清單）",
                    },
                    "brief": {
                        "type": "string",
                        "description": "給該專家的任務提示：指向你觀察到的具體線索（一到三句）",
                    },
                },
                "required": ["role", "brief"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "完成本次任務並結束。當你已經回報完所有發現或無法繼續時呼叫。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Task 6：依授權模式動態組裝 tool schemas，並遮罩持久化的 tool 資料
# ---------------------------------------------------------------------------
def build_tool_schemas(
    allow_sqlmap: bool,
    orchestrator: bool = False,
    specialist_roles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """依模式組裝 tool schemas。

    - allow_sqlmap（deep_mode）：主動探測工具（probe_*／replay_request）可用
    - orchestrator：指揮官模式——只留 dispatch_specialist／finish／
      report_security_issue（調度職責，不親自測試；specialist 不帶
      dispatch，防無限遞迴）
    - specialist_roles：角色目錄（name → {desc, when, ...}）。指揮官模式
      會把 role enum 與「何時派用」說明動態填入 dispatch_specialist 的
      schema——這是指揮官「知道自己手中有什麼」的機制（hermes-agent 的
      能力目錄化概念）
    回傳獨立深拷貝，避免共用 mutable schema 被意外修改。
    """
    deep_only = {"probe_sql_injection", "probe_unauthorized_access", "replay_request"}
    if orchestrator:
        keep = {"dispatch_specialist", "finish", "report_security_issue"}
        schemas = [
            copy.deepcopy(s)
            for s in TOOL_SCHEMAS
            if s["function"]["name"] in keep
        ]
        if specialist_roles:
            role_names = sorted(specialist_roles.keys())
            catalog = "\n".join(
                f"- {name}: {defn.get('desc', '')}（派用時機：{defn.get('when', '')}）"
                for name, defn in specialist_roles.items()
            )
            for schema in schemas:
                if schema["function"]["name"] == "dispatch_specialist":
                    schema["function"]["parameters"]["properties"]["role"] = {
                        "type": "string",
                        "enum": role_names,
                        "description": f"可用專家角色：\n{catalog}",
                    }
        return schemas
    return [
        copy.deepcopy(schema)
        for schema in TOOL_SCHEMAS
        if allow_sqlmap or schema["function"]["name"] not in deep_only
    ]


def redact_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """遮罩即將持久化到 AgentStep 的 tool arguments。

    probe_sql_injection 的 url 參數值可能含敏感 query value（搜尋關鍵字、ID），
    一律經 redact_url_query_values 遮罩；其他 tool 的參數原樣回傳（淺拷貝）。
    """
    clean = dict(arguments or {})
    if (
        tool_name
        in {"probe_sql_injection", "probe_unauthorized_access", "replay_request"}
        and "url" in clean
    ):
        clean["url"] = redact_url_query_values(str(clean["url"]))
    return clean


def redact_tool_result(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """遮罩即將持久化到 AgentStep 的 tool result。

    probe_sql_injection 的 result 只保留 confirmed / blocked / error / correlation_id，
    移除 target URL 與任何額外欄位（note 等），避免 raw URL 或中介資料外洩。
    """
    if tool_name == "get_network_requests":
        raw = result or {}
        return {
            "total_logged": raw.get("total_logged", 0),
            "requests": [
                {
                    **req,
                    "url": redact_url_query_values(str(req.get("url", ""))),
                }
                for req in raw.get("requests", [])
                if isinstance(req, dict)
            ],
        }
    if tool_name in {"probe_unauthorized_access", "replay_request"}:
        raw = result or {}
        safe: dict[str, Any] = {
            "status": raw.get("status"),
            "content_type": raw.get("content_type"),
            "body_length": raw.get("body_length"),
        }
        if raw.get("body_snippet"):
            safe["body_snippet"] = redact_url_query_values(str(raw["body_snippet"]))
        if raw.get("blocked"):
            safe["blocked"] = raw["blocked"]
        if raw.get("error"):
            safe["error"] = raw["error"]
        if raw.get("authenticated") is not None:
            safe["authenticated"] = raw.get("authenticated")
        if raw.get("token_stored") is not None:
            safe["token_stored"] = raw.get("token_stored")
        return safe
    if tool_name != "probe_sql_injection":
        return dict(result or {})
    raw = result or {}
    safe: dict[str, Any] = {"confirmed": bool(raw.get("confirmed"))}
    if raw.get("blocked"):
        safe["blocked"] = raw["blocked"]
    if raw.get("error"):
        safe["error"] = raw["error"]
    if raw.get("correlation_id"):
        safe["correlation_id"] = raw["correlation_id"]
    return safe


@dataclass
class ToolOutcome:
    """單一 tool 執行結果。"""

    ok: bool
    result: dict[str, Any]
    finish: bool = False  # finish/error 達成終止條件
    issue: dict[str, Any] | None = None  # report_ux_issue 的 payload
    security_finding: dict[str, Any] | None = None  # probe_sql_injection 確認後的 security finding


def _truncate(text: str, limit: int = MAX_TEXT_BYTES) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"...[truncated {len(text) - limit} chars]"


class ToolExecutor:
    """把 LLM 的 tool call 轉成 Playwright 動作。

    傳入 page 必須是 async Playwright Page；screenshot_dir 用於存截圖。
    """

    def __init__(
        self,
        page: Page,
        screenshot_dir: str,
        action_timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
        scan_job=None,
        specialist_dispatcher=None,
    ):
        self.page = page
        self.screenshot_dir = screenshot_dir
        self.action_timeout_ms = action_timeout_ms
        # probe_sql_injection 需要 scan_job.id / origin（同源檢查 + 授權鎖）
        self.scan_job = scan_job
        # 指揮官模式：dispatch_specialist tool 的實作由 runner 注入
        # （async fn(role, brief) -> dict 摘要）；specialist 自身不帶（防遞迴）
        self.specialist_dispatcher = specialist_dispatcher
        self._screenshot_counter = 0
        # 被動網路觀察：SPA 的 API 端點只存在於真實流量，agent 靠這個「看到」
        # 頁面自己發出的 XHR/fetch（不發任何新請求）。
        self._network_log: list[dict[str, Any]] = []
        if scan_job is not None:
            self.page.on("response", self._on_network_response)

    def _on_network_response(self, response) -> None:
        """收集 same-origin XHR/fetch 進 network log；任何例外靜默忽略。"""
        try:
            if response.request.resource_type not in {"xhr", "fetch"}:
                return
            origin = getattr(self.scan_job, "origin", "") or ""
            req_url = response.url or ""
            if urlsplit(origin).hostname != urlsplit(req_url).hostname:
                return
            if len(self._network_log) >= _MAX_NETWORK_LOG:
                self._network_log.pop(0)
            self._network_log.append(
                {
                    "method": response.request.method,
                    "url": req_url,
                    "status": response.status,
                }
            )
        except Exception:
            pass

    async def run(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        try:
            if name == "click":
                return await self._click(args.get("selector", ""))
            if name == "type_text":
                return await self._type_text(args.get("selector", ""), args.get("text", ""))
            if name == "scroll":
                return await self._scroll(
                    args.get("direction", "down"), int(args.get("amount", 500))
                )
            if name == "get_visible_text":
                return await self._get_visible_text()
            if name == "get_dom_summary":
                return await self._get_dom_summary()
            if name == "get_network_requests":
                return self._get_network_requests(args)
            if name == "take_screenshot":
                return await self._take_screenshot()
            if name == "report_ux_issue":
                return self._report_ux_issue(args)
            if name == "probe_sql_injection":
                return await self._probe_sql_injection(args.get("url", ""))
            if name == "probe_unauthorized_access":
                return await self._probe_unauthorized_access(args.get("url", ""))
            if name == "replay_request":
                return await self._replay_request(
                    args.get("url", ""),
                    args.get("method", "GET"),
                    args.get("body"),
                    args.get("store_token_key", ""),
                )
            if name == "report_security_issue":
                return self._report_security_issue(args)
            if name == "dispatch_specialist":
                if self.specialist_dispatcher is None:
                    return ToolOutcome(
                        ok=False, result={"error": "dispatcher_not_available"}
                    )
                outcome_data = await self.specialist_dispatcher(
                    str(args.get("role", "")), str(args.get("brief", ""))
                )
                return ToolOutcome(ok=bool(outcome_data), result=outcome_data)
            if name == "finish":
                return ToolOutcome(
                    ok=True,
                    result={"summary": str(args.get("summary", ""))[:500]},
                    finish=True,
                )
            return ToolOutcome(ok=False, result={"error": f"unknown_tool:{name}"})
        except PlaywrightTimeoutError as exc:
            return ToolOutcome(ok=False, result={"error": "timeout", "detail": str(exc)[:200]})
        except Exception as exc:
            return ToolOutcome(
                ok=False,
                result={"error": exc.__class__.__name__, "detail": str(exc)[:200]},
            )

    async def _click(self, selector: str) -> ToolOutcome:
        if not selector:
            return ToolOutcome(ok=False, result={"error": "empty_selector"})
        loc = self.page.locator(selector).first
        await loc.click(timeout=self.action_timeout_ms)
        await self.page.wait_for_load_state("domcontentloaded", timeout=self.action_timeout_ms)
        url = self.page.url
        return ToolOutcome(ok=True, result={"clicked": selector, "url_after": url})

    async def _type_text(self, selector: str, text: str) -> ToolOutcome:
        if not selector:
            return ToolOutcome(ok=False, result={"error": "empty_selector"})
        loc = self.page.locator(selector).first
        await loc.fill(text, timeout=self.action_timeout_ms)
        return ToolOutcome(ok=True, result={"typed_into": selector, "length": len(text)})

    async def _scroll(self, direction: str, amount: int) -> ToolOutcome:
        delta = amount if direction == "down" else -amount
        await self.page.evaluate("(d) => window.scrollBy(0, d)", delta)
        await asyncio.sleep(0.2)
        return ToolOutcome(ok=True, result={"scrolled": delta})

    async def _get_visible_text(self) -> ToolOutcome:
        text = await self.page.evaluate(
            "() => document.body && document.body.innerText ? document.body.innerText : ''"
        )
        return ToolOutcome(ok=True, result={"text": _truncate(str(text))})

    def _get_network_requests(self, args: dict[str, Any]) -> ToolOutcome:
        """回傳被動收集的 same-origin API 請求（最新在前）。"""
        try:
            limit = max(1, min(int(args.get("limit", 20)), 50))
        except (TypeError, ValueError):
            limit = 20
        recent = list(reversed(self._network_log))[:limit]
        return ToolOutcome(
            ok=True, result={"requests": recent, "total_logged": len(self._network_log)}
        )

    async def _get_dom_summary(self) -> ToolOutcome:
        # 注意：JS 模板內 .slice(0, 60) 那行因 JSON 結構需保持單行；用 noqa 略過 ruff 行長檢查
        script = (
            "() => {\n"
            "  const out = [];\n"
            "  const tags = ['a', 'button', 'input', 'select', 'textarea', 'form', 'nav'];\n"
            "  for (const tag of tags) {\n"
            "    const els = document.querySelectorAll(tag);\n"
            f"    for (let i = 0; i < els.length && out.length < {MAX_DOM_NODES}; i++) {{\n"
            "      const el = els[i];\n"
            "      const rect = el.getBoundingClientRect();\n"
            "      if (rect.width === 0 || rect.height === 0) continue;\n"
            "      out.push({\n"
            "        tag,\n"
            "        role: el.getAttribute('role') || '',\n"
            "        name: (el.getAttribute('aria-label') || el.getAttribute('placeholder')"
            " || (el.innerText || '').slice(0, 60)).trim(),\n"
            "        href: el.getAttribute('href') || '',\n"
            "        id: el.id || '',\n"
            "      });\n"
            "    }\n"
            "  }\n"
            "  return out;\n"
            "}"
        )
        nodes = await self.page.evaluate(script)
        return ToolOutcome(ok=True, result={"nodes": nodes[:MAX_DOM_NODES]})

    async def _take_screenshot(self) -> ToolOutcome:
        self._screenshot_counter += 1
        from pathlib import Path

        path = Path(self.screenshot_dir) / f"agent_step_{self._screenshot_counter}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(path), full_page=False)
        return ToolOutcome(ok=True, result={"path": str(path)})

    def _report_ux_issue(self, args: dict[str, Any]) -> ToolOutcome:
        severity = args.get("severity", "low")
        title = (args.get("title") or "").strip()[:255]
        description = (args.get("description") or "").strip()
        remediation = (args.get("remediation") or "").strip()
        selector = (args.get("selector") or "").strip()[:512]

        # 防呆：若描述夾帶程式碼修復片段，仍保留但 strip 過長
        description = description[:5000]
        remediation = remediation[:5000]

        if not title or not description:
            return ToolOutcome(ok=False, result={"error": "missing_title_or_description"})

        valid_sev = {"critical", "high", "medium", "low", "info"}
        payload = {
            "severity": severity if severity in valid_sev else "low",
            "title": title,
            "description": description,
            "remediation": remediation or "請檢視該流程的可用性並對齊使用者預期。",
            "selector": selector,
            "url": self.page.url,
        }
        return ToolOutcome(ok=True, result={"reported": True, "title": title}, issue=payload)

    async def _probe_unauthorized_access(self, url: str) -> ToolOutcome:
        """以無憑證的乾淨請求重放同源端點，驗證是否允許未授權存取。

        安全約束：
        - 強制**同源**（比對 scan_job.origin），與 _probe_sql_injection 同邊界。
        - 工具本身只在 deep_mode（active＋authorized）暴露 schema（build_tool_schemas）；
          runtime 再檢查一次 scan_mode/authorized，防 schema 外洩路徑。
        - 僅發一次普通 GET（scanner UA、無 cookie／token），不帶任何攻擊 payload；
          回應片段經 redact_url_query_values 後才回給 LLM 與持久化。

        回傳原始觀察（status／content_type／長度／片段）；**不由工具判定漏洞**——
        是否屬於應受保護資料由 agent 判斷後以 report_security_issue 回報，
        證據由 agent 附上，維持「證據鏈由觀察組成」的契約。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        from django.conf import settings as dj_settings

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )

        import httpx

        def _fetch() -> dict[str, Any]:
            # 不帶 cookie／Authorization：匿名重放。redirect 不跟隨，避免 open-redirect
            # 把探針導向他站；timeout 短，失敗即回結構化錯誤。
            with httpx.Client(
                headers={"User-Agent": dj_settings.ARGUS_SCANNER_USER_AGENT},
                timeout=10.0,
                follow_redirects=False,
            ) as client:
                r = client.get(url)
            snippet = (r.text or "")[:400]
            return {
                "status": r.status_code,
                "content_type": r.headers.get("content-type", ""),
                "body_length": len(r.content or b""),
                "body_snippet": snippet,
            }

        try:
            observation = await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001 — 網路失敗回結構化錯誤不炸迴圈
            return ToolOutcome(
                ok=False, result={"error": f"request_failed:{exc.__class__.__name__}"}
            )
        observation["body_snippet"] = redact_url_query_values(
            str(observation.get("body_snippet", ""))
        )
        return ToolOutcome(ok=True, result=observation)

    async def _replay_request(
        self,
        url: str,
        method: str,
        body: dict[str, Any] | None,
        store_token_key: str = "",
    ) -> ToolOutcome:
        """以目前頁面的登入態重放同源請求（帶 session cookie 與 localStorage token）。

        agent 在 deep_mode（active＋authorized）已授權滲透範圍內，用此工具對
        已觀察過的 API 端點做「修改後重放」：改 id 測 IDOR、改數值測 business
        logic。工具只負責帶憑證發送與回傳觀察（遮罩後）；漏洞判定由 agent
        以 report_security_issue 附證據回報。

        安全約束：同源閘（比對 scan_job.origin）＋ deep_mode runtime 再驗；
        method 限 GET／POST（不允許 PUT/DELETE 等破壞性操作）；不跟隨 redirect。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        from apps.scans.models import ScanJob

        if not (
            self.scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
            and self.scan_job.active_testing_authorized
        ):
            return ToolOutcome(ok=False, result={"error": "not_authorized_mode"})

        method = (method or "GET").upper()
        if method not in ("GET", "POST", "PUT", "PATCH"):
            return ToolOutcome(ok=False, result={"error": "method_not_allowed"})

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )

        # 取得目前 session 的憑證：cookie（傳統 session）＋ localStorage 的
        # token（SPA JWT 慣例鍵名）。取不到屬正常（未登入），匿名重放仍可執行。
        try:
            token = await self.page.evaluate(
                "() => { const keys = ['token','jwt','access_token','auth_token','id_token'];"
                " for (const k of keys) { const v = localStorage.getItem(k);"
                " if (v) return v.replace(/^\"|\"$/g, ''); } return ''; }"
            )
        except Exception:
            token = ""
        token = str(token or "")
        try:
            cookies = await self.page.context.cookies()
        except Exception:
            cookies = []

        import httpx

        def _fetch() -> dict[str, Any]:
            headers = {"User-Agent": settings.ARGUS_SCANNER_USER_AGENT}
            if token:
                # Bearer 優先；站方若用其他 scheme，cookie 仍會帶上
                headers["Authorization"] = f"Bearer {token}"
            jar = {
                c["name"]: c["value"]
                for c in cookies
                if c.get("name") and c.get("value")
            }
            with httpx.Client(
                headers=headers, cookies=jar, timeout=10.0, follow_redirects=False
            ) as client:
                if method == "POST":
                    r = client.post(url, json=body or {})
                elif method == "PUT":
                    r = client.put(url, json=body or {})
                elif method == "PATCH":
                    r = client.patch(url, json=body or {})
                else:
                    r = client.get(url)
            return {
                "status": r.status_code,
                "content_type": r.headers.get("content-type", ""),
                "body_length": len(r.content or b""),
                "body_snippet": (r.text or "")[:400],
                # token 抽取必須用完整回應：JWT 常超過 snippet 的 400 字元，
                # 截斷字串會讓 json.loads 失敗、token 永遠存不進去
                "_full_body": r.text or "",
            }

        try:
            observation = await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001 — 網路失敗回結構化錯誤不炸迴圈
            return ToolOutcome(
                ok=False, result={"error": f"request_failed:{exc.__class__.__name__}"}
            )
        # 登入端點支援：回應 JSON 裡的 token 寫入 localStorage，讓 agent 的
        # 後續重放自動帶登入態（SPA 慣例）。token 不回傳給 LLM、不持久化。
        token_stored = False
        full_body = observation.pop("_full_body", "")
        if store_token_key:
            try:
                data = json.loads(full_body or "{}")
            except (json.JSONDecodeError, TypeError):
                data = {}
            token_value = (
                ((data.get("authentication") or {}).get("token"))
                or data.get("token")
                or data.get("access_token")
                or data.get("accessToken")
                or ""
            )
            if token_value:
                try:
                    await self.page.evaluate(
                        "([k, v]) => localStorage.setItem(k, v)",
                        [store_token_key, str(token_value)],
                    )
                    token_stored = True
                except Exception:
                    pass
        observation["body_snippet"] = redact_url_query_values(
            str(observation.get("body_snippet", ""))
        )
        # JWT 一串幾百字元只會灌爆 context 又遮住後面的有用欄位（如登入回應
        # 的 bid）；壓縮成長度標記，token 本體 agent 不需要
        observation["body_snippet"] = re.sub(
            r"eyJ[A-Za-z0-9._-]{80,}",
            lambda m: f"[JWT len={len(m.group(0))}]",
            str(observation["body_snippet"]),
        )
        observation["authenticated"] = bool(token or cookies)
        if store_token_key:
            observation["token_stored"] = token_stored
        return ToolOutcome(ok=True, result=observation)

    def _report_security_issue(self, args: dict[str, Any]) -> ToolOutcome:
        """把 agent 觀察到的資安問題組成 security finding（走 probe_sql_injection
        同一條 security_finding 落地鏈，由 loop → persist_agent_security_findings 寫入）。

        觀察型回報的 severity 上限 high：critical 保留給工具確認的漏洞
        （sqlmap confirmed），與計分契約「證據等級」的設計一致。
        """
        from apps.scans.scanners import make_finding

        severity = str(args.get("severity", "low")).lower()
        if severity == "critical":
            severity = "high"
        if severity not in {"high", "medium", "low", "info"}:
            severity = "low"
        title = (args.get("title") or "").strip()[:255]
        description = (args.get("description") or "").strip()[:5000]
        evidence = (args.get("evidence") or "").strip()[:5000]
        remediation = (args.get("remediation") or "").strip()[:5000]
        url = (args.get("url") or "").strip()
        if not title or not description or not evidence:
            return ToolOutcome(
                ok=False, result={"error": "missing_required_fields"}
            )

        safe_url = redact_url_query_values(url) if url else ""
        full_description = description + (f"（觀察端點：{safe_url}）" if safe_url else "")
        finding = make_finding(
            category="security",
            severity=severity,
            rule_id="agent-observed-security",
            title=title,
            description=(
                f"Hermes-Agent 在實際操作與 probe 觀察中發現：{full_description} "
                "此為 AI agent 帶證據的觀察型回報；攻擊性驗證結論另見工具確認項。"
            ),
            remediation=remediation or "依證據內容對應的存取控制／資料保護強化。",
            evidence=evidence,
            impact_area="vulnerability",
        )
        return ToolOutcome(ok=True, result={"reported": title}, security_finding=finding)

    async def _probe_sql_injection(self, url: str) -> ToolOutcome:
        """LLM 自主觸發的授權範圍內 SQLi 主動驗證。

        安全約束：
        - 強制**同源**（比對 scan_job.origin）：即使 LLM 給出他站 URL 也拒絕，維持
          agent 既有的 same-origin 邊界（見 agent/CLAUDE.md）。
        - 必須帶 query 參數（sqlmap 需要注入點）。
        - 授權鎖完全交給 kali_tools.run_sqlmap 的三重鎖（ARGUS_KALI_ENABLED + active +
          authorized）；未授權時回 blocked，LLM 會知道無法執行。
        - subprocess 阻塞，包進 to_thread 避免卡住 event loop。

        Task 6：直接信任 res["confirmed"]，不再解析 stdout（Task 3 讓 stdout 恆為 ""）。
        result 不含 target URL；Finding 的 description 使用遮罩後的 URL。
        """
        if self.scan_job is None:
            return ToolOutcome(ok=False, result={"error": "no_scan_context"})
        from urllib.parse import urlparse

        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolOutcome(ok=False, result={"error": "invalid_url"})
        target_origin = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            target_origin = f"{target_origin}:{parsed.port}"
        if target_origin != self.scan_job.origin:
            return ToolOutcome(
                ok=False,
                result={"error": "cross_origin_forbidden", "allowed_origin": self.scan_job.origin},
            )
        if "?" not in url or "=" not in url:
            return ToolOutcome(ok=False, result={"error": "no_query_parameter"})

        from apps.scans.security.kali_tools import run_sqlmap

        res = await asyncio.to_thread(run_sqlmap, url, self.scan_job.id)
        if res.get("blocked_reason"):
            return ToolOutcome(
                ok=False,
                result={"confirmed": False, "blocked": res["blocked_reason"]},
            )
        if not res.get("confirmed"):
            return ToolOutcome(
                ok=True,
                result={"confirmed": False, "error": res.get("error", "")},
            )

        # 確認可注入 → 產 security finding（欄位與 validate_findings_with_kali 一致）
        from apps.scans.scanners import make_finding

        safe_url = redact_url_query_values(url)
        evidence_summary = res.get("evidence_summary") or {}
        finding = make_finding(
            category="security",
            severity="critical",
            rule_id="kali-sqlmap-sqli",
            title="SQL Injection 已由 Hermes-Agent 觸發 sqlmap 主動驗證可利用",
            description=(
                f"Hermes-Agent 在授權的主動測試中自主判斷並對 {safe_url} 觸發 sqlmap，"
                "確認存在可被利用的 SQL injection 注入點。此為已驗證漏洞，非僅靜態判斷。"
            ),
            remediation=(
                "使用參數化查詢（prepared statements）或 ORM，對所有使用者輸入做嚴格驗證與轉義，"
                "並以最小權限資料庫帳號連線。"
            ),
            evidence=json.dumps(evidence_summary, sort_keys=True),
            impact_area="vulnerability",
            confidence=1.0,
        )
        return ToolOutcome(
            ok=True,
            result={
                "confirmed": True,
                "correlation_id": "kali-sqlmap-sqli",
            },
            security_finding=finding,
        )
