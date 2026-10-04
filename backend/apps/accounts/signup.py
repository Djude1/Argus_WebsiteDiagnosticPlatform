"""註冊流程（2026-10-04）：一律先經 Google 授權確認 Email，再設定用戶名（handle）與密碼。

1. 前端把 Google ID Token 交給 /api/auth/register/google/（或登入時 Google 帳號尚未註冊），
   後端驗證後回傳簽章的 signup_token（含 Email 與姓名，15 分鐘有效），此時還不建立帳號。
2. 使用者設定 handle 與密碼後送 /api/auth/register/，帶 signup_token 才建立帳號。
"""

from __future__ import annotations

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

SIGNUP_SALT = "argus-google-signup"
SIGNUP_MAX_AGE = 15 * 60
HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,29}$")
RESERVED_HANDLES = {
    "admin", "administrator", "root", "argus", "support", "system", "staff", "deleted",
    "api", "login", "register", "settings", "help",
}


class GoogleTokenError(Exception):
    """Google ID Token 無效、過期或 Email 未驗證；訊息可直接顯示。"""


def verify_google_credential(credential: str) -> dict:
    """驗證 Google ID Token，回傳 {email, first_name, last_name}。"""
    if not credential:
        raise GoogleTokenError("缺少 Google ID Token。")
    try:
        info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
            # 容忍 ±10 秒的本機／Google 時鐘漂移（WSL2 從休眠恢復後曾固定慢 2 秒）
            clock_skew_in_seconds=10,
        )
    except ValueError:
        raise GoogleTokenError("Google ID Token 無效或已過期。") from None
    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified"):
        raise GoogleTokenError("Google 帳號 email 未驗證，無法使用。")
    return {
        "email": email,
        "first_name": (info.get("given_name") or "")[:150],
        "last_name": (info.get("family_name") or "")[:150],
    }


def make_signup_token(profile: dict) -> str:
    return signing.dumps(profile, salt=SIGNUP_SALT)


def read_signup_token(token: str) -> dict:
    """回傳 Google 驗證過的資料；過期或被竄改時拋 signing.BadSignature。"""
    return signing.loads(token or "", salt=SIGNUP_SALT, max_age=SIGNUP_MAX_AGE)


def normalize_handle(raw) -> str:
    return str(raw or "").strip().lower()


def handle_error(handle: str, *, exclude_pk=None) -> str:
    """回傳錯誤訊息；合法時回空字串。不能含 @（登入時以 @ 判斷輸入的是 Email 還是用戶名）。"""
    if not HANDLE_RE.match(handle):
        return "用戶名需為 3–30 個英文小寫字母、數字或 _ . -，且以字母或數字開頭。"
    if handle in RESERVED_HANDLES or handle.startswith("deleted-"):
        return "這個用戶名無法使用，請換一個。"
    taken = get_user_model().objects.filter(handle=handle)
    if exclude_pk is not None:
        taken = taken.exclude(pk=exclude_pk)
    if taken.exists():
        return "這個用戶名已被使用。"
    return ""


def find_login_user(identifier: str, *, suspended: bool = False):
    """登入識別：含 @ 視為 Email，否則視為用戶名；回傳啟用中的 User 或 None。

    suspended=True 改找被管理員停用（is_active=False 且未刪除）的帳號，讓登入能回明確的
    「帳號已停用」而不是「帳密錯誤」或被當成未註冊。已刪除的帳號 Email／handle 已清空，找不到。
    """
    identifier = (identifier or "").strip().lower()
    if not identifier:
        return None
    users = get_user_model().objects.filter(is_active=not suspended)
    if suspended:
        users = users.filter(deleted_at__isnull=True)
    if "@" in identifier:
        return users.filter(username=identifier).first() or users.filter(
            email__iexact=identifier
        ).first()
    return users.filter(handle=identifier).first()


def suggest_handle(email: str) -> str:
    """由 Email 帳號部分產生一個目前可用的用戶名建議（使用者可以改）。"""
    base = re.sub(r"[^a-z0-9_.-]", "", (email or "").split("@")[0].lower()).strip("._-")[:24]
    if len(base) < 3:
        base = f"user{base}"
    candidate = base
    for number in range(2, 1000):
        if not handle_error(candidate):
            return candidate
        candidate = f"{base}{number}"
    return ""
