"""Google Search Console 串接（OAuth 2.0 web flow，scope 只有 webmasters.readonly）。

流程：
1. 前端呼叫 connect，取得 Google 授權網址；state 以 Django signing 簽章（含專案、使用者、
   nonce，10 分鐘有效），nonce 另寫進 HttpOnly cookie。callback 必須同時對上兩者，
   避免攻擊者讓受害者把自己的 Google 帳號接到攻擊者的專案（OAuth CSRF）。
2. Google 導回 callback：用 code 換 refresh token，Fernet 加密後存 SearchConsoleConnection。
3. 之後每次查詢以 refresh token 換短效 access token（不保存 access token）。

設定（.env／K8s Secret）：GOOGLE_OAUTH_CLIENT_ID（與登入共用）、GOOGLE_OAUTH_CLIENT_SECRET、
ARGUS_GSC_REDIRECT_URI（選填；沒設時以目前網域的 /api/gsc/callback/ 組成，該網址必須登記在
Google Cloud OAuth 用戶端的「已授權的重新導向 URI」）。refresh token 加密金鑰預設由
SECRET_KEY 推導，可用 ARGUS_GSC_TOKEN_KEY（Fernet key）獨立設定。
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import date, timedelta
from urllib.parse import quote, urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.core.cache import cache

from apps.scans.seo.link_check import registrable_domain

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - 公開端點，不是密碼
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API_BASE = "https://www.googleapis.com/webmasters/v3"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
STATE_SALT = "argus-gsc-oauth"
STATE_MAX_AGE = 600
NONCE_COOKIE = "argus_gsc_nonce"
CALLBACK_PATH = "/api/gsc/callback/"
TIMEOUT = 15
CACHE_SECONDS = 3600
ALLOWED_DAYS = (7, 28, 90)
# Search Console 的資料約延遲 2–3 天；以前兩天為期間結尾，避免最後幾天看起來像流量下滑
DATA_LAG_DAYS = 2


class GscError(Exception):
    """可以直接顯示給使用者的錯誤。reconnect=True 代表授權已失效、需要重新連接。"""

    def __init__(self, message: str, *, reconnect: bool = False):
        super().__init__(message)
        self.reconnect = reconnect


def is_enabled() -> bool:
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def _fernet() -> Fernet:
    key = settings.ARGUS_GSC_TOKEN_KEY
    if not key:
        digest = hashlib.sha256(f"argus-gsc-token:{settings.SECRET_KEY}".encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise GscError("Search Console 授權已失效，請重新連接。", reconnect=True) from None


def redirect_uri(request) -> str:
    return settings.ARGUS_GSC_REDIRECT_URI or request.build_absolute_uri(CALLBACK_PATH)


def build_authorization(request, project) -> tuple[str, str]:
    """回傳 (Google 授權網址, nonce)。nonce 由 view 寫進 HttpOnly cookie。"""
    nonce = secrets.token_urlsafe(16)
    state = signing.dumps(
        {"p": project.id, "u": request.user.pk, "n": nonce}, salt=STATE_SALT
    )
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri(request),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}", nonce


def read_state(state: str, nonce_cookie: str) -> dict:
    try:
        data = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE)
    except signing.BadSignature:
        raise GscError("授權連結已過期或無效，請重新連接。") from None
    if not nonce_cookie or not secrets.compare_digest(str(data.get("n", "")), nonce_cookie):
        raise GscError("授權必須在同一個瀏覽器完成，請重新連接。")
    return data


def _post_token(data: dict) -> dict:
    try:
        response = httpx.post(TOKEN_URL, data=data, timeout=TIMEOUT)
    except httpx.HTTPError:
        raise GscError("暫時無法連線到 Google，請稍後再試。") from None
    payload = response.json() if response.content else {}
    if response.status_code != 200:
        if payload.get("error") == "invalid_grant":
            raise GscError("Search Console 授權已失效，請重新連接。", reconnect=True)
        raise GscError("Google 拒絕了授權要求，請重新連接。")
    return payload


def exchange_code(code: str, uri: str) -> str:
    """用授權碼換 refresh token；確認使用者實際授予了 Search Console 權限。"""
    payload = _post_token({
        "code": code,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": uri,
        "grant_type": "authorization_code",
    })
    if SCOPE not in (payload.get("scope") or "").split():
        raise GscError("沒有取得 Search Console 的讀取權限，請在授權畫面勾選後再試。")
    refresh = payload.get("refresh_token")
    if not refresh:
        raise GscError("Google 沒有回傳長期授權，請重新連接。")
    return refresh


def _access_token(connection) -> str:
    payload = _post_token({
        "refresh_token": decrypt_token(connection.refresh_token_encrypted),
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "grant_type": "refresh_token",
    })
    return payload["access_token"]


def _api(connection, method: str, url: str, *, json: dict | None = None, token: str = "") -> dict:
    token = token or _access_token(connection)
    try:
        response = httpx.request(
            method, url, json=json, timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError:
        raise GscError("暫時無法連線到 Search Console，請稍後再試。") from None
    if response.status_code == 401:
        raise GscError("Search Console 授權已失效，請重新連接。", reconnect=True)
    if response.status_code == 403:
        raise GscError(
            "這個 Google 帳號沒有此資源的權限，或尚未在 Google Cloud 啟用 Search Console API。"
        )
    if response.status_code == 429:
        raise GscError("Search Console 查詢次數已達上限，請稍後再試。")
    if response.status_code >= 400:
        raise GscError(f"Search Console 回應錯誤（HTTP {response.status_code}）。")
    return response.json() if response.content else {}


def list_sites(connection) -> list[dict]:
    data = _api(connection, "GET", f"{API_BASE}/sites")
    sites = [
        {"site_url": entry.get("siteUrl", ""), "permission": entry.get("permissionLevel", "")}
        for entry in data.get("siteEntry", [])
        if entry.get("permissionLevel") != "siteUnverifiedUser"
    ]
    return sorted(sites, key=lambda s: s["site_url"])


def property_matches(property_url: str, origin: str) -> bool:
    """資源是否涵蓋這個網站：網域資源比對可註冊網域，網址前置字元資源比對協定＋主機。"""
    host = (urlsplit(origin).hostname or "").lower()
    if property_url.startswith("sc-domain:"):
        domain = property_url.split(":", 1)[1].lower()
        return host == domain or host.endswith(f".{domain}") or (
            registrable_domain(host) == domain
        )
    prefix = urlsplit(property_url)
    target = urlsplit(origin)
    return (prefix.scheme, (prefix.hostname or "").lower()) == (target.scheme, host)


def property_covers_domain(property_url: str, domain: str) -> bool:
    """資源是否證明擁有這個網域：網域資源涵蓋自己與子網域，網址前置字元資源只證明那一個主機。"""
    domain = (domain or "").lower().rstrip(".")
    if not domain:
        return False
    if property_url.startswith("sc-domain:"):
        owned = property_url.split(":", 1)[1].lower().rstrip(".")
        return domain == owned or domain.endswith(f".{owned}")
    return (urlsplit(property_url).hostname or "").lower() == domain


def property_domain(property_url: str) -> str:
    """資源代表的網域：sc-domain:example.com → example.com；
    https://www.example.com/ → www.example.com。"""
    if property_url.startswith("sc-domain:"):
        return property_url.split(":", 1)[1].lower().rstrip(".")
    return (urlsplit(property_url).hostname or "").lower()


def period(days: int, today: date | None = None) -> tuple[date, date]:
    end = (today or date.today()) - timedelta(days=DATA_LAG_DAYS)
    return end - timedelta(days=days - 1), end


def _query(connection, token: str, start: date, end: date, dimensions: list[str],
           row_limit: int) -> list[dict]:
    url = f"{API_BASE}/sites/{quote(connection.property_url, safe='')}/searchAnalytics/query"
    data = _api(connection, "POST", url, token=token, json={
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dimensions,
        "rowLimit": row_limit,
    })
    rows = []
    for row in data.get("rows", []):
        rows.append({
            "keys": row.get("keys", []),
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr": round(float(row.get("ctr", 0.0)), 4),
            "position": round(float(row.get("position", 0.0)), 1),
        })
    return rows


def performance(connection, days: int) -> dict:
    """搜尋成效：查詢字詞（含與前一期比較）、頁面、每日趨勢、字詞對應的頁面。結果快取 1 小時。"""
    if days not in ALLOWED_DAYS:
        days = 28
    cache_key = f"argus:gsc:{connection.id}:{connection.property_url}:{days}:{date.today()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    start, end = period(days)
    prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)
    token = _access_token(connection)
    queries = _query(connection, token, start, end, ["query"], 200)
    previous = {
        row["keys"][0]: row
        for row in _query(connection, token, prev_start, prev_end, ["query"], 500)
    }
    pages = _query(connection, token, start, end, ["page"], 500)
    trend = _query(connection, token, start, end, ["date"], days + 5)
    query_pages = _query(connection, token, start, end, ["query", "page"], 1000)

    top_page: dict[str, dict] = {}
    for row in query_pages:
        query, page = row["keys"]
        if query not in top_page or row["clicks"] > top_page[query]["clicks"] or (
            row["clicks"] == top_page[query]["clicks"]
            and row["impressions"] > top_page[query]["impressions"]
        ):
            top_page[query] = {"url": page, "clicks": row["clicks"],
                               "impressions": row["impressions"]}

    query_rows = []
    for row in queries:
        query = row["keys"][0]
        before = previous.get(query)
        query_rows.append({
            "query": query,
            "clicks": row["clicks"],
            "impressions": row["impressions"],
            "ctr": row["ctr"],
            "position": row["position"],
            "clicks_change": row["clicks"] - before["clicks"] if before else None,
            "position_change": round(before["position"] - row["position"], 1) if before else None,
            "page": top_page.get(query, {}).get("url", ""),
        })
    totals = {
        "clicks": sum(r["clicks"] for r in trend),
        "impressions": sum(r["impressions"] for r in trend),
    }
    impressions = totals["impressions"]
    totals["ctr"] = round(totals["clicks"] / impressions, 4) if impressions else 0
    result = {
        "property": connection.property_url,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "totals": totals,
        "queries": query_rows,
        "pages": [
            {"url": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"],
             "ctr": r["ctr"], "position": r["position"]}
            for r in pages
        ],
        "trend": [
            {"date": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"],
             "ctr": r["ctr"], "position": r["position"]}
            for r in sorted(trend, key=lambda r: r["keys"][0])
        ],
    }
    cache.set(cache_key, result, CACHE_SECONDS)
    return result


def inspect_url(connection, url: str) -> dict:
    """網址檢查：Google 是否已收錄（與 Argus 判斷的「可索引」是兩件事）。"""
    data = _api(connection, "POST", INSPECT_URL, json={
        "inspectionUrl": url, "siteUrl": connection.property_url, "languageCode": "zh-TW",
    })
    status = (data.get("inspectionResult") or {}).get("indexStatusResult") or {}
    return {
        "url": url,
        "verdict": status.get("verdict", ""),
        "coverage_state": status.get("coverageState", ""),
        "indexing_state": status.get("indexingState", ""),
        "robots_txt_state": status.get("robotsTxtState", ""),
        "page_fetch_state": status.get("pageFetchState", ""),
        "last_crawl_time": status.get("lastCrawlTime", ""),
        "google_canonical": status.get("googleCanonical", ""),
        "user_canonical": status.get("userCanonical", ""),
    }


def revoke(connection) -> None:
    """撤銷 Google 端的授權；失敗不影響本地刪除（使用者也可到 Google 帳號頁面移除）。"""
    try:
        token = decrypt_token(connection.refresh_token_encrypted)
        httpx.post(REVOKE_URL, data={"token": token}, timeout=TIMEOUT)
    except (GscError, httpx.HTTPError):
        pass
