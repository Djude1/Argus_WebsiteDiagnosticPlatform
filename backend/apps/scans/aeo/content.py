"""AEO 第 1 層：能否取得內容。

- 從 HTML 擷取「正文」：排除導覽、頁首頁尾、側欄、隱藏內容與程式碼，切成可引用的段落，
  每段保留所在頁面、最近的小標題與順序（報告用來指出答案位置）。
- 分別處理原始 HTML（伺服器回應）與瀏覽器渲染後的 DOM：Google 會執行 JavaScript，
  所以「原始 HTML 文字較少」不能直接判成「搜尋引擎看不到」，但兩版差異值得量測並說明。
- 讀出索引與摘要限制（robots meta、X-Robots-Tag、data-nosnippet）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# 整個子樹都不算正文的標籤
_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "header",
    "aside",
    "form",
    "select",
    "button",
}
_SKIP_ROLES = {"navigation", "banner", "complementary", "search", "menu"}
# 頁尾不算正文，但聯絡方式常只寫在頁尾：保留下來並標記區域，只給聯絡類問題使用
_FOOTER_TAGS = {"footer"}
# 段落邊界
_BLOCK_TAGS = {
    "p",
    "li",
    "dd",
    "dt",
    "td",
    "th",
    "blockquote",
    "summary",
    "figcaption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "div",
    "section",
    "article",
    "main",
    "tr",
    "dl",
    "ul",
    "ol",
    "table",
    "details",
    "caption",
    "address",
    "pre",
}
_SECTION_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# FAQ 式的問題標題：只在所屬的 dl／details 內有效，容器結束就回到章節標題
_QA_HEADINGS = {"summary", "dt"}
_QA_CONTAINERS = {"dl", "details"}
_HEADING_TAGS = _SECTION_HEADINGS | _QA_HEADINGS
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_WS = re.compile(r"\s+")

MIN_PASSAGE_CHARS = 6
# 有些網站把整段內文包在 h2/h3 裡（例如隱私權政策逐條用 h3）。超過這個長度、
# 或含句號等句子標點的「標題」實際上是內文，當段落處理才找得到裡面的答案。
MAX_HEADING_CHARS = 80
_SENTENCE_END = re.compile(r"[。；！]|\.\s")
# 標題很短也有意義（「價格」「購買須知」），門檻另計
MIN_HEADING_CHARS = 2


@dataclass
class Passage:
    """一段可引用的正文。"""

    page_url: str
    index: int
    text: str
    heading: str = ""
    is_heading: bool = False
    region: str = "main"  # "main"＝正文；"footer"＝頁尾
    # 段落有文字在 data-nosnippet 區塊內：Google 不會拿這段當摘要（引用可得性，roadmap §2 第 6 項）
    nosnippet: bool = False

    def location(self) -> str:
        if self.region == "footer":
            return "頁尾"
        return f"「{self.heading}」段落" if self.heading else f"第 {self.index + 1} 段"


@dataclass
class PageContent:
    url: str
    passages: list[Passage] = field(default_factory=list)
    text_chars: int = 0

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.passages if p.region == "main")


def _is_body_text(text: str) -> bool:
    """標題標籤裡其實是一段內文（長句或含句號），不能當標題、也不能從檢索中略過。"""
    return len(text) > MAX_HEADING_CHARS or bool(_SENTENCE_END.search(text.rstrip("。！!？? ")))


class _MainTextParser(HTMLParser):
    """把 HTML 切成正文段落；略過非正文子樹、hidden／aria-hidden／display:none 元素。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        # (tag, 是否開啟略過, 是否頁尾, 是否 data-nosnippet)
        self.stack: list[tuple[str, bool, bool, bool]] = []
        self.footer_depth = 0
        self.buffer: list[str] = []
        self.current_is_heading = False
        self.heading = ""
        self.section_heading = ""
        self.current_heading_tag = ""
        # (text, heading, is_heading, region, nosnippet)
        self.blocks: list[tuple[str, str, bool, str, bool]] = []
        self.nosnippet_blocks = 0
        self._nosnippet_depth = 0
        self._buffer_nosnippet = False

    def _flush(self) -> None:
        text = _WS.sub(" ", "".join(self.buffer)).strip()
        nosnippet = self._buffer_nosnippet
        self.buffer = []
        self._buffer_nosnippet = False
        if not text:
            return
        region = "footer" if self.footer_depth else "main"
        heading = self.heading if region == "main" else ""
        if self.current_is_heading and _is_body_text(text):
            self.blocks.append((text, heading, False, region, nosnippet))
            return
        if self.current_is_heading:
            if region == "main":
                self.heading = text[:120]
                if self.current_heading_tag in _SECTION_HEADINGS:
                    self.section_heading = self.heading
            self.blocks.append((text, text[:120], True, region, nosnippet))
        else:
            self.blocks.append((text, heading, False, region, nosnippet))

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}
        skip = (
            tag in _SKIP_TAGS
            or "hidden" in a
            or a.get("aria-hidden", "").lower() == "true"
            or a.get("role", "").lower() in _SKIP_ROLES
            or bool(_HIDDEN_STYLE.search(a.get("style", "")))
        )
        nosnippet = "data-nosnippet" in a and not self.skip_depth
        if nosnippet:
            self.nosnippet_blocks += 1
        if tag in _VOID_TAGS:
            if tag == "br" and not self.skip_depth:
                self.buffer.append(" ")
            return
        if tag in _BLOCK_TAGS and not self.skip_depth:
            self._flush()
            self.current_is_heading = tag in _HEADING_TAGS
            self.current_heading_tag = tag if self.current_is_heading else ""
        is_footer = (tag in _FOOTER_TAGS or a.get("role", "").lower() == "contentinfo") and not skip
        if skip:
            self.skip_depth += 1
        if is_footer:
            self._flush()
            self.footer_depth += 1
        if nosnippet:
            self._nosnippet_depth += 1
        self.stack.append((tag, skip, is_footer, nosnippet))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID_TAGS:
            return
        # 容錯：往回找到對應的開標籤（HTML 常有未閉合標籤）
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self._flush()
                for _, opened_skip, opened_footer, opened_nosnippet in self.stack[i:]:
                    if opened_skip:
                        self.skip_depth -= 1
                    if opened_footer:
                        self.footer_depth -= 1
                    if opened_nosnippet:
                        self._nosnippet_depth -= 1
                del self.stack[i:]
                break
        if tag in _BLOCK_TAGS and not self.skip_depth:
            self._flush()
            self.current_is_heading = False
        if tag in _QA_CONTAINERS and not self.skip_depth:
            self.heading = self.section_heading

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.buffer.append(data)
            if self._nosnippet_depth and data.strip():
                self._buffer_nosnippet = True

    def close(self) -> None:
        super().close()
        self._flush()


def extract_page_content(url: str, html: str) -> PageContent:
    """擷取正文段落。去除重複段落（例如同一段落在 RWD 版型重複出現）。"""
    parser = _MainTextParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 — 壞掉的 HTML 不應讓整次分析失敗
        pass
    content = PageContent(url=url)
    seen: set[str] = set()
    for text, heading, is_heading, region, nosnippet in parser.blocks:
        minimum = MIN_HEADING_CHARS if is_heading else MIN_PASSAGE_CHARS
        if len(text) < minimum or text in seen:
            continue
        seen.add(text)
        content.passages.append(
            Passage(
                page_url=url,
                index=len(content.passages),
                text=text[:1200],
                heading=heading,
                is_heading=is_heading,
                region=region,
                nosnippet=nosnippet,
            )
        )
    content.text_chars = sum(
        len(p.text) for p in content.passages if not p.is_heading and p.region == "main"
    )
    return content


def nosnippet_block_count(html: str) -> int:
    parser = _MainTextParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001
        return 0
    return parser.nosnippet_blocks


# ---------- 索引與摘要限制 ----------

_ROBOTS_META = re.compile(
    r"<meta\b[^>]*\bname\s*=\s*[\"'](?:robots|googlebot)[\"'][^>]*>", re.IGNORECASE
)
_CONTENT_ATTR = re.compile(r"\bcontent\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)


def robots_directives(html: str, headers: dict | None) -> dict[str, str]:
    """回傳 {指令: 出處}，例如 {"noindex": "meta robots", "nosnippet": "X-Robots-Tag"}。"""
    found: dict[str, str] = {}

    def _add(raw: str, source: str) -> None:
        for token in re.split(r"[,\s]+", raw.lower()):
            token = token.strip()
            if not token:
                continue
            if token in {"noindex", "nosnippet", "none"} or token.startswith("max-snippet"):
                found.setdefault(token.replace(" ", ""), source)

    for tag in _ROBOTS_META.findall(html or ""):
        match = _CONTENT_ATTR.search(tag)
        if match:
            _add(match.group(1), "meta robots")
    for key, value in (headers or {}).items():
        if str(key).lower() == "x-robots-tag":
            # 「googlebot: noindex」這類帶 user-agent 前綴的寫法也要拆出指令
            _add(re.sub(r"^[\w-]+\s*:\s*", "", str(value)), "X-Robots-Tag")
    return found


def blocks_indexing(directives: dict[str, str]) -> bool:
    return "noindex" in directives or "none" in directives


def blocks_snippets(directives: dict[str, str]) -> bool:
    if "nosnippet" in directives or "none" in directives:
        return True
    return any(k.startswith("max-snippet") and k.endswith(":0") for k in directives)
