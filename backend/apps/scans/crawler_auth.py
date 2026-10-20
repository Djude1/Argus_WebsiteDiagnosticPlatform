"""爬蟲登入態輔助（2026-10-20）。

提供「使用者填了測試帳密時，先登入再以登入狀態爬整站」所需的純函式：候選登入網址、
靜態 HTML 是否含密碼欄位、從頁面抽出像登入頁的連結。實際的瀏覽器操作（填表單、送出、
取 storage_state）在 `crawler.py` 的 `establish_login_state`，才能重用已加固的 context
（同源攔截＋公開目標政策）。

**安全界線**：本模組不碰帳密、不連線；帳密只在 crawler 的登入函式用，且只進 Playwright
的表單欄位，不落 log／DB／findings。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

# 常見登入頁路徑（同源；依序嘗試，數量有限避免打太多頁）
COMMON_LOGIN_PATHS: tuple[str, ...] = (
    "/login", "/signin", "/sign-in", "/account/login", "/accounts/login",
    "/users/sign_in", "/auth/login", "/user/login", "/member/login", "/admin/login",
)
# 連結文字或網址像登入頁的關鍵字
_LOGIN_HINT = re.compile(
    r"(login|log-in|signin|sign-in|sign_in|登入|登錄|登录|會員登入|member[-_]?login)",
    re.I,
)
# 一次最多嘗試幾個候選登入網址（含起始頁）
MAX_LOGIN_CANDIDATES = 6


def _same_origin(url: str, origin: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    netloc_origin = f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")
    return netloc_origin == origin


def _strip_fragment(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


class _FormParser(HTMLParser):
    """收集每個 <form> 內的 input 類型，用來判斷頁面上有沒有登入表單。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[list[dict]] = []
        self._stack_inputs: list[dict] | None = None
        self.loose_inputs: list[dict] = []  # 不在 <form> 裡的 input（SPA 常見）

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "form":
            self._stack_inputs = []
            self.forms.append(self._stack_inputs)
        elif tag == "input":
            info = {k.lower(): (v or "") for k, v in attrs}
            target = self._stack_inputs if self._stack_inputs is not None else self.loose_inputs
            target.append(info)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form":
            self._stack_inputs = None


def _is_password_input(info: dict) -> bool:
    return info.get("type", "").lower() == "password"


def html_has_password_field(html: str) -> bool:
    """靜態 HTML（或已渲染 DOM）裡有沒有可見的密碼欄位——登入頁的最直接訊號。"""
    parser = _FormParser()
    try:
        parser.feed(html or "")
    except Exception:
        return False
    groups = [*parser.forms, parser.loose_inputs]
    return any(any(_is_password_input(i) for i in group) for group in groups)


def extract_login_links(html: str, base_url: str, origin: str) -> list[str]:
    """從頁面抽出「看起來是登入頁」的同源連結（去片段、去重保序）。"""

    class _LinkParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.links: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() != "a":
                return
            attrd = {k.lower(): (v or "") for k, v in attrs}
            href = attrd.get("href", "")
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                return
            text_hint = " ".join(attrd.get(k, "") for k in ("aria-label", "title", "class", "id"))
            self.links.append((href, text_hint))

    parser = _LinkParser()
    try:
        parser.feed(html or "")
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for href, hint in parser.links:
        absolute = _strip_fragment(urljoin(base_url, href))
        if not _same_origin(absolute, origin):
            continue
        if not (_LOGIN_HINT.search(href) or _LOGIN_HINT.search(hint)):
            continue
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def login_candidate_urls(
    start_url: str, origin: str, start_html: str = "",
) -> list[str]:
    """候選登入網址：起始頁本身 → 頁內像登入頁的連結 → 常見登入路徑。同源、去重、設上限。"""
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(url: str) -> None:
        clean = _strip_fragment(url)
        if _same_origin(clean, origin) and clean not in seen:
            seen.add(clean)
            candidates.append(clean)

    _add(start_url)
    for link in extract_login_links(start_html, start_url, origin):
        _add(link)
    for path in COMMON_LOGIN_PATHS:
        _add(origin + path)
    return candidates[:MAX_LOGIN_CANDIDATES]
