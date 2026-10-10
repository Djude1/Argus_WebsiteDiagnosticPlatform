"""MCP 協定層：JSON-RPC 2.0 over Streamable HTTP（無狀態、只回 application/json）。

規格允許伺服器對 POST 直接回 JSON 而不開 SSE 串流、也不發 Mcp-Session-Id；我們的工具都是
請求／回應式，不需要伺服器主動推播，所以採最單純的無狀態模式，Gunicorn（WSGI）即可承載。

支援的方法：initialize、ping、tools/list、tools/call；通知（沒有 id）一律接受並忽略。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from django.conf import settings

from apps.mcp_access.entitlements import get_entitlement, hit_rate_limit
from apps.mcp_access.models import McpApiKey, McpCallLog
from apps.mcp_access.tools import TOOLS, TOOLS_BY_NAME, ToolContext, ToolError

logger = logging.getLogger(__name__)

# 由新到舊；initialize 時客戶端要求的版本在清單內就照用，否則回最新版
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = "2025-06-18"

SERVER_INFO = {"name": "argus", "title": "Argus 網站健檢", "version": "1.0.0"}
INSTRUCTIONS = (
    "Argus 是 AI網站健檢平台（SEO、AEO、GEO、使用體驗、資安）。"
    "只能掃描使用者擁有或已取得書面授權的網站；建立掃描會預扣點數，"
    "建立前可用 estimate_scan 估價、get_account_status 查餘額。"
    "掃描需要數分鐘，建立後用 get_scan 追蹤進度，完成後用 get_scan_findings 與 "
    "get_scan_report 取得結果。"
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass
class CallContext:
    api_key: McpApiKey
    request: object
    client_name: str = ""
    logs: list = field(default_factory=list)


def rpc_error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def rpc_result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _tool_result(text: str, *, data: dict | None = None, is_error: bool = False) -> dict:
    result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if data is not None:
        result["structuredContent"] = data
    return result


def _log(ctx: CallContext, *, method: str, tool: str = "", outcome: str = McpCallLog.Outcome.OK,
         counted: bool = False, scan_job=None, detail: str = "", started: float = 0.0) -> None:
    McpCallLog.objects.create(
        user=ctx.api_key.user,
        api_key=ctx.api_key,
        method=method,
        tool=tool,
        outcome=outcome,
        counted=counted,
        scan_job=scan_job,
        detail=detail[:200],
        duration_ms=int((time.monotonic() - started) * 1000) if started else 0,
    )


def handle_initialize(ctx: CallContext, msg_id, params: dict) -> dict:
    requested = params.get("protocolVersion")
    version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
    client = params.get("clientInfo") or {}
    ctx.client_name = f"{client.get('name', '')} {client.get('version', '')}".strip()[:120]
    _log(ctx, method="initialize", detail=ctx.client_name)
    return rpc_result(msg_id, {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    })


def handle_tools_call(ctx: CallContext, msg_id, params: dict) -> dict:
    import json

    name = params.get("name")
    arguments = params.get("arguments") or {}
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return rpc_error(msg_id, INVALID_PARAMS, f"未知的工具：{name}")
    if not isinstance(arguments, dict):
        return rpc_error(msg_id, INVALID_PARAMS, "arguments 必須是物件。")

    started = time.monotonic()
    user = ctx.api_key.user
    # 權益在每次呼叫重新判定（入口已擋掉無訂閱者；這裡檢查本月額度與每分鐘上限）
    ent = get_entitlement(user)
    if not ent.allowed:
        _log(ctx, method="tools/call", tool=name, outcome=McpCallLog.Outcome.INVALID,
             detail=ent.reason, started=started)
        return rpc_result(msg_id, _tool_result(ent.reason, is_error=True))
    if ent.remaining <= 0:
        message = (
            f"本月 MCP 呼叫額度（{ent.monthly_quota} 次）已用完，"
            f"將於 {ent.period_end:%Y-%m-%d} 重置；升級方案可提高額度。"
        )
        _log(ctx, method="tools/call", tool=name, outcome=McpCallLog.Outcome.QUOTA_EXCEEDED,
             detail="quota", started=started)
        return rpc_result(msg_id, _tool_result(message, is_error=True))
    if hit_rate_limit(user):
        message = (
            f"呼叫過於頻繁（每分鐘上限 {settings.ARGUS_MCP_RATE_PER_MINUTE} 次），請稍後再試。"
        )
        _log(ctx, method="tools/call", tool=name, outcome=McpCallLog.Outcome.RATE_LIMITED,
             detail="rate", started=started)
        return rpc_result(msg_id, _tool_result(message, is_error=True))

    tool_ctx = ToolContext(user=user, request=ctx.request)
    try:
        data = tool.handler(tool_ctx, arguments)
    except ToolError as exc:
        _log(ctx, method="tools/call", tool=name, outcome=McpCallLog.Outcome.TOOL_ERROR,
             counted=True, scan_job=tool_ctx.scan_job, detail=str(exc), started=started)
        return rpc_result(msg_id, _tool_result(str(exc), is_error=True))
    except Exception:  # noqa: BLE001 — 內部錯誤不外洩細節、不扣額度
        logger.exception("MCP 工具執行失敗 tool=%s user=%s", name, user.pk)
        _log(ctx, method="tools/call", tool=name, outcome=McpCallLog.Outcome.TOOL_ERROR,
             detail="internal_error", started=started)
        return rpc_result(msg_id, _tool_result("伺服器內部錯誤，請稍後再試。", is_error=True))
    _log(ctx, method="tools/call", tool=name, counted=True, scan_job=tool_ctx.scan_job,
         started=started)
    text = json.dumps(data, ensure_ascii=False, indent=1, default=str)
    return rpc_result(msg_id, _tool_result(text, data=data))


def handle_message(ctx: CallContext, message) -> dict | None:
    """處理單一 JSON-RPC 訊息；通知與客戶端回應回傳 None（不需回覆）。"""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return rpc_error(None, INVALID_REQUEST, "不是有效的 JSON-RPC 2.0 訊息。")
    method = message.get("method")
    msg_id = message.get("id")
    if method is None:
        return None  # 客戶端對伺服器請求的回應；我們不發請求，直接忽略
    if "id" not in message:
        return None  # 通知（notifications/initialized、notifications/cancelled…）
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return rpc_error(msg_id, INVALID_PARAMS, "params 必須是物件。")
    if method == "initialize":
        return handle_initialize(ctx, msg_id, params)
    if method == "ping":
        return rpc_result(msg_id, {})
    if method == "tools/list":
        return rpc_result(msg_id, {"tools": [tool.definition() for tool in TOOLS]})
    if method == "tools/call":
        return handle_tools_call(ctx, msg_id, params)
    return rpc_error(msg_id, METHOD_NOT_FOUND, f"不支援的方法：{method}")
