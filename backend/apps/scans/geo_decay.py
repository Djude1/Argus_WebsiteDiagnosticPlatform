"""GEO 內容衰退預測（2026-10-10，借鑑 GeoReady/geo-optimizer-skill MIT 的 audit_decay）。

`geo_entity.freshness_findings` 只看「有沒有、合不合理的日期標記」；這裡補「內容本身會不會過時」：
正文裡的明確過去年份、時效性措辭（最近／今年／目前最新…）、軟體版本號、價格，隔一段時間就可能
與現況不符，卻沒有 dateModified 之類的新鮮度訊號時，AI 引用舊資訊的風險較高。

只讀已保存 HTML、不發請求，只對有篇幅的正文頁出題（footer 的版權年份由正文擷取排除、不計），
且要同時出現 ≥2 類衰退訊號才提醒——單一「2024 年」不足以成立。軟訊號，嚴重度 info，不重扣分。
"""

from __future__ import annotations

import re
from datetime import date

from apps.scans.aeo.content import extract_page_content
from apps.scans.models import Finding
from apps.scans.scanners import make_finding
from apps.scans.seo.page_audit import content_size

MIN_PROSE_WORDS = 200
MIN_PROSE_CHARS = 40
MIN_SIGNAL_CATEGORIES = 2  # 要同時有兩類以上才提醒，避免單一年份誤報

_HTML_DOC = re.compile(r"<(?:html|body)\b", re.IGNORECASE)
_CODE_BLOCK = re.compile(r"<(pre|code)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

_YEAR_RE = re.compile(r"(?<!\d)(20[0-2]\d)(?!\d)")
_RECENCY_RE = re.compile(
    r"\b(?:recently|just\s+(?:launched|released|announced|updated)|currently|"
    r"the\s+(?:latest|newest|current)\s+(?:version|release|update))\b"
    r"|最近|近期|日前|目前|現在|今年|去年|上個月|本月|最新(?:版|消息)?|剛(?:推出|上線|發表)",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(
    r"\b(?:Python|Node|Java|PHP|Ruby|Go|Rust|React|Angular|Vue|Next\.?js|Django|"
    r"Laravel|Rails|Swift|Kotlin|TypeScript|iOS|Android|Windows|macOS)\s+v?\d+(?:\.\d+)+"
    r"|\bv(?:ersion)?\s*\d+\.\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(
    r"[$€£¥]\s?\d[\d,]*(?:\.\d{2})?\s*/\s*(?:mo(?:nth)?|yr|year|月|年)"
    r"|NT\$\s?\d[\d,]*\s*/\s*(?:月|年)"
    r"|每(?:月|年)\s?(?:NT\$|[$])?\s?\d",
    re.IGNORECASE,
)


def decay_findings(url: str, html: str) -> list[dict]:
    html = html or ""
    if not _HTML_DOC.search(html[:5000]):
        return []
    clean = _CODE_BLOCK.sub(" ", html)
    content = extract_page_content(url, clean)
    body = "\n".join(
        p.text for p in content.passages
        if p.region == "main" and not p.is_heading and len(p.text) >= MIN_PROSE_CHARS
    )
    if content_size(body)["word_equivalent"] < MIN_PROSE_WORDS:
        return []

    this_year = date.today().year
    samples: list[str] = []
    categories: set[str] = set()

    def _add(category: str, match: re.Match) -> None:
        categories.add(category)
        if len(samples) < 5:
            start, end = max(0, match.start() - 20), min(len(body), match.end() + 20)
            samples.append(" ".join(body[start:end].split()))

    for m in _YEAR_RE.finditer(body):
        if int(m.group(1)) <= this_year - 1:  # 過去年份才算（當年、未來不算）
            _add("過去年份", m)
    _pats = ((_RECENCY_RE, "時效性措辭"), (_VERSION_RE, "軟體版本"), (_PRICE_RE, "定期價格"))
    for pat, name in _pats:
        m = pat.search(body)
        if m:
            _add(name, m)

    if len(categories) < MIN_SIGNAL_CATEGORIES:
        return []

    return [make_finding(
        category=Finding.Category.GEO,
        severity=Finding.Severity.INFO,
        rule_id="geo-content-decay",
        title="內容可能隨時間過時，建議標示新鮮度",
        description=(
            "頁面同時出現「" + "、".join(sorted(categories)) + "」等會隨時間變動的內容，"
            "但沒有明確的更新日期訊號。AI 引擎無法判斷資訊是否仍然正確時，較不願意引用；"
            "補上更新日期或改用相對寫法能降低被當成過時內容的風險。"
        ),
        remediation=(
            "為文章加上 dateModified 結構化資料或「更新於 YYYY-MM-DD」；具體年份改成相對說法"
            "（如「截至最新」），價格與版本號標註「截至某日」或連到即時頁面。"
        ),
        evidence="；".join(samples),
        evidence_source="rule_engine",
    )]
