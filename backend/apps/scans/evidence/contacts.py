"""共用聯絡資訊證據：Email、電話與地址（P0-B Shared Evidence MVP）。

資安（`scanners.analyze_data_exposure`，個資外洩分級）與 AEO（`aeo/answers.py`，「聯絡
Email／電話是什麼」）都從這裡取格式與擷取結果，不再各自維護一套 regex。

地址（2026-10-08）：AEO「地址在哪裡」與結構化資料（JSON-LD `address`，SEO 的必填欄位檢查讀
同一份標記）共用。地址只寫在 JSON-LD 時，搜尋引擎讀得到、頁面文字卻沒有，AEO 照樣判定
找不到，但理由要說明它在結構化資料裡，不能只說「找不到」。

每筆證據帶最小情境（context contract）：來源網址、取得方式（渲染後 DOM／原始 HTML）、
所在位置（一般內容／HTML 註解／mailto・tel 連結）、視窗（桌面版）與登入狀態（匿名）。
情境不同的觀察不強制一致：例如 Email 只在頁首導覽或 HTML 註解，資安會列出、AEO 判定正文
沒有答案，兩者都對——AEO 會在理由中說明它在哪裡，而不是單純說「找不到」。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# Email：要求 TLD 至少 2 字元
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# 台灣手機：09 開頭 + 8 位數字，允許中間有 -、空白；前後不可接數字，避免嵌入更長數字串誤判
TW_MOBILE_PATTERN = re.compile(r"(?<!\d)09\d{2}[\s\-]?\d{3}[\s\-]?\d{3}(?!\d)")

# 電話（市話、手機、國際格式、分機）：AEO 判斷「頁面有沒有寫電話」用
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?886[-\s]?\(?0?\d{1,2}\)?[-\s]?\d{3,4}[-\s]?\d{3,4}"
    r"|0\d{1,2}[-\s)]\s?\d{3,4}[-\s]?\d{3,4}"
    r"|09\d{2}[-\s]?\d{3}[-\s]?\d{3}"
    r"|\(\d{2,3}\)\s?\d{3,4}[-\s]?\d{3,4}"
    r"|\+?\d{1,3}[-\s]\d{2,4}[-\s]\d{3,4}[-\s]?\d{3,4})(?:\s*(?:#|分機|ext\.?)\s*\d{1,5})?(?!\d)",
    re.IGNORECASE,
)

# 地址：台灣（縣市＋區鄉鎮＋路街＋號）與英文街道地址
ADDRESS_PATTERN = re.compile(
    r"(?:[一-鿿]{1,4}[縣市])?[一-鿿]{1,4}[區鄉鎮市]"
    r"[一-鿿\d]{0,12}(?:路|街|大道)(?:[一二三四五六七八九十\d]+段)?"
    r"(?:[\d一二三四五六七八九十]+巷)?(?:[\d一二三四五六七八九十]+弄)?\d+(?:之\d+)?號"
    r"|\d{1,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Blvd\.?)",
)

MAILTO_PATTERN = re.compile(r"mailto:([^\"'?>\s]+)", re.IGNORECASE)
TEL_PATTERN = re.compile(r"tel:([+\d][\d\s()-]{6,})", re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--([\s\S]*?)-->")
JSON_LD_BLOCK = re.compile(
    r"<script[^>]*type\s*=\s*[\"']?application/ld\+json[\"']?[^>]*>([\s\S]*?)</script>",
    re.IGNORECASE,
)
# 輸入框 placeholder 是填寫範例（例：e.g.0911-222-333），不是任何人的資料
PLACEHOLDER_ATTR = re.compile(r"""\bplaceholder\s*=\s*(?:"[^"]*"|'[^']*')""", re.IGNORECASE)

EMAIL = "email"
PHONE = "phone"
ADDRESS = "address"

LOCATION_CONTENT = "content"  # 頁面內容（文字或屬性；是否屬於正文由使用端判斷）
LOCATION_COMMENT = "comment"  # 只出現在 HTML 註解，訪客看不到
LOCATION_LINK = "link"  # mailto:／tel: 連結
LOCATION_STRUCTURED = "structured_data"  # 只在 JSON-LD 結構化資料（訪客看不到）

LOCATION_LABELS = {
    LOCATION_CONTENT: "網頁內容",
    LOCATION_COMMENT: "HTML 註解",
    LOCATION_LINK: "mailto／tel 連結",
    LOCATION_STRUCTURED: "結構化資料（JSON-LD）",
}

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    """只留數字並去掉分機；+886 開頭換成本地的 0 開頭，讓兩種寫法比得起來。"""
    main = re.split(r"#|分機|ext", value, maxsplit=1, flags=re.IGNORECASE)[0]
    digits = re.sub(r"\D", "", main)
    if digits.startswith("886"):
        digits = "0" + digits[3:].lstrip("0")
    return digits


def normalize_address(value: str) -> str:
    """去空白與標點、臺→台、全形數字轉半形、英文小寫，讓同一地址的不同寫法比得起來。"""
    text = value.translate(_FULLWIDTH_DIGITS).replace("臺", "台").lower()
    return re.sub(r"[\s,，、.。\-]", "", text)


def find_emails(text: str) -> list[str]:
    """文字中的 Email（去重、保留出現順序）。"""
    return list(dict.fromkeys(EMAIL_PATTERN.findall(text or "")))


def find_mobiles(text: str) -> list[str]:
    """文字中的台灣手機號碼（去重、保留出現順序）。"""
    return list(dict.fromkeys(TW_MOBILE_PATTERN.findall(text or "")))


def find_phones(text: str) -> list[str]:
    """文字中的電話（市話、手機、國際格式），去重、保留出現順序。"""
    return list(dict.fromkeys(m.group(0).strip() for m in PHONE_PATTERN.finditer(text or "")))


def find_addresses(text: str) -> list[str]:
    """文字中的地址（去重、保留出現順序）。"""
    return list(dict.fromkeys(m.group(0).strip() for m in ADDRESS_PATTERN.finditer(text or "")))


def _json_ld_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _json_ld_nodes(item)
    elif isinstance(data, dict):
        yield data
        for value in data.values():
            if isinstance(value, (dict, list)):
                yield from _json_ld_nodes(value)


def _postal_text(value) -> str:
    """JSON-LD 的 address：字串直接用；PostalAddress 只取街道（縣市區另寫在別的欄位，
    頁面文字常省略，用街道比對才不會因寫法不同而漏）。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        street = value.get("streetAddress")
        return street.strip() if isinstance(street, str) else ""
    return ""


def structured_addresses(html: str) -> list[str]:
    """JSON-LD 中的地址（去重、保留出現順序）；語法錯誤的區塊略過。"""
    found: list[str] = []
    for block in JSON_LD_BLOCK.findall(html or ""):
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        for node in _json_ld_nodes(data):
            values = node.get("address")
            for value in values if isinstance(values, list) else [values]:
                text = _postal_text(value)
                if text and text not in found:
                    found.append(text)
    return found


def mailto_addresses(html: str) -> set[str]:
    return {normalize_email(m) for m in MAILTO_PATTERN.findall(html or "")}


def tel_numbers(html: str) -> set[str]:
    return {normalize_phone(m) for m in TEL_PATTERN.findall(html or "")}


@dataclass(frozen=True)
class ContactEvidence:
    kind: str  # EMAIL／PHONE／ADDRESS
    value: str  # 原始寫法
    normalized: str
    source_url: str
    location: str  # LOCATION_*
    acquisition: str = "rendered_dom"  # rendered_dom／initial_html
    viewport: str = "desktop"
    auth_context: str = "anonymous"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "value": self.value,
            "source_url": self.source_url,
            "location": self.location,
            "acquisition": self.acquisition,
            "viewport": self.viewport,
            "auth_context": self.auth_context,
        }


def collect_contacts(
    page_url: str, html: str, *, acquisition: str = "rendered_dom"
) -> list[ContactEvidence]:
    """一頁 HTML 中的 Email、電話與地址，每個值只記一次（位置以最「看得到」的為準）。

    位置優先序：mailto／tel 連結 ＞ 頁面內容 ＞ HTML 註解 ＞ 結構化資料。placeholder 範例不算。
    """
    html = html or ""
    comments = "\n".join(HTML_COMMENT.findall(html))
    without_comments = PLACEHOLDER_ATTR.sub(" ", HTML_COMMENT.sub(" ", html))
    # JSON-LD 裡的地址另記為結構化資料，不算頁面內容（Email／電話沿用原本的整頁比對）
    texts = {EMAIL: without_comments, PHONE: without_comments,
             ADDRESS: JSON_LD_BLOCK.sub(" ", without_comments)}
    links = {EMAIL: mailto_addresses(html), PHONE: tel_numbers(html), ADDRESS: set()}
    normalizers = {EMAIL: normalize_email, PHONE: normalize_phone, ADDRESS: normalize_address}
    rank = {LOCATION_LINK: 0, LOCATION_CONTENT: 1, LOCATION_COMMENT: 2, LOCATION_STRUCTURED: 3}
    found: dict[tuple[str, str], ContactEvidence] = {}

    def add(kind: str, value: str, location: str) -> None:
        normalized = normalizers[kind](value)
        if not normalized:
            return
        if normalized in links[kind]:
            location = LOCATION_LINK
        key = (kind, normalized)
        if key in found and rank[found[key].location] <= rank[location]:
            return
        found[key] = ContactEvidence(
            kind, value, normalized, page_url, location, acquisition=acquisition
        )

    for kind, finder in ((EMAIL, find_emails), (PHONE, find_phones), (ADDRESS, find_addresses)):
        for value in finder(texts[kind]):
            add(kind, value, LOCATION_CONTENT)
        for value in finder(comments):
            add(kind, value, LOCATION_COMMENT)
    for value in structured_addresses(html):
        add(ADDRESS, value, LOCATION_STRUCTURED)
    return list(found.values())
