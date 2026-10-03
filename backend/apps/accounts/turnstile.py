"""Cloudflare Turnstile：公開表單的人機驗證（伺服器端 siteverify）。

流程：瀏覽器取得 token → 跟著表單送到我們的 API → 這裡呼叫 siteverify。
一律在後端驗證，要求 success、預期的 action 與允許的前端 hostname 三者都符合。

啟用條件：TURNSTILE_SITE_KEY 與 TURNSTILE_SECRET 都有設定。沒設定時（本機開發、CI）不檢查，
前端也不顯示元件（由 GET /api/auth/turnstile/ 告知）；正式環境啟用但 TURNSTILE_HOSTNAMES
為空會被系統檢查擋下（accounts.E002；只設一半是警告 W001）。
token 只能用一次，重送會被 Cloudflare 拒絕。
"""

import logging

import httpx
from config.client_ip import resolve_client_ip
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_FIELD = "cf-turnstile-response"
TOKEN_MAX_LENGTH = 2048
# 同步呼叫會佔住 worker，逾時不宜太長；逾時一律視為未通過
TIMEOUT_SECONDS = 5

FAILED_MESSAGE = "人機驗證未通過或已過期，請重新驗證後再送出。"


def turnstile_enabled() -> bool:
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET)


def verify_turnstile(request, expected_action: str) -> bool:
    """呼叫 siteverify；任何錯誤（逾時、非 200、格式不符）都視為未通過。"""
    token = request.data.get(TOKEN_FIELD) if hasattr(request.data, "get") else None
    hostnames = set(settings.TURNSTILE_HOSTNAMES)
    if not isinstance(token, str) or not token or len(token) > TOKEN_MAX_LENGTH:
        return False
    if not hostnames:
        return False
    try:
        response = httpx.post(
            SITEVERIFY_URL,
            data={
                "secret": settings.TURNSTILE_SECRET,
                "response": token,
                "remoteip": resolve_client_ip(request),
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Turnstile siteverify 呼叫失敗", exc_info=True)
        return False
    if not isinstance(result, dict):
        return False
    if result.get("success") is not True:
        # 只記錯誤代碼，不記 token
        logger.info("Turnstile 驗證未通過：%s", result.get("error-codes"))
        return False
    # Cloudflare 測試用 secret（1x000…AA）不回 action、hostname 固定 example.com；
    # 只在 DEBUG 本機接受，正式環境用真的 secret，不會帶這個標記。
    if settings.DEBUG and (result.get("metadata") or {}).get("result_with_testing_key") is True:
        return True
    return result.get("action") == expected_action and result.get("hostname") in hostnames


def turnstile_rejection(request, expected_action: str):
    """未啟用或驗證通過回 None；否則回 403 Response，由 view 直接 return。"""
    if not turnstile_enabled() or verify_turnstile(request, expected_action):
        return None
    return Response(
        {"detail": FAILED_MESSAGE, "code": "turnstile_failed"},
        status=status.HTTP_403_FORBIDDEN,
    )
