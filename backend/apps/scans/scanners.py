import hashlib
import math
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from apps.scans.ai_bots import SEARCH as AI_SEARCH
from apps.scans.ai_bots import TRAINING as AI_TRAINING
from apps.scans.ai_bots import USER as AI_USER
from apps.scans.ai_bots import blocked as ai_blocked
from apps.scans.evidence import contacts
from apps.scans.models import Finding
from apps.scans.seo.structured_data import validate_blocks as validate_structured_data

# ---------- PII（個人資料）偵測 ----------
# Email 與手機的格式由共用證據模組提供（P0-B），AEO 用同一套，避免兩邊解析結果不一致

# 台灣身分證號：第一碼英文 + 1/2 + 8 位數字。需另經 is_valid_tw_national_id 檢查碼驗證
TW_NATIONAL_ID_PATTERN = re.compile(r"\b[A-Z][12]\d{8}\b")

# 信用卡號：13-19 位數字，常見 16 位 4-4-4-4 格式或無分隔。需另經 is_valid_luhn 驗證
CREDIT_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[\s\-]?){12,18}\d(?!\d)")

# B1: 移除 SVG 元素（雷達圖等動態 SVG 內 polygon points / path d 屬性的浮點座標
# 數字片段巧合通過 Luhn 會被誤判為卡號，已實證 https://camb.xn--gst.tw 雷達圖案例）。
# 用非貪婪 + DOTALL，能抓含巢狀子元素的整段 <svg>...</svg>。
_HTML_SVG_STRIP = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)
# 殘留的 SVG 子元素標籤（裸的 polygon、path、circle 等）整段移除，
# 避免外層 SVG 缺失時座標漏掉。
_HTML_SVG_ELEMENTS = re.compile(
    r"<(?:polygon|polyline|path|circle|ellipse|line|rect|use|g|defs|symbol|marker|pattern|mask|clipPath|filter|feGaussianBlur|feOffset|feMerge|feMergeNode|feColorMatrix|feFlood|feComposite|stop|linearGradient|radialGradient)\b[^>]*/?>",
    re.IGNORECASE,
)
# 同步移除所有 SVG 座標 / 尺寸 / 變換屬性殘留值（保險：若整段 SVG 沒匹配到，仍可清掉純屬性）。
# 補齊比上一版更完整的屬性清單：除 points/d 外含 cx/cy/r/rx/ry/x/y/x1/y1/x2/y2/dx/dy/fx/fy/
# width/height/transform/viewBox/stroke-width/stroke-dasharray/stroke-dashoffset/font-size。
_HTML_PATH_ATTR = re.compile(
    r"""\b(?:points|d|cx|cy|r|rx|ry|x|y|x1|y1|x2|y2|dx|dy|fx|fy|width|height|transform|viewBox|stroke-width|stroke-dasharray|stroke-dashoffset|font-size)\s*=\s*(?:"[^"]*"|'[^']*')""",
    re.IGNORECASE,
)
# B2: HTML 註解抽取（開發者最常把測試資料 / TODO / 卡號 / token 留在 <!-- --> 內）
_HTML_COMMENT = re.compile(r"<!--([\s\S]*?)-->")

# B5: 開發者預留字串（CTF flag 格式 + 常見 placeholder）。
# 正規網站若意外留下這些字串、報告應該直接 echo 給使用者看到、方便定位。
# 涵蓋：`flag{...}`（CTF / 資安教學）、`{{TODO}}`、`<<<placeholder>>>`、明顯的
# `XXX-XXXX-XXXX` 樣式佔位、`Lorem ipsum` 開頭。
_DEV_ARTIFACT_PATTERN = re.compile(
    r"(?:flag\{[a-zA-Z0-9_-]+\}|\{\{\s*TODO[^}]*\}\}|<{2,}[A-Z][A-Z0-9_\s-]*>{2,}|Lorem ipsum\b)",
    re.IGNORECASE,
)

# 台灣身分證號第一碼字母對應的兩位數值（內政部標準）
_TW_ID_LETTER_VALUES = {
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14, "F": 15, "G": 16, "H": 17,
    "I": 34, "J": 18, "K": 19, "L": 20, "M": 21, "N": 22, "O": 35, "P": 23,
    "Q": 24, "R": 25, "S": 26, "T": 27, "U": 28, "V": 29, "W": 32, "X": 30,
    "Y": 31, "Z": 33,
}

# HTML5 語意化區塊標籤，用於 GEO FAST 的 Structured 維度判斷
SEMANTIC_LANDMARK_TAGS = {"main", "article", "header", "nav", "section", "footer", "aside"}

# Open Graph 標籤鍵：決定頁面分享到社群／通訊軟體時的預覽呈現。
# 標準寫法是 property=，少數網站用 name=，兩種都認。
OG_META_KEYS = {"og:title", "og:description", "og:image", "og:url"}

# 不對外索引的後台/管理路徑前綴。這些頁面不需要 SEO/AEO/GEO 評分（補 H1、JSON-LD
# 等對搜尋引擎曝光無意義），但安全性檢查（CSRF token、安全頭部）仍需照常進行。
ADMIN_PATH_PREFIXES = (
    "/admin",
    "/wp-admin",
    "/wp-login",
    "/dashboard",
    "/manage",
    "/management",
    "/api/",
)
# 登入、註冊等帳號功能頁：不是給搜尋引擎收錄的內容頁，同樣跳過 SEO/AEO/GEO
# （2026-10-06 審查：/management/login、/management/register 被要求補 H1）
_AUTH_PATH_SEGMENTS = {
    "login", "signin", "sign-in", "logout", "signout", "sign-out",
    "register", "signup", "sign-up", "forgot-password", "reset-password", "password-reset",
}

# 非 HTML 頁面的二進位/媒體檔案副檔名。這類資源沒有頁面內容，做 SEO/AEO/GEO
# 分析會產生無意義的 finding（例如「APK 連結缺 meta description」）。
NON_HTML_EXTENSIONS = (
    ".apk", ".ipa", ".exe", ".msi", ".dmg", ".deb", ".rpm",
    ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".mov", ".avi", ".wav", ".webm", ".m4a", ".m4v",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tiff",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".css", ".js", ".mjs", ".map",
    ".xml", ".csv", ".json", ".rss", ".atom",
)


def is_valid_tw_national_id(text: str) -> bool:
    """驗證台灣身分證號檢查碼。

    演算法：第一個英文字母對應兩位數（_TW_ID_LETTER_VALUES）拆成十位數與個位數，
    與後續 9 碼數字共 11 個 digit 按 weights [1,9,8,7,6,5,4,3,2,1,1] 加權總和，
    mod 10 == 0 即合法。加檢查碼驗證可大幅降低 regex 對隨機字串的誤判率。
    """
    if not text or len(text) != 10:
        return False
    letter = text[0].upper()
    if letter not in _TW_ID_LETTER_VALUES:
        return False
    n = _TW_ID_LETTER_VALUES[letter]
    digits = [n // 10, n % 10] + [int(c) for c in text[1:]]
    weights = [1, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1]
    return sum(d * w for d, w in zip(digits, weights, strict=True)) % 10 == 0


def is_valid_luhn(text: str) -> bool:
    """Luhn 演算法驗證信用卡號。從右起每隔一位 ×2（超過 9 減 9），總和 mod 10 == 0。

    僅做格式校驗，無法判斷卡號是否實際發行；可大幅降低 regex 對隨機數字串的誤判。
    """
    digits = [int(c) for c in text if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# 信用卡上下文關鍵字：附近出現這些字才把「裸數字串」當卡號，降低隨機數字誤報
_CARD_CONTEXT_KEYWORDS = (
    "card", "卡", "信用", "visa", "master", "amex", "jcb", "unionpay", "銀聯",
    "付款", "payment", "刷卡", "帳單", "cvv", "cvc", "expir", "到期", "持卡",
)


def _is_formatted_card(match: str) -> bool:
    """卡號有 4-4-4-4 / 4-6-5 之類分隔且去分隔後為 15/16 位 → 視為高信心格式。"""
    digits = re.sub(r"\D", "", match)
    return ("-" in match or " " in match) and len(digits) in (15, 16)


def _card_has_context(text: str, match: str, window: int = 48) -> bool:
    """match 在 text 任一出現位置的前後 window 字元內，是否有信用卡關鍵字。"""
    low = text.lower()
    target = match.lower()
    idx = low.find(target)
    while idx != -1:
        seg = low[max(0, idx - window): idx + len(target) + window]
        if any(k in seg for k in _CARD_CONTEXT_KEYWORDS):
            return True
        idx = low.find(target, idx + 1)
    return False


def detect_pii_in_text(text: str) -> dict[str, list[str]]:
    """從文字中偵測 PII，回傳各類別去重後的列表（按出現順序保留）。

    身分證與信用卡會額外用檢查碼過濾，降低 false positive。

    信用卡精準度（收斂誤報）：通過 Luhn 後，僅在「格式化（含分隔且 15/16 位）」
    或「附近有信用卡關鍵字」時才採計；裸數字串（流水號、座標、雜湊片段巧過 Luhn）
    不採計，避免報告灌入大量假卡號（已於靶機報告觀察到此問題）。
    """
    text = text or ""
    cc_valid = [
        m for m in dict.fromkeys(CREDIT_CARD_PATTERN.findall(text)) if is_valid_luhn(m)
    ]
    credit_card = [
        m for m in cc_valid if _is_formatted_card(m) or _card_has_context(text, m)
    ]
    return {
        "email": contacts.find_emails(text),
        "mobile": contacts.find_mobiles(text),
        "national_id": [
            m for m in dict.fromkeys(TW_NATIONAL_ID_PATTERN.findall(text))
            if is_valid_tw_national_id(m)
        ],
        "credit_card": credit_card,
    }


def is_admin_path(url: str) -> bool:
    """判斷 URL 路徑是否屬於不對外索引的後台/管理頁面。

    用於跳過 SEO/AEO/GEO 評分；安全性檢查仍照常執行，因為後台登入頁的
    CSRF 防護與安全頭部反而更重要。
    """
    path = (urlparse(url).path or "").lower()
    if any(segment in _AUTH_PATH_SEGMENTS for segment in path.split("/")):
        return True
    return any(path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + ".")
               for prefix in ADMIN_PATH_PREFIXES)


def is_binary_resource(url: str) -> bool:
    """判斷 URL 是否指向非 HTML 的二進位/媒體檔案。

    這類資源沒有 HTML 內容，SEO/AEO/GEO 分析（例如 H1、meta description、
    JSON-LD 建議）對其完全沒有意義；僅做安全頭部檢查即可。
    """
    path = (urlparse(url).path or "").lower()
    return path.endswith(NON_HTML_EXTENSIONS)


def detect_faq_structure(html: str, dl_count: int) -> bool:
    """偵測頁面是否具備可被解讀為 FAQ 的結構訊號。

    只有出現明確的 FAQ 結構（<dl>、<details>、faq/accordion class 等）時，
    才適合建議補 FAQPage Schema；否則先建內容比較合理。
    """
    if dl_count >= 1:
        return True
    if not html:
        return False
    if re.search(r"<details\b", html, re.IGNORECASE):
        return True
    if re.search(
        r'(?:class|id)=["\'][^"\']*\b(?:faq|qa-list|q-and-a|accordion|frequently-asked)\b',
        html,
        re.IGNORECASE,
    ):
        return True
    return False


@dataclass
class PageAnalysisInput:
    url: str
    final_url: str
    title: str
    html: str
    headers: dict[str, str]
    element_boxes: dict[str, dict]
    html_only: str = ""
    # 行動版量測。空 dict 代表**未量測**（量測失敗或舊資料），不是「沒問題」。
    layout_metrics: dict | None = None
    # 互動可用性訊號（觸控目標過小、表單欄位缺標籤）。空 dict＝未量測或無問題。
    ux_signals: dict | None = None
    # 本頁 JavaScript 執行期錯誤訊息（首行、去重）。空 list＝無錯誤或未量測。
    js_errors: list | None = None
    # axe-core 無障礙檢查結果（accessibility.py）。空 dict＝沒跑；含 "error"＝跑失敗。
    a11y: dict | None = None


def _is_large_image(attributes: dict[str, str]) -> bool:
    """width／height 屬性都 ≥ 120px 才算內容大小的圖；沒標尺寸的不猜。"""
    try:
        width, height = int(attributes.get("width", "0")), int(attributes.get("height", "0"))
    except ValueError:
        return False
    return width >= 120 and height >= 120


class HtmlSignalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_description = ""
        self.canonical = ""
        self.hreflang_count = 0
        self.h1_count = 0
        self.heading_levels: list[int] = []
        self.image_count = 0
        self.image_without_alt = 0
        # alt="" 是裝飾圖的正確寫法；只有「較大的圖片」alt 為空才值得提醒（可能是內容圖）
        self.image_empty_alt_large = 0
        self.form_count = 0
        self.form_without_csrf = 0
        self.json_ld_blocks: list[str] = []
        self.dl_count = 0
        self.og_tags: set[str] = set()
        self.current_script_type = ""
        self.current_script_parts: list[str] = []
        self.in_form = False
        self.form_has_csrf = False
        self.semantic_landmarks: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): value or "" for name, value in attrs}
        normalized_tag = tag.lower()

        if normalized_tag == "meta" and attributes.get("name", "").lower() == "description":
            self.meta_description = attributes.get("content", "")
        elif normalized_tag == "meta":
            og_key = (attributes.get("property", "") or attributes.get("name", "")).lower()
            if og_key in OG_META_KEYS and attributes.get("content", "").strip():
                self.og_tags.add(og_key)
        elif normalized_tag == "link":
            rel = attributes.get("rel", "").lower()
            if rel == "canonical":
                self.canonical = attributes.get("href", "")
            if rel == "alternate" and attributes.get("hreflang"):
                self.hreflang_count += 1
        elif normalized_tag == "h1":
            self.h1_count += 1
            self.heading_levels.append(1)
        elif normalized_tag in {"h2", "h3", "h4", "h5", "h6"}:
            self.heading_levels.append(int(normalized_tag[1]))
        elif normalized_tag == "img":
            self.image_count += 1
            if "alt" not in attributes:
                self.image_without_alt += 1
            elif not attributes["alt"].strip() and _is_large_image(attributes):
                self.image_empty_alt_large += 1
        elif normalized_tag == "form":
            self.form_count += 1
            self.in_form = True
            self.form_has_csrf = False
        elif normalized_tag == "input" and self.in_form:
            name = attributes.get("name", "").lower()
            if "csrf" in name or attributes.get("type", "").lower() == "hidden" and "token" in name:
                self.form_has_csrf = True
        elif normalized_tag == "script":
            self.current_script_type = attributes.get("type", "").lower()
            self.current_script_parts = []
        elif normalized_tag == "dl":
            self.dl_count += 1

        if normalized_tag in SEMANTIC_LANDMARK_TAGS:
            self.semantic_landmarks.add(normalized_tag)

    def handle_data(self, data: str) -> None:
        if self.current_script_type == "application/ld+json":
            self.current_script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "script" and self.current_script_type == "application/ld+json":
            self.json_ld_blocks.append("".join(self.current_script_parts))
            self.current_script_type = ""
            self.current_script_parts = []
        elif normalized_tag == "form" and self.in_form:
            if not self.form_has_csrf:
                self.form_without_csrf += 1
            self.in_form = False
            self.form_has_csrf = False


def build_ai_handoff_prompt(
    *,
    category: str,
    severity: str,
    description: str,
    remediation: str,
    evidence: str,
) -> str:
    return (
        "我網站有以下問題，請協助我分析並提供修復方向：\n"
        f"- 問題類型：{category}\n"
        f"- 嚴重度：{severity}\n"
        f"- 問題描述：{description}\n"
        "- 相關證據：\n"
        f"{evidence}\n"
        f"- 修補建議方向：{remediation}\n\n"
        "請依此資訊提供具體修改方向、檢查步驟與注意事項；不要輸出完整修復程式碼。"
    )


def _normalize_rule_token(value: str) -> str:
    token = re.sub(r"[^0-9A-Za-z]+", "_", value or "").strip("_").upper()
    return token[:80] or "GENERAL"


# security/ 子套件的 7 個 scanner 都沒有傳 priority_score，留 None 會讓
# PostgreSQL 的 DESC NULLS FIRST 把這些 finding 排到報告最前面（SQLite 的 DESC
# 是 NULLS LAST，所以本機開發複現不出來）。沒有更細的排序依據時就以 severity
# 當預設；呼叫端仍可傳明確值覆寫。
_SEVERITY_DEFAULT_PRIORITY = {
    "critical": 90.0,
    "high": 75.0,
    "medium": 50.0,
    "low": 25.0,
    "info": 10.0,
}


def _default_rule_id(category: str, title: str) -> str:
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10].upper()
    return f"{_normalize_rule_token(str(category))}_{_normalize_rule_token(title)}_{digest}"


def _default_evidence_json(
    *,
    evidence: str,
    evidence_type: str,
    evidence_source: str,
    selector: str,
    bounding_box: dict | None,
) -> dict:
    payload = {
        "type": evidence_type or "text",
        "source": evidence_source,
        "excerpt": (evidence or "")[:1000],
    }
    if selector:
        payload["selector"] = selector
    if bounding_box:
        payload["bounding_box"] = bounding_box
    return payload


def make_finding(
    *,
    category: str,
    severity: str,
    title: str,
    description: str,
    remediation: str,
    evidence: str = "",
    selector: str = "",
    bounding_box: dict | None = None,
    priority_score: float | None = None,
    impact_area: str = "",
    confidence: float = 1.0,
    rule_id: str = "",
    evidence_type: str = "",
    evidence_json: dict | None = None,
    evidence_source: str = "",
) -> dict:
    resolved_rule_id = rule_id or _default_rule_id(str(category), title)
    resolved_priority_score = (
        priority_score
        if priority_score is not None
        else _SEVERITY_DEFAULT_PRIORITY.get(str(severity), 10.0)
    )
    resolved_evidence_type = evidence_type or "text"
    resolved_evidence_source = evidence_source or "rule_engine"
    resolved_evidence_json = evidence_json or _default_evidence_json(
        evidence=evidence,
        evidence_type=resolved_evidence_type,
        evidence_source=resolved_evidence_source,
        selector=selector,
        bounding_box=bounding_box,
    )
    return {
        "category": category,
        "severity": severity,
        "rule_id": resolved_rule_id,
        "title": title,
        "description": description,
        "remediation": remediation,
        "evidence": evidence[:4000],
        "evidence_type": resolved_evidence_type,
        "evidence_json": resolved_evidence_json,
        "evidence_source": resolved_evidence_source,
        "ai_explanation": "",
        "ai_remediation": "",
        "llm_model": "",
        "llm_generated_at": None,
        "selector": selector,
        "bounding_box": bounding_box,
        "priority_score": resolved_priority_score,
        "impact_area": impact_area,
        "confidence": confidence,
        "ai_handoff_prompt": build_ai_handoff_prompt(
            category=category,
            severity=severity,
            description=description,
            remediation=remediation,
            evidence=evidence[:2000],
        ),
    }


def parse_html_signals(html: str) -> HtmlSignalParser:
    parser = HtmlSignalParser()
    parser.feed(html or "")
    return parser


def analyze_page(page_input: PageAnalysisInput, categories: set[str] | None = None) -> list[dict]:
    """單頁四維＋資安分析。categories 指定時只跑勾選維度（None＝全部）。

    維度對應：seo/aeo→analyze_seo/aeo、geo→analyze_geo(_fast)＋站台訊號、
    security→analyze_security/analyze_data_exposure（管理頁與二進位資源的
    安全檢查也屬 security）、ux→analyze_ux（行動版版面）。
    """
    wanted = set(categories) if categories is not None else None

    def runs(category: str) -> bool:
        return wanted is None or category in wanted

    parser = parse_html_signals(page_input.html)
    findings: list[dict] = []

    target_url = page_input.final_url or page_input.url

    # 二進位/媒體資源（.apk、.pdf 等）沒有頁面內容，不做 SEO/AEO/GEO 分析；
    # 安全頭部仍檢查，因為這些檔案的下載仍需 HSTS / X-Content-Type-Options 等保護。
    if is_binary_resource(target_url):
        if runs("security"):
            findings.extend(analyze_security(page_input, parser))
        return findings

    # 管理後台/登入頁不對外索引，SEO/AEO/GEO 評分對其無意義；
    # 但 SECURITY 檢查（CSRF token、安全頭部）對後台反而更關鍵，必須保留。
    # PII 偵測也保留：後台頁面意外外洩個資反而更嚴重。
    if is_admin_path(target_url):
        if runs("security"):
            findings.extend(analyze_security(page_input, parser))
            findings.extend(analyze_data_exposure(page_input))
        return findings

    if runs("seo"):
        findings.extend(analyze_seo(page_input, parser))
    if runs("aeo"):
        findings.extend(analyze_aeo(page_input, parser))
    if runs("geo"):
        # 內容結構（geo_structure.py 匯入 make_finding，放在函式內避免循環匯入）
        from apps.scans.geo_structure import structure_findings

        findings.extend(analyze_geo(page_input, parser))
        findings.extend(analyze_geo_fast(page_input, parser))
        findings.extend(structure_findings(page_input.url, page_input.html))
    if runs("security"):
        findings.extend(analyze_security(page_input, parser))
        findings.extend(analyze_data_exposure(page_input))
    if runs("ux"):
        findings.extend(analyze_ux(page_input))
    return findings


# 手機上超出這個寬度就會出現水平捲軸。1px 以內是次像素捨入，crawler 已扣掉。
_MOBILE_OVERFLOW_TOLERANCE_PX = 4


def analyze_ux(page_input: PageAnalysisInput) -> list[dict]:
    """使用者體驗（UX）可用性檢查。

    判準都是客觀量測、不需要人為評分：
    - 行動版水平溢出（破版）：`layout_metrics`
    - 版面位移（CLS）與位移的元素：`layout_metrics.layout_shift`（桌面視窗、載入與捲動期間）
    - 觸控目標過小、表單欄位缺可及標籤：`ux_signals`（行動版視窗量測）
    - JavaScript 執行期錯誤：`js_errors`（頁面實際拋出的未捕捉例外）
    - WCAG 自動化檢查：`a11y`（axe-core，勾 UX 才跑）

    各來源為空一律代表「未量測或無問題」，不會硬湊 finding。
    """
    findings: list[dict] = []
    findings.extend(_ux_mobile_overflow(page_input))
    findings.extend(_ux_layout_shift(page_input))
    findings.extend(_ux_tap_targets(page_input))
    findings.extend(_ux_unlabeled_fields(page_input))
    findings.extend(_ux_js_errors(page_input))
    findings.extend(_ux_axe(page_input))
    return findings


def _mobile_annotations(offenders: list[dict], label) -> dict | None:
    """行動版截圖上的逐元素標註（爬蟲量到的文件座標）；沒有座標的舊資料回 None。

    觸控目標等問題是在 375px 寬量的，要框在行動版截圖上、而且框住元素本身，
    不能退回整個 Header 或區塊（2026-10-06 使用者要求）。
    """
    boxes = []
    for offender in offenders:
        box = offender.get("box") or {}
        if box.get("width") and box.get("height"):
            boxes.append({
                "x": box.get("x", 0), "y": box.get("y", 0),
                "width": box["width"], "height": box["height"],
                "label": label(offender),
            })
    return {"viewport": "mobile", "boxes": boxes} if boxes else None


def _ux_mobile_overflow(page_input: PageAnalysisInput) -> list[dict]:
    """行動版水平溢出（破版）。`layout_metrics` 為空代表沒量到，不能當成通過。"""
    metrics = page_input.layout_metrics or {}
    if not metrics:
        return []

    overflow = int(metrics.get("overflow_px") or 0)
    if overflow <= _MOBILE_OVERFLOW_TOLERANCE_PX:
        return []

    offenders = metrics.get("offenders") or []
    worst = offenders[0] if offenders else {}
    viewport = metrics.get("viewport_width") or 375
    detail = (
        "、".join(f"{o.get('selector')}（超出 {o.get('overflow_px')}px）" for o in offenders[:3])
        or "未能定位到具體元素"
    )
    return [
        make_finding(
            category=Finding.Category.UX,
            # 超出越多、破版越明顯。半個螢幕寬以上已經是嚴重可用性問題。
            severity=(
                Finding.Severity.MEDIUM if overflow >= viewport * 0.5 else Finding.Severity.LOW
            ),
            title="行動版出現水平捲動（破版）",
            description=(
                f"在 {viewport}px 寬的行動版視窗下，頁面內容寬度為 "
                f"{metrics.get('scroll_width')}px，超出 {overflow}px，"
                "會產生左右捲動。使用者需要橫向滑動才能看完內容，"
                "在手機上是明顯的可用性問題。"
            ),
            remediation=(
                "找出超出視窗的元素，改用 max-width:100% 或 width:auto，"
                "並檢查是否有固定寬度、負 margin 或未換行的長字串（可用 "
                "overflow-wrap:anywhere 處理）。"
            ),
            evidence=f"viewport={viewport}px, overflow={overflow}px, 元素：{detail}",
            selector=worst.get("selector", ""),
            impact_area="responsive",
            priority_score=55 if overflow >= viewport * 0.5 else 42,
            evidence_type="layout_metrics",
            evidence_json={
                "viewport_width": viewport,
                "scroll_width": metrics.get("scroll_width"),
                "overflow_px": overflow,
                "offenders": offenders[:5],
                "annotations": _mobile_annotations(
                    offenders[:3], lambda o: f"超出 {o.get('overflow_px')}px"
                ),
            },
        )
    ]


# Google CLS 門檻：≤0.1 良好、≤0.25 需改善、>0.25 不佳
_CLS_NEEDS_IMPROVEMENT = 0.1
_CLS_POOR = 0.25


def _ux_layout_shift(page_input: PageAnalysisInput) -> list[dict]:
    """版面位移（CLS）過高，並列出位移的元素。沒量到（空 dict）不算通過、也不列問題。"""
    shift = (page_input.layout_metrics or {}).get("layout_shift") or {}
    cls = shift.get("cls") or 0
    if cls <= _CLS_NEEDS_IMPROVEMENT:
        return []
    poor = cls > _CLS_POOR
    elements = shift.get("elements") or []
    detail = "、".join(
        f"{e.get('selector')}（位移 {e.get('moved_px')}px）" for e in elements[:3]
    ) or "瀏覽器沒有回報位移的元素"
    unsized = shift.get("unsized_media") or 0
    cause = (
        f"這頁有 {unsized} 個圖片／影片／iframe 沒有同時標 width 與 height 屬性，"
        "若 CSS 也沒有預留尺寸，載入後就會把下方內容往下推。"
        if unsized else ""
    )
    return [
        make_finding(
            category=Finding.Category.UX,
            severity=Finding.Severity.MEDIUM if poor else Finding.Severity.LOW,
            rule_id="ux-layout-shift",
            title="頁面載入時版面跳動（CLS 偏高）",
            description=(
                f"Argus 爬取時量到這頁的累計版面位移（CLS）為 {cls}"
                "（Google 標準：0.1 以下良好、0.25 以上不佳），"
                f"屬於「{'不佳' if poor else '需改善'}」。"
                "內容在讀者閱讀或準備點擊時突然移動，容易點錯、找不到剛才讀到的位置。"
                + cause
            ),
            remediation=(
                "為圖片、影片、iframe 與廣告版位預留空間（標 width／height 或 CSS aspect-ratio），"
                "不要在既有內容上方插入橫幅或動態內容，"
                "網頁字型使用 font-display: optional 或調整備用字型尺寸。"
                "下列是被推動的元素，原因通常在它上方較晚載入的內容。"
            ),
            evidence=f"CLS={cls}（桌面視窗、單次量測）；位移的元素：{detail}",
            selector=(elements[0].get("selector", "") if elements else ""),
            impact_area="stability",
            priority_score=50 if poor else 38,
            evidence_type="layout_metrics",
            evidence_json={
                "cls": cls,
                "shifts": shift.get("shifts"),
                "elements": elements[:5],
                "unsized_media": unsized,
            },
        )
    ]


def _ux_tap_targets(page_input: PageAnalysisInput) -> list[dict]:
    """觸控目標過小：手機上手指不易點準的可點元素。"""
    signals = page_input.ux_signals or {}
    offenders = signals.get("small_tap_targets") or []
    if not offenders:
        return []

    worst = offenders[0]
    labels = "、".join(
        f"{o.get('label') or o.get('selector')}"
        f"（{o.get('width_px')}×{o.get('height_px')}px）"
        for o in offenders[:3]
    )
    # 目標數量多代表整頁互動密度都偏小，比零星一兩個更值得處理。
    severity = Finding.Severity.MEDIUM if len(offenders) >= 5 else Finding.Severity.LOW
    # 標準引用要精確（2026-10-06 審查）：40px 是 Argus 的易用性建議；WCAG 2.2 的 AA 門檻
    # 是 2.5.8 的 24×24（相鄰間距足夠可豁免），44×44 是 AAA 的 2.5.5。
    under_aa = sum(
        1 for o in offenders
        if min(o.get("width_px") or 0, o.get("height_px") or 0) < 24
    )
    wcag_note = (
        f"其中 {under_aa} 個小於 24×24px，可能不符合 WCAG 2.2 AA（2.5.8），"
        "若與相鄰目標間距足夠則可豁免，需人工確認。"
        if under_aa
        else "都在 WCAG 2.2 AA（2.5.8）24×24px 的最低要求以上，屬於易用性建議，不是合規問題。"
    )
    return [
        make_finding(
            category=Finding.Category.UX,
            severity=severity,
            title="觸控目標過小",
            description=(
                f"頁面有 {len(offenders)} 個可點元素（連結、按鈕或表單控制項）在 "
                "行動版視窗下的寬或高小於 40px（Argus 易用性建議），過小會讓使用者誤點或點不到。"
                f"{wcag_note}"
                "WCAG 2.2 AAA（2.5.5）的建議是 44×44px。"
            ),
            remediation=(
                "把可點元素的可點區域放大到至少 44×44px，可用 padding、min-width／"
                "min-height 或增加行高；相鄰的小連結之間保留足夠間距。"
            ),
            evidence=f"過小的觸控目標：{labels}",
            selector=worst.get("selector", ""),
            impact_area="mobile_usability",
            priority_score=48 if severity == Finding.Severity.MEDIUM else 38,
            evidence_type="ux_signals",
            evidence_json={
                "small_tap_targets": offenders[:8],
                "annotations": _mobile_annotations(
                    offenders[:8], lambda o: f"{o.get('width_px')}×{o.get('height_px')}px"
                ),
            },
        )
    ]


def _ux_unlabeled_fields(page_input: PageAnalysisInput) -> list[dict]:
    """表單欄位缺少可及標籤：螢幕報讀者與部分使用者無從得知欄位用途。"""
    signals = page_input.ux_signals or {}
    offenders = signals.get("unlabeled_fields") or []
    if not offenders:
        return []

    worst = offenders[0]
    labels = "、".join(
        f"{o.get('name') or o.get('type') or o.get('selector')}" for o in offenders[:4]
    )
    return [
        make_finding(
            category=Finding.Category.UX,
            severity=Finding.Severity.MEDIUM,
            title="表單欄位缺少可及標籤",
            description=(
                f"頁面有 {len(offenders)} 個表單欄位沒有可及名稱（沒有對應的 "
                "<label>、aria-label／aria-labelledby，也沒有 title 或 placeholder）。"
                "螢幕報讀者會唸不出欄位用途，語音輸入與自動填入也難以對應。"
            ),
            remediation=(
                "為每個輸入欄位加上 <label for>（或用 <label> 包住欄位），"
                "或補上 aria-label；placeholder 不能取代 label，因為輸入後就消失。"
            ),
            evidence=f"缺標籤的欄位：{labels}",
            selector=worst.get("selector", ""),
            impact_area="accessibility",
            priority_score=46,
            evidence_type="ux_signals",
            evidence_json={
                "unlabeled_fields": offenders[:8],
                "annotations": _mobile_annotations(
                    offenders[:8], lambda o: o.get("name") or o.get("type") or "欄位"
                ),
            },
        )
    ]


# axe-core 的 impact → 嚴重度。critical／serious 會直接擋住部分使用者，moderate／minor 是障礙
_AXE_SEVERITY = {
    "critical": Finding.Severity.HIGH,
    "serious": Finding.Severity.MEDIUM,
    "moderate": Finding.Severity.LOW,
    "minor": Finding.Severity.LOW,
}
_AXE_PRIORITY = {"critical": 60, "serious": 45, "moderate": 30, "minor": 20}
# 常見規則的中文標題與修法（其餘以 axe 的英文說明加官方連結呈現）
_AXE_ZH = {
    "image-alt": ("圖片缺少替代文字", "為有意義的圖片加上描述內容的 alt；純裝飾圖片用 alt=\"\"。"),
    "button-name": ("按鈕沒有可辨識的名稱", "按鈕內放文字，或用 aria-label 說明按下去會做什麼。"),
    "link-name": ("連結沒有可辨識的文字", "連結內放文字；只有圖示時補 aria-label 或圖片 alt。"),
    "color-contrast": (
        "文字與背景對比不足",
        "一般文字對比至少 4.5:1、大字 3:1；調深文字或調淺背景後再用對比檢查工具確認。",
    ),
    "html-has-lang": ("網頁沒有宣告語言", "在 <html> 加上 lang，例如 lang=\"zh-Hant\"。"),
    "html-lang-valid": ("網頁語言代碼無效", "lang 使用有效的語言代碼，例如 zh-Hant、en。"),
    "document-title": ("網頁沒有標題", "在 <head> 加上描述這一頁內容的 <title>。"),
    "frame-title": ("內嵌框架沒有標題", "為 <iframe> 加上說明內容的 title。"),
    "input-image-alt": ("圖片按鈕缺少替代文字", "為 <input type=\"image\"> 加上 alt。"),
    "aria-required-attr": ("ARIA 角色缺少必要屬性", "依該 role 的規範補上必要的 aria-* 屬性。"),
    "aria-valid-attr-value": (
        "ARIA 屬性值無效", "修正 aria-* 屬性值，指向存在的元素或使用允許的值。"
    ),
    "aria-hidden-focus": (
        "被隱藏的區塊內仍有可聚焦元素",
        "aria-hidden=\"true\" 的區塊內不可有可用 Tab 聚焦的元素，或移除 aria-hidden。",
    ),
    "list": ("清單結構不正確", "<ul>／<ol> 底下只放 <li>（或 script／template）。"),
    "listitem": ("清單項目不在清單內", "把 <li> 放在 <ul> 或 <ol> 裡。"),
    "duplicate-id-aria": ("被引用的 id 重複", "讓 aria-labelledby 等引用的 id 在頁面上唯一。"),
    "meta-viewport": (
        "禁止使用者縮放頁面", "移除 viewport 的 user-scalable=no 與過小的 maximum-scale。"
    ),
    "nested-interactive": ("互動元素巢狀", "不要把按鈕或連結放進另一個按鈕或連結裡。"),
    "role-img-alt": ("role=img 的元素缺少替代文字", "加上 aria-label 或 aria-labelledby。"),
    "svg-img-alt": (
        "SVG 圖片缺少替代文字", "為 role=\"img\" 的 <svg> 加上 <title> 或 aria-label。"
    ),
}


def _ux_axe(page_input: PageAnalysisInput) -> list[dict]:
    """axe-core（WCAG 2.x A／AA 自動化檢查）的違規，每條規則一項。

    自動化檢查只涵蓋部分 WCAG 準則：沒有違規不等於符合 WCAG，報告不得如此宣稱。
    """
    result = page_input.a11y or {}
    findings = []
    for violation in result.get("violations") or []:
        rule = str(violation.get("id") or "")
        if not rule:
            continue
        impact = violation.get("impact") or "moderate"
        nodes = violation.get("nodes") or []
        count = int(violation.get("count") or len(nodes))
        zh_title, zh_fix = _AXE_ZH.get(rule, ("", ""))
        help_text = str(violation.get("help") or rule)
        wcag = "、".join(violation.get("tags") or []) or "WCAG"
        first_box = next((n.get("box") for n in nodes if n.get("box")), None)
        evidence_lines = [
            f"{n.get('target', '')}｜{n.get('html', '')}" for n in nodes
        ]
        findings.append(
            make_finding(
                category=Finding.Category.UX,
                severity=_AXE_SEVERITY.get(impact, Finding.Severity.LOW),
                rule_id=f"axe-{rule}",
                title=zh_title or f"無障礙：{help_text}",
                description=(
                    f"axe-core 自動化檢查在這一頁找到 {count} 個元素不符合規則「{help_text}」"
                    f"（{wcag}）。{violation.get('description') or ''}"
                ),
                remediation=(
                    (zh_fix + " " if zh_fix else "")
                    + f"規則說明與修正範例：{violation.get('help_url') or 'https://dequeuniversity.com/rules/axe/'}"
                ),
                evidence="\n".join(evidence_lines)[:2000],
                selector=(nodes[0].get("target", "") if nodes else ""),
                bounding_box=first_box,
                impact_area="accessibility",
                priority_score=_AXE_PRIORITY.get(impact, 25),
                evidence_type="axe",
                evidence_source=f"axe-core {result.get('version', '')}".strip(),
                evidence_json={
                    "axe_rule": rule,
                    "impact": impact,
                    "wcag": violation.get("tags") or [],
                    "help_url": violation.get("help_url") or "",
                    "count": count,
                    "nodes": nodes,
                },
            )
        )
    return findings


def _ux_js_errors(page_input: PageAnalysisInput) -> list[dict]:
    """JavaScript 執行期錯誤：未捕捉的例外常導致互動失效。"""
    errors = [str(e).strip() for e in (page_input.js_errors or []) if str(e).strip()]
    if not errors:
        return []

    joined = "\n".join(errors[:8])
    return [
        make_finding(
            category=Finding.Category.UX,
            severity=Finding.Severity.MEDIUM,
            title="頁面出現 JavaScript 執行期錯誤",
            description=(
                f"載入這個頁面時，瀏覽器主控台出現 {len(errors)} 則未捕捉的 "
                "JavaScript 錯誤。這類錯誤會中斷腳本執行，常導致按鈕沒反應、"
                "內容載不出來或表單無法送出。"
            ),
            remediation=(
                "在瀏覽器開發者工具的 Console 重現這些錯誤，從第一則往下修："
                "常見原因是存取了 null／undefined、缺少資源或第三方腳本失敗；"
                "並為關鍵流程加上錯誤處理，避免單一例外讓整頁互動失效。"
            ),
            evidence=joined[:_MAX_JS_ERROR_EVIDENCE_CHARS],
            impact_area="reliability",
            priority_score=50,
            evidence_type="js_errors",
            evidence_json={"errors": errors[:8]},
        )
    ]


_MAX_JS_ERROR_EVIDENCE_CHARS = 800


def _seo_title_length(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> dict | None:
    """Meta title 過短或過長（10–65 字元以外）。"""
    title_length = len((page_input.title or "").strip())
    if not (title_length < 10 or title_length > 65):
        return None
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.LOW,
        title="Meta title 長度不理想",
        description="頁面標題過短或過長，可能降低搜尋結果可讀性與點擊率。",
        remediation="將 title 調整為清楚描述頁面主題且約 10 到 65 字元。",
        evidence=f"title={page_input.title!r}, length={title_length}",
        selector="title",
        impact_area="metadata",
        priority_score=40,
    )


def _seo_meta_description(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> dict | None:
    """Meta description 缺失、過短或過長（50–160 字元以外）。"""
    description_length = len(parser.meta_description.strip())
    if not (description_length < 50 or description_length > 160):
        return None
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.LOW,
        title="Meta description 缺失或長度不理想",
        description="Meta description 缺失、過短或過長，會影響搜尋摘要品質。",
        remediation="補上清楚摘要頁面價值的 description，建議約 50 到 160 字元。",
        # 附上實際內容開頭，讀者才能自行核對（例如 CMS 把整篇文章塞進 description）
        evidence=(
            f"description_length={description_length}"
            + (
                f", 開頭：「{parser.meta_description.strip()[:60]}」"
                if description_length
                else "（頁面沒有 meta description）"
            )
        ),
        selector='meta[name="description"]',
        impact_area="metadata",
        priority_score=38,
    )


def _seo_h1_count(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> dict | None:
    """H1 不是恰好一個。

    HTML 與 Google 都不要求「只能有一個 H1」：沒有 H1 是低風險（頁面主題不明確），
    多個 H1 只是建議（2026-10-06 審查：原本判中風險，高估了影響）。
    """
    if parser.h1_count == 1:
        return None
    missing = parser.h1_count == 0
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.LOW if missing else Finding.Severity.INFO,
        title="H1 標題數量不正確",
        description=(
            "頁面沒有 H1，搜尋引擎與使用者較難一眼看出頁面主題。"
            if missing
            else f"頁面有 {parser.h1_count} 個 H1。這不違反 HTML 規範，Google 也能處理，"
            "但一個明確的主標題通常更容易理解。"
        ),
        remediation="保留一個代表頁面主題的 H1，其他段落標題改用 H2-H6。",
        evidence=f"h1_count={parser.h1_count}",
        selector="h1",
        bounding_box=page_input.element_boxes.get("h1"),
        impact_area="heading",
        priority_score=42 if missing else 20,
    )


def _seo_image_alt(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> dict | None:
    """有圖片缺少 alt 屬性；或較大的圖片 alt 為空（可能是內容圖，僅提醒）。"""
    if parser.image_without_alt:
        title = "圖片缺少 alt 屬性"
        severity = Finding.Severity.LOW
        description = "圖片缺少替代文字會降低無障礙體驗，也讓搜尋引擎難以理解圖片內容。"
    elif parser.image_empty_alt_large >= 3:
        # alt="" 合法（裝飾圖），但大量大尺寸圖片都留空，多半是內容圖漏寫描述（2026-10-06 實測）
        title = "多張大圖的 alt 為空"
        severity = Finding.Severity.INFO
        description = (
            "alt=\"\" 代表裝飾圖、螢幕報讀器會略過。這些圖片尺寸較大，若是照片、課程或成員等"
            "內容圖片，應寫出描述。"
        )
    else:
        return None
    return make_finding(
        category=Finding.Category.SEO,
        severity=severity,
        title=title,
        description=description,
        remediation="為有語意的圖片補上精準 alt，裝飾性圖片可使用空 alt。",
        evidence=(
            f"image_count={parser.image_count}, "
            f"image_without_alt={parser.image_without_alt}, "
            f"large_image_empty_alt={parser.image_empty_alt_large}"
        ),
        selector="img:not([alt])",
        bounding_box=page_input.element_boxes.get("img:not([alt])"),
        impact_area="accessibility",
        priority_score=25,
    )


def _seo_canonical(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> dict | None:
    """缺少 canonical URL（info）。"""
    if parser.canonical:
        return None
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.INFO,
        title="缺少 canonical URL",
        description="缺少 canonical 可能讓重複內容頁面分散搜尋權重。",
        remediation="為主要內容頁加入 canonical，指向該內容的標準 URL。",
        evidence="canonical_missing=true",
        selector='link[rel="canonical"]',
        impact_area="metadata",
        priority_score=15,
    )


def _seo_open_graph(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> dict | None:
    """缺少 Open Graph 分享標籤。"""
    missing_og = sorted(OG_META_KEYS - parser.og_tags)
    if not missing_og:
        return None
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.LOW,
        title="缺少 Open Graph 社交分享標籤",
        description=(
            "頁面缺少部分 Open Graph 標籤，連結被分享到社群媒體或通訊軟體時，"
            "預覽卡片可能沒有標題、描述或圖片，降低點擊意願。"
        ),
        remediation=(
            "為頁面補齊 og:title、og:description、og:image 與 og:url 標籤，"
            "內容與頁面主題一致，圖片建議 1200×630 以上。"
        ),
        evidence=f"missing_og_tags={', '.join(missing_og)}",
        selector='meta[property^="og:"]',
        impact_area="metadata",
        priority_score=30,
    )


def _seo_structured_data(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> dict | None:
    """已有的結構化資料缺少 Google 複合式搜尋結果的必填欄位（seo/structured_data.py）。"""
    if not parser.json_ld_blocks:
        return None
    result = validate_structured_data(parser.json_ld_blocks)
    issues = result["issues"]
    if not issues:
        return None
    lines = [f"{i['type']}「{i['item']}」缺少：{'、'.join(i['missing'])}" for i in issues]
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.LOW,
        rule_id="seo-structured-data-required",
        title="結構化資料缺少 Google 複合式搜尋結果的必填欄位",
        description=(
            "頁面的結構化資料缺少 Google 列為必填的欄位，這些項目不符合複合式搜尋結果"
            "（例如價格、評分星等、活動日期）的顯示資格，只會以一般搜尋結果呈現。"
        ),
        remediation=(
            "依下方清單補上欄位，內容要與頁面上看得到的資訊一致，再用 Google 複合式搜尋結果測試"
            "（https://search.google.com/test/rich-results）確認。"
            "若沒有打算爭取複合式搜尋結果，也可以移除不完整的標記。"
        ),
        evidence=f"{page_input.url}\n" + "\n".join(lines),
        selector='script[type="application/ld+json"]',
        impact_area="structured_data",
        evidence_json={"url": page_input.url, "issues": issues},
        priority_score=32,
    )


def _seo_self_serving_reviews(
    page_input: PageAnalysisInput, parser: HtmlSignalParser
) -> dict | None:
    """商家或組織標記了自己的評分：Google 不會顯示星等。"""
    if not parser.json_ld_blocks:
        return None
    names = validate_structured_data(parser.json_ld_blocks)["self_serving"]
    if not names:
        return None
    return make_finding(
        category=Finding.Category.SEO,
        severity=Finding.Severity.INFO,
        rule_id="seo-structured-data-self-serving-reviews",
        title="商家自己的評分標記不會顯示成搜尋星等",
        description=(
            "LocalBusiness 或 Organization 標記裡含有評分或評論。網站自己控制的評論"
            "（含嵌入的第三方評論元件）屬於 Google 所說的自我評論，不會顯示星等。"
        ),
        remediation=(
            "不需要為了星等保留這段標記；評論內容可以照常顯示在頁面上。"
            "評價產品或服務時，改標在 Product 等類型上。"
        ),
        evidence=f"{page_input.url}\n標記評分的項目：" + "、".join(names),
        selector='script[type="application/ld+json"]',
        impact_area="structured_data",
        evidence_json={"url": page_input.url, "items": names},
    )


# 逐頁 SEO 檢查：每項獨立、順序即 finding 輸出順序；新增檢查寫成同樣簽名的函式加進來。
SEO_PAGE_CHECKS = (
    _seo_title_length,
    _seo_meta_description,
    _seo_h1_count,
    _seo_image_alt,
    _seo_canonical,
    _seo_open_graph,
    _seo_structured_data,
    _seo_self_serving_reviews,
)


def analyze_seo(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    findings: list[dict] = []
    for check in SEO_PAGE_CHECKS:
        finding = check(page_input, parser)
        if finding is not None:
            findings.append(finding)
    return findings


def analyze_aeo(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    """AEO 逐頁檢查：索引／摘要限制與結構化資料一致性（apps/scans/aeo/page_checks.py）。

    2026-09-28 起 AEO 改為「問題能否從網站內容中被找到、回答並追溯證據」：
    舊版只數問句、辨識 FAQ 區塊並建議補 FAQPage，無法證明答案存在，還會在只有資訊提示時
    讓 AEO 拿 100 分。能否回答問題的檢測是站台層級（aeo/evaluate.py），在所有頁面分析完
    之後由 tasks.stage_aeo_answerability 執行一次。
    """
    from apps.scans.aeo.page_checks import analyze_page_aeo

    return analyze_page_aeo(page_input, parser)


_BLOCK_SPLIT = re.compile(
    r"<(?:/?(?:p|div|li|dd|dt|td|th|blockquote|section|article|h[1-6])\b[^>]*|br\s*/?)>",
    re.IGNORECASE,
)


def _text_block_count(html: str) -> int:
    """可獨立引用的文字區塊數：以區塊標籤切段，計算去標籤後 40 字以上的段落。

    舊版只數 <p>，許多 CMS 以 <div>／<br> 排版，會出現「全文 9000 字卻只有 1 段」的誤判。
    """
    body = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    count = 0
    for chunk in _BLOCK_SPLIT.split(body):
        text = re.sub(r"\s+", "", re.sub(r"<[^>]+>", " ", chunk))
        if len(text) >= 40:
            count += 1
    return count


def analyze_geo(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    findings: list[dict] = []
    text = re.sub(r"<[^>]+>", " ", page_input.html or "")
    paragraph_count = _text_block_count(page_input.html or "")
    json_ld_text = "\n".join(parser.json_ld_blocks).lower()
    if not parser.json_ld_blocks:
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.LOW,
                title="可補充 JSON-LD 結構化資料",
                description=(
                    "頁面目前沒有 JSON-LD 結構化資料。若此頁承載品牌介紹、文章、"
                    "產品、服務或常見問答內容，補充 Schema.org 資料可提升 AI 系統"
                    "辨識頁面主題與實體的穩定性。"
                ),
                remediation=(
                    "依頁面類型考慮加入 Organization、WebSite、WebPage、Article、Product、"
                    "Service、FAQPage、HowTo 或 BreadcrumbList 等 Schema。"
                ),
                evidence="json_ld_blocks=0",
                selector='script[type="application/ld+json"]',
                impact_area="structured_data",
                priority_score=35,
            )
        )
    elif not any(
        kind in json_ld_text
        for kind in [
            "organization",
            "website",
            "webpage",
            "article",
            "product",
            "service",
            "faqpage",
            "howto",
            "breadcrumblist",
            "person",
            "localbusiness",
            "softwareapplication",
            "event",
        ]
    ):
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.INFO,
                title="JSON-LD 可補充更明確的實體類型",
                description=(
                    "頁面已有結構化資料，但目前未偵測到常見的頁面、組織、文章、產品、"
                    "服務、問答或導覽類型。這可能讓 AI 系統較難穩定判斷頁面用途。"
                ),
                remediation=(
                    "檢查 Schema 類型是否符合頁面目的，"
                    "必要時補齊更明確的 @type 與必要欄位。"
                ),
                evidence=json_ld_text[:1000],
                selector='script[type="application/ld+json"]',
                impact_area="structured_data",
                priority_score=25,
            )
        )
    if paragraph_count < 2 or len(text.strip()) < 300:
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.INFO,
                title="可引用文字區塊偏少",
                description=(
                    "頁面可獨立引用的文字段落偏少。若此頁希望被 AI 系統摘要或引用，"
                    "可補充更清楚的段落、定義、數據來源與具體事實。"
                ),
                remediation="增加清楚的小段落、定義、數據來源與具體事實，讓內容更容易被引用。",
                evidence=(
                    f"text_block_count={paragraph_count}（40 字以上的文字區塊）, "
                    f"text_length={len(text.strip())}"
                ),
                selector="main",
                bounding_box=page_input.element_boxes.get("main"),
                impact_area="chunkability",
                priority_score=20,
            )
        )
    return findings


def analyze_security(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    """頁面層級安全檢查：CSRF token（依各頁面自己的表單而定，本來就該逐頁各自判斷）。

    HTTPS / HSTS / CSP / X-Frame-Options / X-Content-Type-Options 屬伺服器設定，
    對整站幾乎一致，已搬到 analyze_security_site_level()（由 tasks.py 對整批
    crawled_pages 只呼叫一次），避免多頁站台把同一個問題重複扣好幾倍分數。
    """
    findings: list[dict] = []
    if parser.form_without_csrf:
        findings.append(
            make_finding(
                category=Finding.Category.SECURITY,
                severity=Finding.Severity.MEDIUM,
                title="表單可能缺少 CSRF token",
                description=(
                    "偵測到表單可能缺少 CSRF token。若此表單會改變登入狀態、個人資料、"
                    "訂單或後台設定，可能造成使用者在不知情下提交非預期請求。"
                ),
                remediation="確認會改變狀態的表單都具備 CSRF token 或等效防護。",
                evidence=(
                    f"form_count={parser.form_count}, "
                    f"form_without_csrf={parser.form_without_csrf}"
                ),
                selector="form",
                bounding_box=page_input.element_boxes.get("form"),
                impact_area="csrf",
                priority_score=64,
            )
        )
    return findings


def analyze_security_site_level(pages: list[dict]) -> list[dict]:
    """HTTPS / HSTS / CSP / X-Frame-Options / X-Content-Type-Options：只評估一次。

    取第一個有 headers 的頁面（比照 security/header_scanner.py::analyze_headers()
    的去重模式），因為這些是伺服器設定，逐頁重複檢查只會產生一堆內容相同的 finding，
    還會把 SECURITY 分數不成比例地往下拖。

    排除 blocked_reason 非空的頁面（例如跨網域導向、CF challenge、oversized）：
    這些頁面的 headers 可能來自第三方網域或錯誤頁，不能代表使用者自己網站的設定。
    """
    findings: list[dict] = []
    page = next(
        (p for p in pages if p.get("headers") and not p.get("blocked_reason")), None
    )
    if not page:
        return findings
    final_url = page.get("final_url") or page.get("url") or ""
    parsed = urlparse(final_url)
    headers = {key.lower(): value for key, value in (page.get("headers") or {}).items()}
    if parsed.scheme != "https":
        findings.append(
            make_finding(
                category=Finding.Category.SECURITY,
                severity=Finding.Severity.HIGH,
                title="頁面未使用 HTTPS",
                description="HTTP 連線可能被竊聽或竄改，會影響使用者安全與信任。",
                remediation="為網站啟用 HTTPS，並將 HTTP 流量重新導向 HTTPS。",
                evidence=f"scheme={parsed.scheme}",
                impact_area="transport_security",
                priority_score=90,
            )
        )
    required_headers = {
        "strict-transport-security": (Finding.Severity.MEDIUM, "缺少 HSTS"),
        # CSP 是縱深防禦：缺少它不代表已有可利用的漏洞，與其他縱深防禦標頭同列低風險
        # （2026-10-06 審查：中風險且排進優先清單第二，高估了實際風險）
        "content-security-policy": (Finding.Severity.LOW, "缺少 CSP"),
        "x-frame-options": (Finding.Severity.LOW, "缺少 X-Frame-Options"),
        "x-content-type-options": (Finding.Severity.INFO, "缺少 X-Content-Type-Options"),
    }
    # 防點擊劫持看的是「有沒有防護」：CSP frame-ancestors 與 X-Frame-Options 擇一即可
    has_frame_ancestors = "frame-ancestors" in headers.get("content-security-policy", "").lower()
    for header_name, (severity, title) in required_headers.items():
        if header_name == "x-frame-options" and has_frame_ancestors:
            continue
        if header_name not in headers:
            description = f"Response header 缺少 {header_name}，可能降低瀏覽器防護能力。"
            if header_name == "x-frame-options":
                description = (
                    "沒有 X-Frame-Options，CSP 也沒有 frame-ancestors，"
                    "頁面可以被其他網站嵌入，有點擊劫持（clickjacking）的風險。"
                )
            findings.append(
                make_finding(
                    category=Finding.Category.SECURITY,
                    severity=severity,
                    title=title,
                    description=description,
                    remediation=f"依網站需求設定合適的 {header_name} header。",
                    evidence=f"missing_header={header_name}",
                    impact_area="security_headers",
                    priority_score=55 if severity == Finding.Severity.MEDIUM else 25,
                )
            )
    return findings


def _collect_pii(raw_html: str) -> tuple[dict, dict, dict, list[str]]:
    """從頁面 HTML 萃取 PII。

    回傳 (合併後 pii, 註解中的 pii, 各類「只在註解」筆數, 開發者預留字串)。
    """
    # B1: 移除 SVG 整段 → 殘留的 SVG 子元素 → 殘留的 SVG 座標屬性；三層防護避免浮點誤判為卡號
    safe_html = _HTML_SVG_STRIP.sub(" ", raw_html)
    safe_html = _HTML_SVG_ELEMENTS.sub(" ", safe_html)
    safe_html = _HTML_PATH_ATTR.sub(" ", safe_html)
    # 輸入框 placeholder 是填寫範例（例：e.g.0911-222-333），不是任何人的資料（2026-10-06 實測）
    safe_html = contacts.PLACEHOLDER_ATTR.sub(" ", safe_html)
    pii_main = detect_pii_in_text(safe_html)

    # B2: 額外掃 HTML 註解內容（開發者常留測試資料 / TODO / 卡號 / token）
    comments_text = "\n".join(_HTML_COMMENT.findall(raw_html))
    pii_comments = detect_pii_in_text(comments_text) if comments_text else {}

    # 合併 main + comments（去重保序）
    pii = {}
    comment_only_counts: dict[str, int] = {}
    for key in ("email", "mobile", "national_id", "credit_card"):
        main_list = pii_main.get(key) or []
        comment_list = pii_comments.get(key) or []
        merged = list(dict.fromkeys(main_list + comment_list))
        pii[key] = merged
        # 計算「只在註解中發現」的筆數，提供使用者明確線索
        comment_only_counts[key] = len([v for v in comment_list if v not in main_list])

    # B5: 額外掃 raw HTML（不剝 SVG、不只看註解）內的開發者預留字串。
    # 為了避免一般網站誤觸發、僅當「同頁 PII 已有 1 筆以上 OR 字串看起來像 CTF flag」才報。
    dev_artifacts = list(dict.fromkeys(_DEV_ARTIFACT_PATTERN.findall(raw_html)))

    return pii, pii_comments, comment_only_counts, dev_artifacts


def _classify_pii(
    page_url: str,
    raw_html: str,
    pii: dict,
    pii_comments: dict,
    comment_only_counts: dict,
    dev_artifacts: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """依資料種類與出現脈絡分成（高風險, 個人聯絡資料, 刻意公開的聯絡方式）三組證據行。"""
    # 依「資料種類 × 出現脈絡」分級，而不是看到個資就一律高風險（2026-09-28 報告審查）：
    # 身分證、信用卡幾乎不會刻意公開 → 高風險；手機、非本網域 Email、藏在 HTML 註解的
    # 資料 → 中風險；網站自己網域的 Email 或 mailto/tel 連結 → 多半是刻意公開的聯絡資訊，
    # 只列為資訊提示請網站主確認，不當成外洩。
    site_domain = _registrable_domain(urlparse(page_url).hostname or "")
    site_label = site_domain.split(".", 1)[0] if site_domain else ""
    mailto = contacts.mailto_addresses(raw_html)
    tel = contacts.tel_numbers(raw_html)
    comment_values = {v for vals in pii_comments.values() for v in (vals or [])}

    sensitive: list[str] = []
    personal: list[str] = []
    public_contact: list[str] = []
    for label_key, label in (("national_id", "身分證號"), ("credit_card", "信用卡號")):
        if pii[label_key]:
            sensitive.append(_pii_line(label, pii[label_key], comment_only_counts[label_key]))
    personal_emails, public_emails = [], []
    for email in pii["email"]:
        domain = _registrable_domain(email.rsplit("@", 1)[-1].lower())
        in_comment = email in comment_values
        local = email.rsplit("@", 1)[0].lower()
        # 組織信箱：信箱名稱就是網站名稱（ntubimdbirc@ntub.edu.tw 之於 ntubimdbirc.tw）或角色信箱
        organizational = (len(site_label) >= 4 and site_label in local) or local in _ROLE_MAILBOXES
        if not in_comment and (
            email.lower() in mailto or (site_domain and domain == site_domain) or organizational
        ):
            public_emails.append(email)
        else:
            personal_emails.append(email)
    personal_mobiles, public_mobiles = [], []
    for mobile in pii["mobile"]:
        if mobile not in comment_values and contacts.normalize_phone(mobile) in tel:
            public_mobiles.append(mobile)
        else:
            personal_mobiles.append(mobile)
    if personal_emails:
        personal.append(_pii_line("email（非本網域或位於 HTML 註解）", personal_emails, 0))
    if personal_mobiles:
        personal.append(_pii_line("台灣手機", personal_mobiles, comment_only_counts["mobile"]))
    if dev_artifacts:
        personal.append(
            f"⚠️ 開發者預留字串（{len(dev_artifacts)} 筆）：{', '.join(dev_artifacts[:50])}"
        )
    if public_emails:
        public_contact.append(_pii_line("email（本網域或 mailto 連結）", public_emails, 0))
    if public_mobiles:
        public_contact.append(_pii_line("手機（tel 連結）", public_mobiles, 0))
    return sensitive, personal, public_contact


def analyze_data_exposure(page_input: PageAnalysisInput) -> list[dict]:
    """偵測頁面外洩的個人資料（email、台灣手機、身分證、信用卡）。

    顯示原始 PII 在 finding evidence 中（依使用者明確要求，不做遮罩）；
    description 前置警示文字，讓報告閱讀者意識到本報告含未遮罩個資的法律責任。
    身分證與信用卡含檢查碼驗證以降低 false positive。

    防誤報（B1）：移除 SVG 元素與所有 points/d 屬性，避免雷達圖等動態
    SVG 內的浮點座標數字（如 133.4346474264069）剛好 13-19 位且巧合通過
    Luhn 被誤判為信用卡號（實機在 cekb.local 測試靶機已觀察到此 FP）。

    強化覆蓋率（B2）：額外掃 HTML <!-- --> 註解內容，因為開發者最常把
    測試資料（PCI 測試卡 4111-1111-1111-1111、員工聯絡簿、TODO 含路徑、
    API key sample）以註解形式留在 production HTML。同類 evidence 會
    在文案上標示「含 HTML 註解 X 筆」讓使用者注意成因。
    """
    raw_html = page_input.html or ""
    pii, pii_comments, comment_only_counts, dev_artifacts = _collect_pii(raw_html)
    total = sum(len(v) for v in pii.values())
    if total == 0 and not dev_artifacts:
        return []
    sensitive, personal, public_contact = _classify_pii(
        page_input.final_url or page_input.url or "",
        raw_html,
        pii,
        pii_comments,
        comment_only_counts,
        dev_artifacts,
    )

    findings: list[dict] = []
    if sensitive:
        findings.append(
            _pii_finding(
                severity=Finding.Severity.HIGH,
                rule_id="SECURITY_PII_8B24BB8B28",
                title="頁面外洩個人資料 (PII)",
                description=(
                    "⚠️ 此項目顯示原始個資，請依個資法妥善處理本報告。\n"
                    "頁面內容出現通過檢查碼驗證的身分證號或信用卡號。這類資料幾乎不會刻意公開，"
                    "若非測試資料，可能違反個資法第 27 條的妥善保管義務，並讓當事人面臨冒用與詐"
                    "騙風險。"
                ),
                lines=sensitive,
                assessment={
                    "condition": (
                        "頁面對外公開、未經登入即可讀取，且內容含有真實的身分證號或信用卡號。"
                    ),
                    "observed": "頁面內容出現通過檢查碼驗證的號碼（見檢測依據，報告中已遮罩）。",
                    "missing": (
                        "檢查碼只能排除亂碼，無法證明號碼屬於真實當事人；也可能是測試資料或範例。"
                    ),
                    "verify": (
                        "由網站管理者確認號碼來源與是否為真實當事人；確認為真實資料時才維持高風險。"
                    ),
                },
                priority_score=85,
            )
        )
    if personal:
        findings.append(
            _pii_finding(
                severity=Finding.Severity.MEDIUM,
                rule_id="security-pii-personal-contact",
                title="頁面出現個人聯絡資料 (PII)",
                description=(
                    "⚠️ 此項目顯示原始個資，請依個資法妥善處理本報告。\n"
                    "頁面出現手機號碼、非本網站網域的 Email，或藏在 HTML 註解中的資料。"
                    "這些不一定是外洩（也可能是當事人同意公開的聯絡方式），但比網站官方聯絡信箱"
                    "更可能屬於個人。"
                ),
                lines=personal,
                assessment={
                    "condition": (
                        "資料屬於特定個人，且公開未經當事人同意（或不在網站的公開用途內）。"
                    ),
                    "observed": "頁面內容或 HTML 註解中出現上列資料（見檢測依據）。",
                    "missing": (
                        "無法從頁面判斷資料擁有者是否同意公開，以及公開是否為網站的既定用途。"
                    ),
                    "verify": (
                        "請網站管理者確認每筆資料的擁有者與公開依據；HTML 註解中的資料通常不應出現"
                        "在正式網站。"
                    ),
                },
                priority_score=55,
            )
        )
    if public_contact:
        findings.append(
            _pii_finding(
                severity=Finding.Severity.INFO,
                rule_id="security-pii-public-contact",
                title="頁面公開了聯絡 Email／電話（請確認是否刻意公開）",
                description=(
                    "頁面出現網站自己網域的 Email，或以 mailto／tel 連結提供的聯絡方式。"
                    "這通常是刻意公開的聯絡資訊，不屬於外洩；列出來是請你確認每一筆都是預期要公"
                    "開的。"
                ),
                lines=public_contact,
                assessment=None,
                priority_score=10,
            )
        )
    return findings


# 角色信箱：對外服務窗口，不屬於特定個人
_ROLE_MAILBOXES = {
    "info", "service", "services", "contact", "admin", "support", "help", "office", "hr",
    "sales", "marketing", "webmaster", "privacy", "dpo", "noreply", "no-reply", "news",
    "press", "pr", "media", "secretary", "center", "job", "jobs", "career", "careers",
}
_SECOND_LEVEL_LABELS = {
    "com", "edu", "gov", "org", "net", "ac", "co", "idv", "mil", "or", "ne", "go",
}


def _registrable_domain(host: str) -> str:
    """近似的可註冊網域：imd.ntub.edu.tw → ntub.edu.tw、www.example.com → example.com。"""
    labels = [label for label in (host or "").lower().strip(".").split(".") if label]
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL_LABELS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _pii_line(label: str, values: list[str], comment_only: int) -> str:
    note = f"，其中 {comment_only} 筆在 HTML 註解中" if comment_only else ""
    return f"{label}（{len(values)} 筆{note}）：{', '.join(values[:50])}"


def _pii_finding(*, severity, rule_id, title, description, lines, assessment, priority_score):
    evidence_json = None
    if assessment:
        evidence_json = {
            "type": "text",
            "source": "rule_engine",
            "excerpt": "\n".join(lines)[:1000],
            "assessment": assessment,
        }
    return make_finding(
        category=Finding.Category.SECURITY,
        severity=severity,
        rule_id=rule_id,
        title=title,
        description=description,
        remediation=(
            "1. 逐筆確認這些資料是否為刻意公開（如官方聯絡頁、承辦人信箱）。\n"
            "2. 非刻意公開者：從頁面與 HTML 註解移除，或改為登入後才能查看。\n"
            "3. 追查成因：後台資料直接輸出、除錯訊息、註解殘留、靜態檔案誤上傳等。\n"
            "4. 已被搜尋引擎或網頁封存收錄時，向 Google、Wayback Machine 申請移除。"
        ),
        evidence="\n".join(lines),
        evidence_json=evidence_json,
        impact_area="data_exposure",
        priority_score=priority_score,
    )


def visible_text_length(html: str) -> int:
    """估算 HTML 去除 script/style 後的可見文字字數（不含空白）。"""
    without_scripts = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        " ",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return len(re.sub(r"\s+", "", text))


def analyze_geo_fast(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    """GEO FAST 框架補充檢查：Accessible、Structured、Trim 三個維度。"""
    findings: list[dict] = []

    # Accessible：核心內容是否在初始 HTML 即可取得，而非高度依賴 JavaScript 渲染
    if page_input.html_only:
        rendered_length = visible_text_length(page_input.html)
        raw_length = visible_text_length(page_input.html_only)
        if rendered_length >= 400 and raw_length < rendered_length * 0.5:
            findings.append(
                make_finding(
                    category=Finding.Category.GEO,
                    severity=Finding.Severity.MEDIUM,
                    title="核心內容高度依賴 JavaScript 渲染",
                    description=(
                        "初始 HTML 的文字量明顯少於渲染後內容，"
                        "不執行 JavaScript 的 AI 爬蟲可能讀不到主要內容。"
                    ),
                    remediation=(
                        "以伺服器端渲染或靜態 HTML 提供核心內容，"
                        "確保不執行 JavaScript 也能取得主要文字。"
                    ),
                    evidence=f"raw_html_text={raw_length}, rendered_text={rendered_length}",
                    impact_area="accessible",
                    priority_score=66,
                )
            )

    # Structured：是否使用語意化主內容區塊標籤
    if "main" not in parser.semantic_landmarks:
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.LOW,
                title="缺少語意化主內容區塊",
                description="頁面未使用 main 等語意化區塊標籤，AI 與輔助技術較難辨識主要內容範圍。",
                remediation="以 main、article、section 等語意化標籤標示主要內容與段落結構。",
                evidence=f"semantic_landmarks={sorted(parser.semantic_landmarks)}",
                selector="main",
                impact_area="structured",
                priority_score=34,
            )
        )

    # Trim：段落是否過長，影響可被獨立引用的程度
    paragraphs = re.findall(
        r"<p[^>]*>(.*?)</p>",
        page_input.html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    long_paragraphs = [
        paragraph
        for paragraph in paragraphs
        if len(re.sub(r"<[^>]+>", "", paragraph).strip()) > 1000
    ]
    if long_paragraphs:
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.LOW,
                title="段落過長不利於 AI 引用",
                description="頁面有過長的段落，AI 系統較難擷取簡短、可獨立引用的內容片段。",
                remediation="將過長段落拆成聚焦單一重點的短段落，並適度加入小標題。",
                evidence=f"long_paragraph_count={len(long_paragraphs)}",
                selector="p",
                impact_area="trim",
                priority_score=28,
            )
        )
    return findings


def analyze_site_signals(site_signals: dict) -> list[dict]:
    """GEO FAST 框架的 Fetchable 維度：站台層級的 llms.txt 與 AI 爬蟲可存取性。"""
    findings: list[dict] = []
    if not site_signals.get("llms_txt_found"):
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.INFO,
                title="網站未提供 llms.txt",
                description=(
                    "llms.txt 可主動告知 AI 系統網站定位與重要頁面；"
                    "缺少時 AI 需自行推斷網站重點。"
                    "這是新興做法、尚未成為正式標準，主要搜尋與 AI 服務是否採用仍不確定，"
                    "列為選擇性建議。"
                ),
                remediation="在網站根目錄建立 llms.txt，列出網站簡介與重要頁面連結。",
                evidence="llms_txt_found=false",
                impact_area="fetchable",
                priority_score=20,
            )
        )
    # 只有擋到「AI 搜尋與回答」「使用者觸發讀取」的爬蟲才列問題；只擋訓練用爬蟲是正當的商業選擇，
    # 不影響這些服務的搜尋與引用（網站架構分頁另有完整的 AI 爬蟲政策表）
    policy = site_signals.get("ai_bot_policy") or {}
    answer_bots = ai_blocked(policy, AI_SEARCH, AI_USER)
    if answer_bots:
        names = "、".join(f"{b['agent']}（{b['vendor']}）" for b in answer_bots)
        training = [b["agent"] for b in ai_blocked(policy, AI_TRAINING)]
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.LOW,
                title="robots.txt 擋住 AI 搜尋與回答服務的爬蟲",
                description=(
                    f"robots.txt 封鎖了 {names}。這些爬蟲替 AI 搜尋與對話服務讀取網頁，"
                    "封鎖後這些服務的回答比較不會引用、連結到你的網站。"
                    + (
                        f"另外封鎖了訓練用的 {'、'.join(training)}，"
                        "那是不同的選擇，不影響搜尋與引用。"
                        if training else ""
                    )
                ),
                remediation=(
                    "如果希望出現在 AI 搜尋與回答中，在 robots.txt 允許上述爬蟲；"
                    "不想被拿去訓練模型的話，"
                    "只封鎖 GPTBot、ClaudeBot、Google-Extended 等訓練用爬蟲即可。"
                    "若是刻意不讓 AI 服務讀取，可忽略此項。"
                ),
                evidence="robots.txt 封鎖：" + "、".join(b["agent"] for b in answer_bots),
                rule_id="geo-ai-search-bots-blocked",
                evidence_json={"blocked": [b["agent"] for b in answer_bots],
                               "blocked_training": training},
                impact_area="fetchable",
                priority_score=30,
            )
        )
    return findings


# 分數衰減常數：category_score = 100 * exp(-penalty / SCORE_DECAY_CONSTANT)。
# 這是刻意可調的產品參數，不是演算法細節。目前值讓：
#   1 個低風險(4)   -> 92 分      1 個中風險(12)  -> 79 分
#   1 個高風險(35)  -> 50 分      1 個嚴重(60)    -> 30 分
#   典型中小企業體質(2 中 4 低 = 40) -> 45 分
# 調小 = 更嚴格（分數掉更快），調大 = 更寬鬆。
SCORE_DECAY_CONSTANT = 50.0


def _dedupe_findings_for_scoring(findings: list[dict]) -> list[dict]:
    """同一分類內同一個 rule_id 只保留第一筆。

    一個問題出現在幾頁是「廣度」不是「嚴重度」，不該讓扣分翻倍——報告本來就用
    reports._group_findings_for_report() 把它們合併成一筆顯示，計分卻沒有，於是
    使用者看到報告只列一項 PII，分數卻是被扣三次的結果。rule_id 缺漏時（例如
    agent 直接組出的 UX finding）退回 title 當鍵。
    """
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for finding in findings:
        key = _finding_key(finding)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


# 這些 rule 的結果已經反映在分類的「基準分」裡（base_scores），不再另外扣分
BASE_SCORED_RULE_PREFIXES = ("aeo-answer-",)

SCORE_CATEGORIES = ("seo", "aeo", "geo", "security", "ux")

# 嚴重度必須壓過數量。舊比例 35/25/14/6 讓「1 個 critical」(50 分) 約等於
# 「6 個 low」(49 分)——六個缺 canonical URL 等於一個嚴重漏洞，站不住腳。
# 拉開比例後 1 個 critical 是 30 分、6 個 low 是 62 分，數量只能在同一嚴重度
# 帶內移動分數，不能把嚴重度洗掉。
SEVERITY_PENALTY = {
    Finding.Severity.CRITICAL: 60,
    Finding.Severity.HIGH: 35,
    Finding.Severity.MEDIUM: 12,
    Finding.Severity.LOW: 4,
    Finding.Severity.INFO: 0,
}


def _finding_key(finding: dict) -> tuple[str, str]:
    return (
        str(finding.get("category") or ""),
        str(finding.get("rule_id") or finding.get("title") or ""),
    )


def score_breakdown(
    findings: list[dict],
    *,
    tested_categories: set[str] | None = None,
    base_scores: dict[str, int] | None = None,
) -> dict[str, dict]:
    """各維度分數的來源（roadmap §12 第 3 項：評分可解釋化）。

    calculate_scores() 的分類分數就是由這裡算出，兩者不會不一致。每個維度：

    - ``score``：base × e^(−penalty／SCORE_DECAY_CONSTANT)。
    - ``base``／``base_source``：基準分（預設 100；AEO 是可回答性分數）。
    - ``penalty``：扣分權重合計。
    - ``deductions``：逐項扣分（同一問題在多頁出現只扣一次，``occurrences`` 記出現筆數），
      ``score_without`` 是只修好這一項時的分數；依權重由大到小。
    - ``in_base``：已反映在基準分、不另外扣分的問題筆數（AEO 逐題結果）。
    - ``info``：資訊類（不扣分）筆數。
    """
    base_scores = base_scores or {}
    occurrences: dict[tuple[str, str], int] = {}
    for finding in findings:
        key = _finding_key(finding)
        occurrences[key] = occurrences.get(key, 0) + 1
    deduped = _dedupe_findings_for_scoring(findings)
    result: dict[str, dict] = {}
    for category in SCORE_CATEGORIES:
        if tested_categories is not None and category not in tested_categories:
            continue
        has_base = category in base_scores
        base = base_scores.get(category, 100)
        deductions, in_base, info = [], 0, 0
        for finding in deduped:
            if finding["category"] != category:
                continue
            key = _finding_key(finding)
            if has_base and str(finding.get("rule_id") or "").startswith(
                BASE_SCORED_RULE_PREFIXES
            ):
                in_base += occurrences[key]
                continue
            weight = SEVERITY_PENALTY.get(finding["severity"], 0)
            if not weight:
                info += occurrences[key]
                continue
            deductions.append({
                "rule_id": finding.get("rule_id") or "",
                "title": finding["title"],
                "severity": finding["severity"],
                "weight": weight,
                "occurrences": occurrences[key],
            })
        penalty = sum(item["weight"] for item in deductions)
        for item in deductions:
            item["score_without"] = round(
                base * math.exp(-(penalty - item["weight"]) / SCORE_DECAY_CONSTANT)
            )
        deductions.sort(key=lambda item: -item["weight"])
        result[category] = {
            "score": round(base * math.exp(-penalty / SCORE_DECAY_CONSTANT)),
            "base": base,
            "base_source": "aeo_answerability" if has_base and category == "aeo" else "",
            "penalty": penalty,
            "deductions": deductions,
            "in_base": in_base,
            "info": info,
        }
    return result


def calculate_scores(
    findings: list[dict],
    *,
    tested_categories: set[str] | None = None,
    base_scores: dict[str, int] | None = None,
) -> tuple[int, dict[str, int], list[dict]]:
    """算各分類分數與 overall_score。

    分數模型（2026-08-30 修正，成因見
    docs/scan-report-quality-audit-2026-08-30.md）：

    - **同一分類內同一 rule_id 只扣一次**：見 _dedupe_findings_for_scoring()。
    - **info 不扣分**：info 多半是純資訊甚至正向指標（例如「Nuclei 探針被 WAF
      攔截，代表防護有效」），舊版讓這種好消息倒扣 2 分。
    - **指數衰減取代線性扣減**：舊版 max(0, 100 - penalty) 累積 100 分懲罰後就
      固定歸零，4 個高風險與 40 個高風險看起來一樣，而且對只是缺幾個 header 的
      網站宣告「資安 0 分」並不成立。衰減讓分數在整個區間都保有解析度。
    - **未評估的分類不寫進 category_scores**：缺鍵即代表「未評估」。舊版一律回
      傳 ux=100，報告直接印「UX：100」，但 Agent 預設停用、UX 根本沒測，使用者
      會解讀成「UX 完美」。同時這讓「報告列出的分數」與「overall 平均的分母」
      一致——舊版列 5 個卻只平均 4 個，使用者怎麼算都對不出總分。

    tested_categories 傳 None 時視為全部類別皆已測試（相容舊呼叫）。

    base_scores：分類的基準分（預設 100）。AEO 的基準分是「可回答性」分數
    （aeo/evaluate.py，逐題判定的加權平均）；逐題 finding（BASE_SCORED_RULE_PREFIXES）
    已反映在基準分裡，不再重複扣分，其餘 AEO 問題（noindex、標記錯誤）照一般規則扣。

    呼叫端注意：category_scores 不再保證含全部 5 個分類，取值請用 .get()。
    """
    breakdown = score_breakdown(
        findings, tested_categories=tested_categories, base_scores=base_scores
    )
    category_scores = {category: entry["score"] for category, entry in breakdown.items()}
    deduped = _dedupe_findings_for_scoring(findings)
    overall_score = (
        round(sum(category_scores.values()) / len(category_scores))
        if category_scores
        else 0
    )
    # info 不進優先改善建議：它多半是正向或純資訊（例如「偵測到 WAF 保護」，
    # 對應的建議修補就是「無需修復」），列進待辦會誤導使用者。
    actionable = [
        finding
        for finding in deduped
        if finding["severity"] != Finding.Severity.INFO
    ]
    top_actions = [
        {
            "title": finding["title"],
            "category": finding["category"],
            "severity": finding["severity"],
            "priority_score": finding.get("priority_score") or 0,
        }
        for finding in sorted(
            actionable,
            key=lambda item: item.get("priority_score") or 0,
            reverse=True,
        )[:5]
    ]
    return overall_score, category_scores, top_actions
