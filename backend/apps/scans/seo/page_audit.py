"""逐頁 SEO 檢查：只讀資料庫保存的 HTML，不對目標網站發任何請求。

判定原則（使用者需求與 Sitechecker 參考報告的差異）：
- H1 不必與 Title 完全相同：兩者並列顯示，不做「必須相同」或「必須不同」的判定。
- 繁體中文不直接套用英文字符門檻：長度以「顯示寬度」計算（中日韓全形字＝2、半形＝1），
  搜尋結果是依像素截斷，一個中文字約等於兩個英文字母寬；正文長度以「中文字＋英文詞」計算。
- 每項結論都附原始值（value）與修復建議（advice），由 report 層補上網址與檢測時間。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

from apps.scans.aeo.content import blocks_indexing, extract_page_content, robots_directives

# 搜尋結果標題約 600px、摘要約 920px；以英文字母寬為 1 單位換算
TITLE_WIDTH_RANGE = (20, 60)
DESCRIPTION_WIDTH_RANGE = (70, 160)
# 正文偏少的門檻（英文詞＋中文字÷1.5，約等於英文 150 詞或中文 225 字）
THIN_CONTENT_WORDS = 150
SLOW_LOAD_MS = 3000
VERY_SLOW_LOAD_MS = 6000
MAX_HEADINGS = 120
MAX_IMAGES = 80
MAX_LINKS = 400
GENERIC_ANCHORS = {
    "點此", "點這裡", "按此", "這裡", "更多", "了解更多", "閱讀更多", "詳細", "詳情", "more",
    "click here", "here", "read more", "learn more", "link", "this",
}

_CJK = re.compile(
    "[ᄀ-ᇿ⺀-〿぀-ヿ㄀-ㇿ㐀-䶿"
    "一-鿿가-힯豈-﫿︰-﹏＀-￯]"
)
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
_WS = re.compile(r"\s+")
_SKIP_LINK_SCHEMES = ("javascript:", "mailto:", "tel:", "sms:", "data:")


def display_width(text: str) -> int:
    """搜尋結果的顯示寬度：全形（中日韓）字算 2，其餘算 1。"""
    return sum(2 if _CJK.match(ch) else 1 for ch in text)


def content_size(text: str) -> dict:
    cjk = len(_CJK.findall(text))
    latin_words = len(_LATIN_WORD.findall(_CJK.sub(" ", text)))
    return {
        "cjk_chars": cjk,
        "latin_words": latin_words,
        "word_equivalent": round(latin_words + cjk / 1.5),
    }


def _clean(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


@dataclass
class _Capture:
    kind: str
    attrs: dict
    parts: list[str] = field(default_factory=list)


class _SeoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.lang = ""
        self.meta: dict[str, str] = {}
        self.og: dict[str, str] = {}
        self.canonical = ""
        self.hreflang: list[dict] = []
        self.has_favicon = False
        self.has_viewport = False
        self.headings: list[dict] = []
        self.images: list[dict] = []
        self.image_total = 0
        self.links: list[dict] = []
        self.link_total = 0
        self._captures: list[_Capture] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript", "template"}:
            self._skip_depth += 1
            return
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"].strip()
        elif tag == "title" and not self.title_parts:
            self.in_title = True
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            if name in {"description", "robots", "googlebot"} and name not in self.meta:
                self.meta[name] = a.get("content", "")
            if name == "viewport":
                self.has_viewport = True
            if prop.startswith("og:") and prop not in self.og:
                self.og[prop] = a.get("content", "")
        elif tag == "link":
            rel = {r.strip().lower() for r in a.get("rel", "").split()}
            if "canonical" in rel and not self.canonical:
                self.canonical = a.get("href", "").strip()
            if "alternate" in rel and a.get("hreflang"):
                self.hreflang.append({"lang": a["hreflang"], "href": a.get("href", "")})
            if rel & {"icon", "shortcut", "apple-touch-icon"}:
                self.has_favicon = True
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._captures.append(_Capture(tag, a))
        elif tag == "a":
            self._captures.append(_Capture("a", a))
        elif tag == "img":
            self.image_total += 1
            if len(self.images) < MAX_IMAGES:
                self.images.append({
                    "src": a.get("src") or a.get("data-src") or "",
                    "alt": a["alt"] if "alt" in a else None,
                    "title": a.get("title", ""),
                })
            # 圖片的 alt 是連結文字的一部分（純圖片連結）
            for capture in self._captures:
                if capture.kind == "a" and a.get("alt"):
                    capture.parts.append(f" {a['alt']} ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() in {"a", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self.in_title = False
            return
        for index in range(len(self._captures) - 1, -1, -1):
            if self._captures[index].kind == tag:
                capture = self._captures.pop(index)
                self._finish(capture)
                break

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        for capture in self._captures:
            capture.parts.append(data)

    def _finish(self, capture: _Capture) -> None:
        text = _clean("".join(capture.parts))
        if capture.kind == "a":
            self.link_total += 1
            if len(self.links) < MAX_LINKS:
                self.links.append({
                    "href": capture.attrs.get("href", "").strip(),
                    "text": text[:200],
                    "label": _clean(
                        capture.attrs.get("aria-label") or capture.attrs.get("title") or ""
                    )[:200],
                    "rel": capture.attrs.get("rel", "").lower(),
                })
        elif len(self.headings) < MAX_HEADINGS:
            self.headings.append({"level": int(capture.kind[1]), "text": text[:300]})


def _same_url(a: str, b: str) -> bool:
    def key(url: str) -> tuple:
        parts = urlsplit(urldefrag(url)[0])
        return (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/",
                parts.query)

    return key(a) == key(b)


def page_links(parser: _SeoParser, base_url: str) -> list[dict]:
    """頁面上的 <a href>：轉成絕對網址，略過 javascript:／mailto:／同頁錨點。"""
    links = []
    for link in parser.links:
        href = link["href"]
        if not href or href.startswith("#") or href.lower().startswith(_SKIP_LINK_SCHEMES):
            continue
        absolute = urldefrag(urljoin(base_url, href))[0]
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        if urlsplit(absolute).path.startswith("/cdn-cgi/"):
            continue  # Cloudflare 注入的連結（Email 保護、挑戰頁），不是網站自己的連結
        links.append({**link, "url": absolute})
    return links


def _check(key: str, label: str, level: str, value, advice: str = "") -> dict:
    return {"key": key, "label": label, "level": level, "value": value, "advice": advice}


def _title_check(title: str) -> dict:
    if not title:
        return _check("title", "Title", "critical", "", "加上描述本頁主題的 <title>。")
    width = display_width(title)
    low, high = TITLE_WIDTH_RANGE
    value = f"{title}（{len(title)} 字，寬度 {width}）"
    if width < low:
        return _check("title", "Title", "warning", value,
                      "標題過短，補上頁面主題與品牌（中文約 10–30 字）。")
    if width > high:
        return _check("title", "Title", "warning", value,
                      "標題可能在搜尋結果被截斷，重點放前面（中文約 30 字內）。")
    return _check("title", "Title", "pass", value)


def _description_check(description: str) -> dict:
    if not description:
        return _check("description", "Description", "warning", "",
                      "加上 meta description，摘要本頁內容（中文約 35–80 字）。")
    width = display_width(description)
    low, high = DESCRIPTION_WIDTH_RANGE
    value = f"{description}（{len(description)} 字，寬度 {width}）"
    if width < low:
        return _check("description", "Description", "notice", value,
                      "摘要偏短，可補上頁面能解決的問題（中文約 35–80 字）。")
    if width > high:
        return _check("description", "Description", "notice", value,
                      "摘要可能在搜尋結果被截斷，把重點寫在前 80 字。")
    return _check("description", "Description", "pass", value)


def _h1_check(headings: list[dict]) -> dict:
    h1s = [h["text"] for h in headings if h["level"] == 1]
    if not h1s:
        return _check("h1", "H1", "warning", "（沒有 H1）",
                      "加上一個說明頁面主題的 H1；不必與 Title 完全相同。")
    if len(h1s) > 1:
        return _check("h1", "H1", "notice", " ／ ".join(h1s[:5]) + f"（共 {len(h1s)} 個）",
                      "多個 H1 不會直接受罰，但建議保留一個主標題，其他改用 H2。")
    if not h1s[0]:
        return _check("h1", "H1", "warning", "（H1 沒有文字）", "H1 內要有可讀的文字。")
    return _check("h1", "H1", "pass", h1s[0])


def _heading_structure_check(headings: list[dict]) -> dict:
    counts = {f"h{n}": sum(1 for h in headings if h["level"] == n) for n in range(1, 7)}
    summary = "、".join(f"{k.upper()}×{v}" for k, v in counts.items() if v) or "沒有標題"
    jumps = []
    previous = 0
    for heading in headings:
        if previous and heading["level"] > previous + 1:
            jumps.append(f"H{previous}→H{heading['level']}「{heading['text'][:30]}」")
        previous = heading["level"]
    empty = sum(1 for h in headings if not h["text"])
    if empty:
        return _check("headings", "H1–H6 結構", "warning", f"{summary}；{empty} 個標題沒有文字",
                      "移除空標題，或補上文字。")
    if jumps:
        value = f"{summary}；跳號：{'；'.join(jumps[:3])}"
        return _check("headings", "H1–H6 結構", "notice", value,
                      "標題層級依序往下（H2 之下用 H3），螢幕閱讀器與搜尋引擎較易理解段落關係。")
    return _check("headings", "H1–H6 結構", "pass", summary)


def _content_check(size: dict, text_ratio: float) -> dict:
    value = (f"約 {size['word_equivalent']} 詞（中文字 {size['cjk_chars']}、"
             f"英文詞 {size['latin_words']}）；文字佔原始碼 {text_ratio:.1%}")
    if size["word_equivalent"] < THIN_CONTENT_WORDS:
        return _check("content", "主要內容", "notice", value,
                      "正文偏少；若這是重要頁面，補上能回答使用者問題的說明。"
                      "（中文以字數換算，不套用英文字數門檻）")
    return _check("content", "主要內容", "pass", value)


def _canonical_check(canonical: str, final_url: str) -> dict:
    if not canonical:
        return _check("canonical", "Canonical", "notice", "（未設定）",
                      "建議加上指向本頁標準網址的 canonical，避免參數網址分散權重。")
    absolute = urljoin(final_url, canonical)
    if _same_url(absolute, final_url):
        return _check("canonical", "Canonical", "pass", absolute)
    if urlsplit(absolute).hostname != urlsplit(final_url).hostname:
        return _check("canonical", "Canonical", "warning", absolute,
                      "canonical 指向其他網域，本頁可能不會被收錄；確認這是刻意的。")
    return _check("canonical", "Canonical", "notice", absolute,
                  "canonical 指向其他網址：搜尋引擎會以該網址為準，本頁不會單獨出現在結果中。")


def _robots_check(directives: dict[str, str]) -> dict:
    if not directives:
        return _check("robots", "Robots 指令", "pass", "（無限制）")
    value = "、".join(f"{k}（{v}）" for k, v in directives.items())
    if blocks_indexing(directives):
        return _check("robots", "Robots 指令", "warning", value,
                      "本頁設定 noindex，不會被搜尋引擎收錄；若是要曝光的頁面請移除。")
    return _check("robots", "Robots 指令", "notice", value, "摘要長度或片段受到限制。")


def _images_check(images: list[dict], total: int) -> dict:
    missing = [img["src"] for img in images if img["alt"] is None]
    decorative = sum(1 for img in images if img["alt"] == "")
    value = f"{total} 張圖片；缺 alt {len(missing)}、空 alt（裝飾用）{decorative}"
    if missing:
        return _check("images", "圖片 alt", "warning", value,
                      "為有意義的圖片補上描述性 alt；純裝飾圖片用 alt=\"\"。")
    return _check("images", "圖片 alt", "pass", value)


def _speed_check(load_time_ms: int | None) -> dict:
    if load_time_ms is None:
        return _check("speed", "載入時間", "notice", "（未量測）")
    value = f"{load_time_ms / 1000:.1f} 秒（爬蟲量測，非 Core Web Vitals）"
    if load_time_ms >= VERY_SLOW_LOAD_MS:
        return _check("speed", "載入時間", "warning", value,
                      "載入明顯偏慢：壓縮圖片、延後非必要的 JavaScript、啟用快取。")
    if load_time_ms >= SLOW_LOAD_MS:
        return _check("speed", "載入時間", "notice", value,
                      "載入偏慢，可用 PageSpeed Insights 找出主因。")
    return _check("speed", "載入時間", "pass", value)


def _status_check(status_code: int | None, blocked_reason: str) -> dict:
    if status_code is None:
        return _check("status", "HTTP 狀態", "warning", blocked_reason or "（未取得）",
                      "爬蟲無法取得本頁，確認網站沒有阻擋。")
    if status_code >= 400:
        return _check("status", "HTTP 狀態", "critical", str(status_code),
                      "頁面回應錯誤；修正或從站內連結移除。")
    return _check("status", "HTTP 狀態", "pass", str(status_code))


def _open_graph_check(og: dict) -> dict:
    required = ["og:title", "og:description", "og:image"]
    missing = [key for key in required if not og.get(key)]
    if missing:
        return _check("open_graph", "Open Graph", "notice", f"缺 {', '.join(missing)}",
                      "補上 og:title／og:description／og:image，分享到社群時才有預覽卡片。")
    return _check("open_graph", "Open Graph", "pass", "已設定 og:title、og:description、og:image")


def audit_page(page) -> dict:
    """單頁 SEO 檢查。page 為 apps.scans.models.Page（或欄位相同的物件）。"""
    html = page.rendered_dom or page.html or ""
    final_url = page.final_url or page.url
    parser = _SeoParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 — 壞掉的 HTML 不應讓整頁分析失敗
        pass

    title = _clean("".join(parser.title_parts)) or _clean(page.title)
    description = _clean(parser.meta.get("description", ""))
    directives = robots_directives(html, page.headers or {})
    main = extract_page_content(final_url, html)
    size = content_size(main.text)
    text_ratio = (len(main.text) / len(html)) if html else 0.0

    checks = [
        _status_check(page.status_code, page.blocked_reason),
        _title_check(title),
        _description_check(description),
        _h1_check(parser.headings),
        _heading_structure_check(parser.headings),
        _content_check(size, text_ratio),
        _canonical_check(parser.canonical, final_url),
        _robots_check(directives),
        _images_check(parser.images, parser.image_total),
        _speed_check(page.load_time_ms),
        _open_graph_check(parser.og),
    ]
    canonical = urljoin(final_url, parser.canonical) if parser.canonical else ""
    not_indexable = []
    if page.status_code != 200:
        not_indexable.append(f"HTTP {page.status_code or '未取得'}")
    if blocks_indexing(directives):
        source = directives.get("noindex") or directives.get("none")
        not_indexable.append(f"noindex（{source}）")
    if canonical and not _same_url(canonical, final_url):
        not_indexable.append("canonical 指向其他網址")

    return {
        "page_id": page.id,
        "url": page.url,
        "final_url": final_url,
        "status_code": page.status_code,
        "title": title,
        "description": description,
        "h1": [h["text"] for h in parser.headings if h["level"] == 1],
        "headings": parser.headings,
        "lang": parser.lang,
        "canonical": canonical,
        "robots": directives,
        "indexable": not not_indexable,
        "not_indexable_reasons": not_indexable,
        "content": {**size, "text_ratio": round(text_ratio, 3)},
        "main_text": main.text,
        "images": parser.images,
        "image_total": parser.image_total,
        "open_graph": parser.og,
        "hreflang": parser.hreflang,
        "has_favicon": parser.has_favicon,
        "has_viewport": parser.has_viewport,
        "load_time_ms": page.load_time_ms,
        "html_bytes": len(html.encode("utf-8")),
        "links": page_links(parser, final_url),
        "link_total": parser.link_total,
        "checks": checks,
    }
