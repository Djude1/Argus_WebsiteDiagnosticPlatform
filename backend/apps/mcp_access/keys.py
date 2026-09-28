"""MCP API 憑證的產生、驗證與撤銷。

格式：`argus_mcp_` ＋ 43 字元 URL-safe 亂數（256 bits）。資料庫只存 SHA-256 雜湊；
憑證本身是高熵亂數，不需要慢雜湊。明文只在建立當下回傳一次，之後無法再取回。
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.mcp_access.models import McpApiKey

KEY_PREFIX = "argus_mcp_"
_DISPLAY_PREFIX_LEN = len(KEY_PREFIX) + 4


class KeyLimitReached(Exception):
    pass


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@transaction.atomic
def create_api_key(user, name: str) -> tuple[McpApiKey, str]:
    """建立一把憑證，回傳 (紀錄, 明文)。每位使用者同時有效的憑證數有上限。"""
    active = McpApiKey.objects.select_for_update().filter(user=user, revoked_at__isnull=True)
    if active.count() >= int(settings.ARGUS_MCP_MAX_KEYS):
        raise KeyLimitReached(
            f"最多同時保留 {settings.ARGUS_MCP_MAX_KEYS} 把有效憑證，請先撤銷不用的憑證。"
        )
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    key = McpApiKey.objects.create(
        user=user,
        name=(name or "").strip()[:60] or "未命名憑證",
        prefix=raw[:_DISPLAY_PREFIX_LEN],
        key_hash=hash_key(raw),
    )
    return key, raw


def authenticate_key(raw: str) -> McpApiKey | None:
    """以明文憑證找出有效（未撤銷）的紀錄；格式不符直接回 None，不查資料庫。"""
    if not raw or not raw.startswith(KEY_PREFIX) or len(raw) > 128:
        return None
    return (
        McpApiKey.objects.select_related("user")
        .filter(key_hash=hash_key(raw), revoked_at__isnull=True)
        .first()
    )


def revoke_api_key(key: McpApiKey) -> None:
    if key.revoked_at is None:
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
