import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from apps.scans.models import Finding

# ---------- PII（個人資料）偵測 ----------
# email 標準 pattern，要求 TLD 至少 2 字元
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# 台灣手機：09 開頭 + 8 位數字，允許中間有 -、空白；前後 lookahead/lookbehind 避免嵌入更長數字串誤判
TW_MOBILE_PATTERN = re.compile(r"(?<!\d)09\d{2}[\s\-]?\d{3}[\s\-]?\d{3}(?!\d)")

# 台灣身分證號：第一碼英文 + 1/2 + 8 位數字。需另經 is_valid_tw_national_id 檢查碼驗證
TW_NATIONAL_ID_PATTERN = re.compile(r"\b[A-Z][12]\d{8}\b")

# 信用卡號：13-19 位數字，常見 16 位 4-4-4-4 格式或無分隔。需另經 is_valid_luhn 驗證
CREDIT_CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[\s\-]?){12,18}\d(?!\d)")

# B1: 移除 SVG 元素（雷達圖等動態 SVG 內 polygon points / path d 屬性的浮點座標
# 數字片段巧合通過 Luhn 會被誤判為卡號，已實證 https://camb.xn--gst.tw 雷達圖案例）。
# 用非貪婪 + DOTALL，能抓含巢狀子元素的整段 <svg>...</svg>。
_HTML_SVG_STRIP = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)
# 殘留的 SVG 子元素標籤（裸的 <polygon>、<path>、<circle>...）整段移除，避免外層 <svg> 缺失時座標漏掉。
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

# 不對外索引的後台/管理路徑前綴。這些頁面不需要 SEO/AEO/GEO 評分（補 H1、JSON-LD
# 等對搜尋引擎曝光無意義），但安全性檢查（CSRF token、安全頭部）仍需照常進行。
ADMIN_PATH_PREFIXES = (
    "/admin",
    "/wp-admin",
    "/wp-login",
    "/dashboard",
    "/manage",
    "/api/",
)

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
        "email": list(dict.fromkeys(EMAIL_PATTERN.findall(text))),
        "mobile": list(dict.fromkeys(TW_MOBILE_PATTERN.findall(text))),
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
        self.form_count = 0
        self.form_without_csrf = 0
        self.json_ld_blocks: list[str] = []
        self.dl_count = 0
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
            if not attributes.get("alt", "").strip():
                self.image_without_alt += 1
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
        "priority_score": priority_score,
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


def analyze_page(page_input: PageAnalysisInput) -> list[dict]:
    parser = parse_html_signals(page_input.html)
    findings: list[dict] = []

    target_url = page_input.final_url or page_input.url

    # 二進位/媒體資源（.apk、.pdf 等）沒有頁面內容，不做 SEO/AEO/GEO 分析；
    # 安全頭部仍檢查，因為這些檔案的下載仍需 HSTS / X-Content-Type-Options 等保護。
    if is_binary_resource(target_url):
        findings.extend(analyze_security(page_input, parser))
        return findings

    # 管理後台/登入頁不對外索引，SEO/AEO/GEO 評分對其無意義；
    # 但 SECURITY 檢查（CSRF token、安全頭部）對後台反而更關鍵，必須保留。
    # PII 偵測也保留：後台頁面意外外洩個資反而更嚴重。
    if is_admin_path(target_url):
        findings.extend(analyze_security(page_input, parser))
        findings.extend(analyze_data_exposure(page_input))
        return findings

    findings.extend(analyze_seo(page_input, parser))
    findings.extend(analyze_aeo(page_input, parser))
    findings.extend(analyze_geo(page_input, parser))
    findings.extend(analyze_geo_fast(page_input, parser))
    findings.extend(analyze_security(page_input, parser))
    findings.extend(analyze_data_exposure(page_input))
    return findings


def analyze_seo(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    findings: list[dict] = []
    title_length = len((page_input.title or "").strip())
    if title_length < 10 or title_length > 65:
        findings.append(
            make_finding(
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
        )
    description_length = len(parser.meta_description.strip())
    if description_length < 50 or description_length > 160:
        findings.append(
            make_finding(
                category=Finding.Category.SEO,
                severity=Finding.Severity.LOW,
                title="Meta description 缺失或長度不理想",
                description="Meta description 缺失、過短或過長，會影響搜尋摘要品質。",
                remediation="補上清楚摘要頁面價值的 description，建議約 50 到 160 字元。",
                evidence=f"description_length={description_length}",
                selector='meta[name="description"]',
                impact_area="metadata",
                priority_score=38,
            )
        )
    if parser.h1_count != 1:
        findings.append(
            make_finding(
                category=Finding.Category.SEO,
                severity=Finding.Severity.MEDIUM if parser.h1_count == 0 else Finding.Severity.LOW,
                title="H1 標題數量不正確",
                description="每頁應有唯一且明確的 H1，協助搜尋引擎與使用者理解頁面主題。",
                remediation="保留一個代表頁面主題的 H1，其他段落標題改用 H2-H6。",
                evidence=f"h1_count={parser.h1_count}",
                selector="h1",
                bounding_box=page_input.element_boxes.get("h1"),
                impact_area="heading",
                priority_score=55 if parser.h1_count == 0 else 42,
            )
        )
    if parser.image_without_alt:
        findings.append(
            make_finding(
                category=Finding.Category.SEO,
                severity=Finding.Severity.LOW,
                title="圖片缺少 alt 屬性",
                description="圖片缺少替代文字會降低無障礙體驗，也讓搜尋引擎難以理解圖片內容。",
                remediation="為有語意的圖片補上精準 alt，裝飾性圖片可使用空 alt。",
                evidence=(
                    f"image_count={parser.image_count}, "
                    f"image_without_alt={parser.image_without_alt}"
                ),
                selector="img:not([alt])",
                bounding_box=page_input.element_boxes.get("img:not([alt])"),
                impact_area="accessibility",
                priority_score=25,
            )
        )
    if not parser.canonical:
        findings.append(
            make_finding(
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
        )
    return findings


def analyze_aeo(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    findings: list[dict] = []
    json_ld_text = "\n".join(parser.json_ld_blocks).lower()
    has_faq_or_howto = "faqpage" in json_ld_text or "howto" in json_ld_text

    # 問句訊號改從可見文字計算，避免 HTML 屬性、註解、tag 名稱中的字元
    # 被誤算（例如 class="how-to-img" 被當成「如何」）。
    visible_text = re.sub(r"<[^>]+>", " ", page_input.html or "")
    question_like = len(re.findall(r"[？?]|什麼|如何|為何|怎麼", visible_text))

    # 問句門檻必須夠高才視為真正的問答內容；單純內文出現「什麼」「如何」
    # 等常用詞不應觸發 FAQPage 建議。
    if question_like < 4:
        return findings

    has_faq_structure = detect_faq_structure(page_input.html, parser.dl_count)

    if has_faq_structure and not has_faq_or_howto:
        # 已有明確的 FAQ 結構卻沒有對應 Schema：補 Schema 才有意義。
        findings.append(
            make_finding(
                category=Finding.Category.AEO,
                severity=Finding.Severity.LOW,
                title="問答內容缺少 FAQPage 或 HowTo 結構化資料",
                description=(
                    "頁面已有 FAQ 結構（dl/details/accordion）但缺少對應 Schema，"
                    "AI answer engine 較難穩定抽取答案。"
                ),
                remediation="為現有 FAQ 內容加入符合主題的 FAQPage 或 HowTo Schema。",
                evidence=(
                    f"question_like_count={question_like}, "
                    f"json_ld_blocks={len(parser.json_ld_blocks)}, "
                    f"dl_count={parser.dl_count}"
                ),
                selector='script[type="application/ld+json"]',
                impact_area="answer_engine",
                priority_score=38,
            )
        )
    elif not has_faq_structure:
        # 出現大量問答語氣卻沒有任何 FAQ 結構：先整理內容比補 Schema 重要。
        findings.append(
            make_finding(
                category=Finding.Category.AEO,
                severity=Finding.Severity.INFO,
                title="問答資訊缺少明確結構",
                description="頁面出現大量問句但沒有明確的問答區塊，AI 與使用者都較難快速擷取答案。",
                remediation=(
                    "使用 dl/details、明確的小標題或 FAQ 區塊整理問答內容，"
                    "再考慮加上 Schema。"
                ),
                evidence=f"question_like_count={question_like}, dl_count={parser.dl_count}",
                impact_area="content_structure",
                priority_score=25,
            )
        )
    return findings


def analyze_geo(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    findings: list[dict] = []
    text = re.sub(r"<[^>]+>", " ", page_input.html or "")
    paragraph_count = len(re.findall(r"<p[\s>]", page_input.html or "", flags=re.IGNORECASE))
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
                evidence=f"paragraph_count={paragraph_count}, text_length={len(text.strip())}",
                selector="main",
                bounding_box=page_input.element_boxes.get("main"),
                impact_area="chunkability",
                priority_score=20,
            )
        )
    return findings


def analyze_security(page_input: PageAnalysisInput, parser: HtmlSignalParser) -> list[dict]:
    findings: list[dict] = []
    parsed = urlparse(page_input.final_url)
    headers = {key.lower(): value for key, value in page_input.headers.items()}
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
        "content-security-policy": (Finding.Severity.MEDIUM, "缺少 CSP"),
        "x-frame-options": (Finding.Severity.LOW, "缺少 X-Frame-Options"),
        "x-content-type-options": (Finding.Severity.INFO, "缺少 X-Content-Type-Options"),
    }
    for header_name, (severity, title) in required_headers.items():
        if header_name not in headers:
            findings.append(
                make_finding(
                    category=Finding.Category.SECURITY,
                    severity=severity,
                    title=title,
                    description=f"Response header 缺少 {header_name}，可能降低瀏覽器防護能力。",
                    remediation=f"依網站需求設定合適的 {header_name} header。",
                    evidence=f"missing_header={header_name}",
                    impact_area="security_headers",
                    priority_score=55 if severity == Finding.Severity.MEDIUM else 25,
                )
            )
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

    # B1: 移除 SVG 整段 → 殘留的 SVG 子元素 → 殘留的 SVG 座標屬性；三層防護避免浮點誤判為卡號
    safe_html = _HTML_SVG_STRIP.sub(" ", raw_html)
    safe_html = _HTML_SVG_ELEMENTS.sub(" ", safe_html)
    safe_html = _HTML_PATH_ATTR.sub(" ", safe_html)
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

    total = sum(len(v) for v in pii.values())
    if total == 0 and not dev_artifacts:
        return []

    # 每類最多列前 50 筆，避免 evidence 欄位被個資灌爆（make_finding 還會截到 4000 字）
    pii_labels = [
        ("email", "email"),
        ("mobile", "台灣手機"),
        ("national_id", "身分證號"),
        ("credit_card", "信用卡號"),
    ]
    parts: list[str] = []
    for key, label in pii_labels:
        values = pii[key]
        if values:
            comment_note = ""
            if comment_only_counts.get(key):
                comment_note = f"，其中 {comment_only_counts[key]} 筆在 HTML 註解中"
            parts.append(f"{label}（{len(values)} 筆{comment_note}）：{', '.join(values[:50])}")

    # B5: 開發者預留字串獨立一行顯示（CTF flag / TODO placeholder / Lorem 等）
    if dev_artifacts:
        parts.append(
            f"⚠️ 開發者預留字串（{len(dev_artifacts)} 筆）：{', '.join(dev_artifacts[:50])}"
        )

    evidence = "\n".join(parts)

    return [
        make_finding(
            category=Finding.Category.SECURITY,
            severity=Finding.Severity.HIGH,
            title="頁面外洩個人資料 (PII)",
            description=(
                "⚠️ 此項目顯示原始個資，請依個資法妥善處理本報告。\n"
                f"在頁面內容中偵測到 {total} 筆疑似個資（email、手機、身分證、信用卡）。"
                "若這些資料非刻意公開（如聯絡資訊頁），可能違反個資法第 27 條的妥善保管義務，"
                "並讓網站使用者面臨身分盜用、詐騙、釣魚等風險。"
            ),
            remediation=(
                "1. 確認這些資料是否為刻意公開（如官方聯絡頁、開源貢獻者名單）。\n"
                "2. 若為意外外洩，立即下架該頁或加上登入驗證。\n"
                "3. 檢查成因：DB 直連 API 未驗證、debug 訊息洩漏、後台路徑未限制存取、"
                "JSON-LD/comment 內嵌入個資、靜態檔案誤上傳等。\n"
                "4. 對歷史快取（Google cache、Wayback Machine）發起移除請求。"
            ),
            evidence=evidence,
            impact_area="data_exposure",
            priority_score=85,
        )
    ]


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
                ),
                remediation="在網站根目錄建立 llms.txt，列出網站簡介與重要頁面連結。",
                evidence="llms_txt_found=false",
                impact_area="fetchable",
                priority_score=20,
            )
        )
    blocked = site_signals.get("blocked_ai_crawlers") or []
    if blocked:
        findings.append(
            make_finding(
                category=Finding.Category.GEO,
                severity=Finding.Severity.INFO,
                title="robots.txt 阻擋了主流 AI 爬蟲",
                description=(
                    "robots.txt 目前阻擋部分 AI 爬蟲；"
                    "若你希望內容能被 AI 引用，這會降低曝光，請依自身策略判斷。"
                ),
                remediation=(
                    "若希望被 AI 系統收錄，檢視 robots.txt 對 AI 爬蟲 User-Agent 的規則；"
                    "若刻意阻擋則可忽略此項。"
                ),
                evidence=f"blocked_ai_crawlers={blocked}",
                impact_area="fetchable",
                priority_score=18,
            )
        )
    return findings


def calculate_scores(findings: list[dict]) -> tuple[int, dict[str, int], list[dict]]:
    categories = [
        Finding.Category.SEO,
        Finding.Category.AEO,
        Finding.Category.GEO,
        Finding.Category.SECURITY,
        Finding.Category.UX,
    ]
    severity_penalty = {
        Finding.Severity.CRITICAL: 35,
        Finding.Severity.HIGH: 25,
        Finding.Severity.MEDIUM: 14,
        Finding.Severity.LOW: 6,
        Finding.Severity.INFO: 2,
    }
    category_scores: dict[str, int] = {}
    for category in categories:
        penalty = sum(
            severity_penalty.get(finding["severity"], 0)
            for finding in findings
            if finding["category"] == category
        )
        category_scores[category] = max(0, 100 - penalty)
    overall_score = round(sum(category_scores.values()) / len(category_scores))
    top_actions = [
        {
            "title": finding["title"],
            "category": finding["category"],
            "severity": finding["severity"],
            "priority_score": finding.get("priority_score") or 0,
        }
        for finding in sorted(
            findings,
            key=lambda item: item.get("priority_score") or 0,
            reverse=True,
        )[:5]
    ]
    return overall_score, category_scores, top_actions
