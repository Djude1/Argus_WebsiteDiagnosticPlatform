"""Google Search Console 網域驗證（OAuth 2.0 授權碼流程）。

使用者授權 Argus 以 `webmasters.readonly` 讀取其 Google Search Console
的網站資源清單；僅採信具 siteOwner 權限的 sc-domain 網域資源。
報表讀取權與 URL 字首資源不能證明整個網域的控制權；符合條件的
擁有者不必再自行放置 Argus token。

設計邊界：
- 與 `domain_verification.py` 的三種 token 方法**並存**，作為第四種選項；
  使用者可以完全跳過本方法（前端不點按鈕即不觸發，token 方法照常可用）。
- `access_type=online`：只拿短效 access token 即用即棄，不申請 refresh
  token、不落地儲存任何 Google 憑證、不寫入 log。
- state 以 Django signing（獨立 salt）簽署 user + VerifiedDomain + 隨機 nonce，
  600 秒內單次有效，以 cache.add 原子取得使用權。callback 端點不需 JWT——瀏覽器 302 回來
  時不會帶 Authorization header（access token 只活在 SPA 記憶體），身分
  綁在簽署過的 state 裡，比 session 更貼合這個跳轉流程。
- 所有對 Google 的錯誤訊息一律轉成安全中文；不把回應原文（可能含授權
  細節）帶進 API 回應或 log。
"""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

STATE_MAX_AGE_SECONDS = 600
_STATE_SALT = "argus.gsc-site-verification.v1"
HTTP_TIMEOUT_SECONDS = 15.0

# 一般使用者即使可讀報表，也不能據此授權整個網域接受主動測試。
_VERIFIED_PERMISSION_LEVELS = {"siteOwner"}


class GoogleSiteVerificationError(RuntimeError):
    """GSC 驗證流程失敗（訊息為安全中文，可直接顯示給使用者）。"""


def is_gsc_verification_enabled() -> bool:
    """CLIENT_ID 與 CLIENT_SECRET 同時設定才算啟用（與 Google 登入共用戶端）。"""
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def resolve_redirect_uri(request) -> str:
    """回呼 URI：env 明確覆寫優先，否則依請求 host 組成。

    start 與 callback 兩次呼叫必須得到完全相同的值（Google 換 token 時
    會比對 redirect_uri）；同一使用者的兩次請求都來自同一個瀏覽器 origin，
    因此依請求組成即一致。
    """
    if settings.ARGUS_GSC_REDIRECT_URI:
        return settings.ARGUS_GSC_REDIRECT_URI
    return request.build_absolute_uri(reverse("verified-domain-google-callback"))


def _state_cache_key(state: str) -> str:
    return f"argus:gsc-state:{hashlib.sha256(state.encode()).hexdigest()}"


def build_state(user_id: int, verified_domain_id: int) -> str:
    """簽署並登記獨立 state，避免同秒再次發起時復用既有連結。"""
    state = signing.dumps(
        {"uid": user_id, "did": verified_domain_id, "nonce": secrets.token_urlsafe(32)},
        salt=_STATE_SALT,
    )
    cache.set(_state_cache_key(state), 1, STATE_MAX_AGE_SECONDS)
    return state


def consume_state(state: str) -> dict:
    """驗證並消耗 state；簽名無效、過期或重放都拋 GoogleSiteVerificationError。"""
    if not state:
        raise GoogleSiteVerificationError("缺少驗證狀態（state），請重新發起 Google 驗證。")
    try:
        payload = signing.loads(state, salt=_STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
    except signing.SignatureExpired as exc:
        raise GoogleSiteVerificationError(
            "Google 驗證連結已過期（10 分鐘內有效），請重新點「使用 Google 驗證」。"
        ) from exc
    except signing.BadSignature as exc:
        raise GoogleSiteVerificationError(
            "Google 驗證連結無效，請重新發起驗證。"
        ) from exc
    if (
        not isinstance(payload, dict)
        or type(payload.get("uid")) is not int
        or type(payload.get("did")) is not int
        or payload["uid"] <= 0
        or payload["did"] <= 0
        or not isinstance(payload.get("nonce"), str)
        or not payload["nonce"]
    ):
        raise GoogleSiteVerificationError("Google 驗證連結內容無效，請重新發起驗證。")
    key = _state_cache_key(state)
    if cache.get(key) is None:
        raise GoogleSiteVerificationError(
            "此 Google 驗證連結已使用過或已失效，請重新點「使用 Google 驗證」。"
        )
    # 保留消耗標記至簽名效期結束，兩個同時讀到 issued 的回呼也只有一個能成功。
    if not cache.add(f"{key}:consumed", 1, STATE_MAX_AGE_SECONDS):
        raise GoogleSiteVerificationError(
            "此 Google 驗證連結已使用過，請重新點「使用 Google 驗證」。"
        )
    cache.delete(key)
    return payload


def build_authorization_url(user_id: int, verified_domain_id: int, redirect_uri: str) -> str:
    """產生 Google 授權頁 URL（select_account 讓多帳號使用者選到有 GSC 的那個）。"""
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GSC_SCOPE,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "consent select_account",
        "state": build_state(user_id, verified_domain_id),
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_access_token(code: str, redirect_uri: str) -> str:
    """以授權碼換短效 access token；即用即棄，不落地。"""
    if not code:
        raise GoogleSiteVerificationError("Google 未回傳授權碼，請重新發起驗證。")
    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise GoogleSiteVerificationError("無法連上 Google 授權服務，請稍後再試。") from exc
    if response.status_code != 200:
        raise GoogleSiteVerificationError(
            "Google 授權失敗（無法換取存取權杖），請重新發起驗證。"
        )
    try:
        return response.json()["access_token"]
    except (KeyError, ValueError) as exc:
        raise GoogleSiteVerificationError("Google 授權回應格式異常，請重新發起驗證。") from exc


def fetch_verified_site_entries(access_token: str) -> list[str]:
    """列出該 Google 帳號在 Search Console 具有擁有者權限的資源。"""
    try:
        response = httpx.get(
            GSC_SITES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise GoogleSiteVerificationError("無法連上 Google Search Console，請稍後再試。") from exc
    if response.status_code == 401:
        raise GoogleSiteVerificationError("Google 授權已失效，請重新發起驗證。")
    if response.status_code != 200:
        raise GoogleSiteVerificationError(
            "無法讀取 Google Search Console 的網站清單，請稍後再試。"
        )
    try:
        entries = response.json().get("siteEntry", [])
    except ValueError as exc:
        raise GoogleSiteVerificationError(
            "Google Search Console 回應格式異常，請稍後再試。"
        ) from exc
    return [
        entry["siteUrl"]
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("permissionLevel") in _VERIFIED_PERMISSION_LEVELS
        and entry.get("siteUrl")
    ]


def site_url_matches_domain(site_url: str, domain: str) -> bool:
    """GSC 資源 siteUrl 是否涵蓋 Argus 待驗證網域。

    - `sc-domain:example.com`（網域資源）涵蓋 example.com 與其所有子網域
      ——與 user_owns_domain 的子網域涵蓋規則一致；
    - URL 字首資源只證明特定協定／主機／路徑的權限，不採信為
      VerifiedDomain 的整個網域及子網域授權。
    """
    domain = (domain or "").lower().rstrip(".")
    site_url = (site_url or "").strip().lower()
    if not site_url.startswith("sc-domain:"):
        return False
    scope = site_url[len("sc-domain:") :].rstrip(".")
    try:
        domain = domain.encode("idna").decode("ascii")
        scope = scope.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return bool(scope and domain) and (domain == scope or domain.endswith(f".{scope}"))


def run_google_verification(verified_domain, code: str, redirect_uri: str) -> None:
    """執行 GSC 驗證並更新 VerifiedDomain；不符合時拋例外（由 view 記 last_error）。

    成功路徑與 domain_verification.run_verification 對齊：status=verified、
    method=google_search_console、verified_at/expires_at=TTL、last_error 清空。
    驗證不通過時**不**動狀態（pending 留 pending、rejected 維持人工否決），
    只由 view 把原因寫進 last_error 供前端顯示。
    """
    access_token = exchange_code_for_access_token(code, redirect_uri)
    site_urls = fetch_verified_site_entries(access_token)
    domain = (verified_domain.domain or "").lower().rstrip(".")
    matched = next((url for url in site_urls if site_url_matches_domain(url, domain)), None)
    if matched is None:
        raise GoogleSiteVerificationError(
            f"你的 Google 帳號在 Search Console 中沒有具擁有者權限的 {domain} 網域資源；"
            "請確認 Google 帳號，並在 Search Console 完成「網域」資源的 DNS 驗證，"
            "或改用 Argus 的 DNS TXT / meta 標籤 / 驗證檔方法。"
        )
    now = timezone.now()
    verified_domain.status = verified_domain.Status.VERIFIED
    verified_domain.method = verified_domain.Method.GOOGLE_SEARCH_CONSOLE
    verified_domain.verified_at = now
    verified_domain.expires_at = now + timedelta(days=verified_domain.ttl_days())
    verified_domain.last_checked_at = now
    verified_domain.last_error = ""
    verified_domain.save()
