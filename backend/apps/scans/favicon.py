"""網站專案的 favicon：從首頁宣告的圖示（沒有就 /favicon.ico）抓取，縮成小 PNG 存進專案。

兩個時機：新增專案時立刻抓（`refresh_project_favicon_from_url`，使用者加入網站當下就看得到圖示）；
之後每次掃描在 `tasks.stage_favicon` 用爬到的首頁 HTML 更新（最多每 7 天一次）。

只供會員區辨識網站用（專案切換器、所有專案、總覽）。抓取一律先過
assert_public_http_url（含每次轉址）、限制大小與逾時；任何失敗都只是沒有圖示，
不影響掃描。存的是 data URL，前端用 <img> 顯示（SVG 在 <img> 內不會執行腳本）。
"""

from __future__ import annotations

import base64
import io
import time
from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
from django.conf import settings
from django.utils import timezone

from apps.scans.services import assert_public_http_url

# 原始檔讀取上限（.ico 常含多種尺寸，30–100KB 都常見）；輸出縮成 ICON_SIZE 的 PNG，通常只有幾 KB
MAX_ICON_BYTES = 200_000
# 新增專案時要先抓首頁 HTML 找 <link rel=icon>；只需要 <head>，讀前 512KB 就夠
MAX_HTML_BYTES = 512_000
# 新增專案的 API 會等圖示抓完再回應，整體時間上限（逾時就先不放圖示，下次掃描再補）
CREATE_DEADLINE_SECONDS = 8.0
MAX_SVG_BYTES = 20_000
ICON_SIZE = 64
HTTP_TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 3
MAX_CANDIDATES = 3
# 抓過之後多久內不再重抓（每次掃描都會經過這裡）
REFRESH_AFTER_DAYS = 7


class _IconLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []  # (rel, href, sizes)

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        values = {name.lower(): (value or "") for name, value in attrs}
        rel = values.get("rel", "").lower()
        if "icon" in rel.split() and values.get("href"):
            self.links.append((rel, values["href"].strip(), values.get("sizes", "")))


def _icon_rank(link: tuple[str, str, str]) -> int:
    """偏好：一般 icon（svg／32px 以上）＞ 其他 icon ＞ apple-touch-icon（多半是大圖）。"""
    rel, href, sizes = link
    if "apple-touch-icon" in rel:
        return 2
    if href.lower().endswith(".svg") or any(s in sizes for s in ("32", "48", "64", "96")):
        return 0
    return 1


def icon_candidates(html: str, page_url: str) -> list[str]:
    """首頁 HTML 宣告的圖示網址（依偏好排序，最後補 /favicon.ico），已轉成絕對網址並去重。"""
    parser = _IconLinkParser()
    try:
        parser.feed(html[:200_000])
    except Exception:  # noqa: BLE001 - 壞掉的 HTML 不影響後備的 /favicon.ico
        pass
    urls: list[str] = []
    for link in sorted(parser.links, key=_icon_rank):
        url = urljoin(page_url, link[1])
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    fallback = urljoin(page_url, "/favicon.ico")
    if fallback not in urls:
        urls.append(fallback)
    return urls[:MAX_CANDIDATES]


def _fetch(
    url: str, max_bytes: int = MAX_ICON_BYTES, *, truncate: bool = False
) -> tuple[str, bytes, str]:
    """抓單一網址（每一跳轉址都重新檢查公開位址）；回傳 (content-type, body, 最終網址)。

    超過 max_bytes 時：truncate=True 截斷保留前段（HTML 只需要 <head>），否則視為失敗。
    失敗回 ("", b"", "")。
    """
    # 與爬蟲相同的可辨識 User-Agent（站長看得出是誰）；部分網站（如 Wikipedia）拒絕沒有 UA 的請求
    headers = {
        "User-Agent": settings.ARGUS_SCANNER_USER_AGENT,
        "Accept": "text/html,image/*,*/*;q=0.8",
    }
    with httpx.Client(
        timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=False, headers=headers
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            url = assert_public_http_url(url)
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    return "", b"", ""
                content_type = (
                    response.headers.get("content-type", "").split(";")[0].strip().lower()
                )
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        if not truncate:
                            return "", b"", ""
                        body = body[:max_bytes]
                        break
                return content_type, body, url
    return "", b"", ""


def to_data_url(content_type: str, body: bytes) -> str:
    """把圖示轉成 data URL：點陣圖縮成 ICON_SIZE 的 PNG；SVG 原樣（限大小）。無法辨識回空字串。"""
    if not body:
        return ""
    head = body[:512].lstrip().lower()
    if (
        content_type == "image/svg+xml"
        or head.startswith(b"<svg")
        or (head.startswith(b"<?xml") and b"<svg" in body[:2048].lower())
    ):
        if len(body) > MAX_SVG_BYTES:
            return ""
        return "data:image/svg+xml;base64," + base64.b64encode(body).decode()
    if (
        content_type
        and not content_type.startswith("image/")
        and not content_type.startswith("application/octet")
    ):
        # 例如網站對不存在的 /favicon.ico 回 200 的 HTML 頁；
        # image/x-png 等非標準的 image/* 型別交給 Pillow 判斷
        return ""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(body)) as image:
            if image.format == "ICO":
                # 多尺寸 .ico 取最大的一張再縮
                sizes = sorted(image.info.get("sizes") or [], reverse=True)
                if sizes:
                    image.size = sizes[0]
            image.load()
            icon = image.convert("RGBA")
            icon.thumbnail((ICON_SIZE, ICON_SIZE))
            buffer = io.BytesIO()
            icon.save(buffer, format="PNG", optimize=True)
    except Exception:  # noqa: BLE001 - 不是可解析的圖片就當作沒有圖示
        return ""
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def discover_favicon(html: str, page_url: str, deadline: float | None = None) -> str:
    """依序嘗試候選網址，回傳第一個可用圖示的 data URL；都失敗（或超過 deadline）回空字串。"""
    for url in icon_candidates(html, page_url):
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            content_type, body, _final = _fetch(url)
            data_url = to_data_url(content_type, body)
        except Exception:  # noqa: BLE001 - SSRF 拒絕、逾時、連線錯誤都換下一個候選
            continue
        if data_url:
            return data_url
    return ""


def favicon_for_url(start_url: str, timeout_seconds: float = CREATE_DEADLINE_SECONDS) -> str:
    """還沒有掃描資料時：先抓首頁 HTML 找宣告的圖示，再依序嘗試；抓不到首頁也會試 /favicon.ico。"""
    deadline = time.monotonic() + timeout_seconds
    html, page_url = "", start_url
    try:
        content_type, body, final_url = _fetch(start_url, MAX_HTML_BYTES, truncate=True)
        if body and (not content_type or "html" in content_type):
            html = body.decode("utf-8", errors="replace")
        page_url = final_url or start_url
    except Exception:  # noqa: BLE001 - 首頁抓不到時仍用起始網址的 /favicon.ico
        pass
    return discover_favicon(html, page_url, deadline=deadline)


def needs_refresh(project) -> bool:
    checked = project.favicon_checked_at
    return checked is None or timezone.now() - checked > timedelta(days=REFRESH_AFTER_DAYS)


def refresh_project_favicon(project, html: str, page_url: str) -> None:
    """掃描時用爬到的首頁 HTML 更新圖示。"""
    _store(project, discover_favicon(html, page_url))


def refresh_project_favicon_from_url(project) -> None:
    """新增（或恢復）專案時立刻抓圖示；任何錯誤都只是暫時沒有圖示，不影響建立專案。"""
    try:
        data_url = favicon_for_url(project.start_url)
    except Exception:  # noqa: BLE001
        data_url = ""
    _store(project, data_url)


def _store(project, data_url: str) -> None:
    """抓不到時保留舊圖示（網站暫時出錯不該讓圖示消失），只更新檢查時間。"""
    fields = ["favicon_checked_at"]
    project.favicon_checked_at = timezone.now()
    if data_url:
        project.favicon = data_url
        fields.append("favicon")
    project.save(update_fields=fields)
