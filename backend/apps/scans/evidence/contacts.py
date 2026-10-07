"""共用聯絡資訊證據：Email 與電話（P0-B Shared Evidence MVP）。

資安（`scanners.analyze_data_exposure`，個資外洩分級）與 AEO（`aeo/answers.py`，「聯絡
Email／電話是什麼」）都從這裡取格式與擷取結果，不再各自維護一套 regex。

每筆證據帶最小情境（context contract）：來源網址、取得方式（渲染後 DOM／原始 HTML）、
所在位置（一般內容／HTML 註解／mailto・tel 連結）、視窗（桌面版）與登入狀態（匿名）。
情境不同的觀察不強制一致：例如 Email 只在頁首導覽或 HTML 註解，資安會列出、AEO 判定正文
沒有答案，兩者都對——AEO 會在理由中說明它在哪裡，而不是單純說「找不到」。
"""

from __future__ import annotations

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

MAILTO_PATTERN = re.compile(r"mailto:([^\"'?>\s]+)", re.IGNORECASE)
TEL_PATTERN = re.compile(r"tel:([+\d][\d\s()-]{6,})", re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--([\s\S]*?)-->")
# 輸入框 placeholder 是填寫範例（例：e.g.0911-222-333），不是任何人的資料
PLACEHOLDER_ATTR = re.compile(r"""\bplaceholder\s*=\s*(?:"[^"]*"|'[^']*')""", re.IGNORECASE)

EMAIL = "email"
PHONE = "phone"

LOCATION_CONTENT = "content"  # 頁面內容（文字或屬性；是否屬於正文由使用端判斷）
LOCATION_COMMENT = "comment"  # 只出現在 HTML 註解，訪客看不到
LOCATION_LINK = "link"  # mailto:／tel: 連結

LOCATION_LABELS = {
    LOCATION_CONTENT: "網頁內容",
    LOCATION_COMMENT: "HTML 註解",
    LOCATION_LINK: "mailto／tel 連結",
}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str) -> str:
    """只留數字並去掉分機；+886 開頭換成本地的 0 開頭，讓兩種寫法比得起來。"""
    main = re.split(r"#|分機|ext", value, maxsplit=1, flags=re.IGNORECASE)[0]
    digits = re.sub(r"\D", "", main)
    if digits.startswith("886"):
        digits = "0" + digits[3:].lstrip("0")
    return digits


def find_emails(text: str) -> list[str]:
    """文字中的 Email（去重、保留出現順序）。"""
    return list(dict.fromkeys(EMAIL_PATTERN.findall(text or "")))


def find_mobiles(text: str) -> list[str]:
    """文字中的台灣手機號碼（去重、保留出現順序）。"""
    return list(dict.fromkeys(TW_MOBILE_PATTERN.findall(text or "")))


def find_phones(text: str) -> list[str]:
    """文字中的電話（市話、手機、國際格式），去重、保留出現順序。"""
    return list(dict.fromkeys(m.group(0).strip() for m in PHONE_PATTERN.finditer(text or "")))


def mailto_addresses(html: str) -> set[str]:
    return {normalize_email(m) for m in MAILTO_PATTERN.findall(html or "")}


def tel_numbers(html: str) -> set[str]:
    return {normalize_phone(m) for m in TEL_PATTERN.findall(html or "")}


@dataclass(frozen=True)
class ContactEvidence:
    kind: str  # EMAIL／PHONE
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
    """一頁 HTML 中的 Email 與電話，每個值只記一次（位置以最「看得到」的為準）。

    位置優先序：mailto／tel 連結 ＞ 頁面內容 ＞ HTML 註解。placeholder 範例不算。
    """
    html = html or ""
    comments = "\n".join(HTML_COMMENT.findall(html))
    without_comments = PLACEHOLDER_ATTR.sub(" ", HTML_COMMENT.sub(" ", html))
    links = {EMAIL: mailto_addresses(html), PHONE: tel_numbers(html)}
    found: dict[tuple[str, str], ContactEvidence] = {}

    def add(kind: str, value: str, location: str) -> None:
        normalized = normalize_email(value) if kind == EMAIL else normalize_phone(value)
        if not normalized:
            return
        if normalized in links[kind]:
            location = LOCATION_LINK
        key = (kind, normalized)
        if key in found and found[key].location != LOCATION_COMMENT:
            return
        found[key] = ContactEvidence(
            kind, value, normalized, page_url, location, acquisition=acquisition
        )

    for kind, finder in ((EMAIL, find_emails), (PHONE, find_phones)):
        for value in finder(without_comments):
            add(kind, value, LOCATION_CONTENT)
        for value in finder(comments):
            add(kind, value, LOCATION_COMMENT)
    return list(found.values())
