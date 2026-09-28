"""MCP 接入的 HTTP 端點。

- `/api/mcp/`：MCP Streamable HTTP 端點，只接受 `Authorization: Bearer <MCP 憑證>`
  （不吃網站登入的 JWT／cookie，因此不需要 CSRF）。每次請求都重新檢查憑證、帳號與訂閱。
- `/api/mcp/reports/<token>/`：get_scan_report 發出的短效報告下載連結（簽章綁定掃描與使用者）。
- `/api/mcp-access/*`：會員區「MCP 接入中心」頁面用的管理 API（JWT 登入）。
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse, JsonResponse
from django.http.request import split_domain_port, validate_host
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.mcp_access.entitlements import get_entitlement, hit_rate_limit
from apps.mcp_access.keys import KeyLimitReached, authenticate_key, create_api_key, revoke_api_key
from apps.mcp_access.models import McpApiKey, McpCallLog
from apps.mcp_access.protocol import (
    PARSE_ERROR,
    SUPPORTED_PROTOCOL_VERSIONS,
    CallContext,
    handle_message,
    rpc_error,
)
from apps.mcp_access.tools import REPORT_LINK_SALT, TOOLS, public_url
from apps.scans.models import ScanJob

_MAX_BODY_BYTES = 256 * 1024


def _json(body, status_code: int = 200, headers: dict | None = None) -> JsonResponse:
    response = JsonResponse(body, status=status_code, safe=False, json_dumps_params={
        "ensure_ascii": False,
    })
    for key, value in (headers or {}).items():
        response[key] = value
    response["Cache-Control"] = "no-store"
    return response


def _bearer_token(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _first_id(payload):
    if isinstance(payload, dict):
        return payload.get("id")
    return None


def _origin_allowed(request, origin: str) -> bool:
    netloc = urlparse(origin).netloc
    if not netloc:
        return False
    if netloc == request.get_host():
        return True
    domain, _port = split_domain_port(netloc)
    return bool(domain) and validate_host(domain, settings.ALLOWED_HOSTS)


@csrf_exempt
def mcp_endpoint(request):
    if not settings.ARGUS_MCP_ENABLED:
        raise Http404()
    if request.method != "POST":
        # 無狀態伺服器：不提供 GET 的 SSE 串流、也沒有 session 可 DELETE
        response = HttpResponse(status=405)
        response["Allow"] = "POST"
        return response

    # 規格要求檢查 Origin 防 DNS rebinding：瀏覽器來的請求必須是本站允許的主機
    origin = request.META.get("HTTP_ORIGIN")
    if origin and not _origin_allowed(request, origin):
        return _json(rpc_error(None, -32000, "不允許的 Origin。"), 403)

    header_version = request.META.get("HTTP_MCP_PROTOCOL_VERSION")
    if header_version and header_version not in SUPPORTED_PROTOCOL_VERSIONS:
        return _json(rpc_error(None, -32000, f"不支援的 MCP 協定版本：{header_version}"), 400)

    try:
        payload = json.loads(request.body[:_MAX_BODY_BYTES + 1] or b"null")
    except (ValueError, UnicodeDecodeError):
        payload = ...
    if payload is ... or len(request.body) > _MAX_BODY_BYTES:
        return _json(rpc_error(None, PARSE_ERROR, "請求內容不是有效的 JSON。"), 400)

    api_key = authenticate_key(_bearer_token(request))
    if api_key is None:
        return _json(
            rpc_error(_first_id(payload), -32001, "缺少或無效的 Argus MCP 憑證。"),
            401,
            {"WWW-Authenticate": 'Bearer realm="argus-mcp"'},
        )
    user = api_key.user
    entitlement = get_entitlement(user)
    if not entitlement.allowed:
        return _json(rpc_error(_first_id(payload), -32002, entitlement.reason), 403)

    if hit_rate_limit(user, scope="request"):
        return _json(
            rpc_error(_first_id(payload), -32003, "請求過於頻繁，請稍後再試。"),
            429,
            {"Retry-After": "60"},
        )

    # 建立掃描的 serializer 以 request.user 判斷身分與網域授權
    request.user = user
    ctx = CallContext(api_key=api_key, request=request)
    if isinstance(payload, list):
        responses = [r for r in (handle_message(ctx, m) for m in payload) if r is not None]
        body = responses or None
    else:
        body = handle_message(ctx, payload)

    now = timezone.now()
    updates = {"last_used_at": now}
    if ctx.client_name:
        updates["last_client"] = ctx.client_name
    McpApiKey.objects.filter(pk=api_key.pk).update(**updates)

    if body is None:
        return HttpResponse(status=202)
    return _json(body)


def mcp_report_download(request, token: str):
    """MCP 報告連結：簽章內含掃描與使用者，逾時或被竄改即失效。"""
    from apps.scans.views import ensure_report_file, report_file_response

    try:
        value = signing.TimestampSigner(salt=REPORT_LINK_SALT).unsign(
            token, max_age=settings.ARGUS_MCP_REPORT_LINK_TTL
        )
        scan_id, user_id = (int(part) for part in value.split(":"))
    except (signing.BadSignature, ValueError):
        raise Http404("報告連結無效或已過期，請重新呼叫 get_scan_report。") from None
    scan = ScanJob.objects.filter(
        id=scan_id, user_id=user_id, status=ScanJob.Status.COMPLETED
    ).first()
    if scan is None:
        raise Http404("找不到報告。")
    return report_file_response(ensure_report_file(scan))


# ---------- 會員區管理 API ----------

def _key_row(key: McpApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "last_client": key.last_client,
        "revoked_at": key.revoked_at,
        "is_active": key.is_active,
    }


def _call_row(call: McpCallLog) -> dict:
    return {
        "id": call.id,
        "method": call.method,
        "tool": call.tool,
        "outcome": call.outcome,
        "counted": call.counted,
        "scan_id": call.scan_job_id,
        "key_prefix": call.api_key.prefix if call.api_key else None,
        # 成功的工具呼叫不需要附註；initialize 的附註是用戶端名稱（驗證連線時顯示）
        "detail": (
            call.detail
            if call.outcome != McpCallLog.Outcome.OK or call.method == "initialize"
            else ""
        ),
        "duration_ms": call.duration_ms,
        "created_at": call.created_at,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mcp_overview(request):
    user = request.user
    keys = McpApiKey.objects.filter(user=user)
    calls = McpCallLog.objects.filter(user=user).select_related("api_key")[:20]
    return Response({
        "enabled": settings.ARGUS_MCP_ENABLED,
        "endpoint_url": public_url(request, "/api/mcp/"),
        "entitlement": get_entitlement(user).as_dict(),
        "max_keys": settings.ARGUS_MCP_MAX_KEYS,
        "rate_per_minute": settings.ARGUS_MCP_RATE_PER_MINUTE,
        "keys": [_key_row(k) for k in keys],
        "recent_calls": [_call_row(c) for c in calls],
        "tools": [
            {"name": t.name, "title": t.title, "description": t.description,
             "read_only": t.read_only}
            for t in TOOLS
        ],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mcp_create_key(request):
    entitlement = get_entitlement(request.user)
    if not entitlement.allowed:
        return Response({"detail": entitlement.reason}, status=status.HTTP_403_FORBIDDEN)
    try:
        key, raw = create_api_key(request.user, str(request.data.get("name") or ""))
    except KeyLimitReached as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    # 明文只在這一次回應出現
    return Response({"key": _key_row(key), "secret": raw}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mcp_revoke_key(request, key_id: int):
    key = McpApiKey.objects.filter(user=request.user, id=key_id).first()
    if key is None:
        return Response({"detail": "找不到憑證。"}, status=status.HTTP_404_NOT_FOUND)
    revoke_api_key(key)
    return Response({"key": _key_row(key)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mcp_connection_check(request):
    """「驗證連線」：回傳指定時間之後，這位使用者的 MCP 用戶端是否已連上並呼叫過。"""
    since_raw = request.query_params.get("since") or ""
    since = None
    if since_raw:
        from django.utils.dateparse import parse_datetime

        since = parse_datetime(since_raw)
    if since is None:
        return Response({"detail": "since 必須是 ISO 8601 時間。"}, status=400)
    calls = McpCallLog.objects.filter(user=request.user, created_at__gte=since)
    key_id = request.query_params.get("key_id")
    if key_id and key_id.isdigit():
        calls = calls.filter(api_key_id=int(key_id))
    calls = list(calls.select_related("api_key").order_by("created_at")[:20])
    return Response({
        "connected": any(c.method == "initialize" for c in calls),
        "tool_called": any(c.method == "tools/call" for c in calls),
        "calls": [_call_row(c) for c in calls],
    })
