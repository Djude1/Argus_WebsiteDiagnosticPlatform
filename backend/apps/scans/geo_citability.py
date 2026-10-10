"""GEO 可引用性：內容本身容不容易被 AI 引用（roadmap §3 GEO，2026-10-10）。

結構面（JSON-LD、小標題、可摘要性）由 `analyze_geo`／`geo_structure` 負責；這裡補「內容訊號」——
依 Princeton「GEO: Generative Engine Optimization」(Aggarwal et al., KDD 2024,
arxiv.org/abs/2311.09735) 在 GEO-bench 10,000 題實測，最能提升被 AI 引用機率的三種寫法：

- 引用權威來源（Cite Sources，實測 +27%）：連到 .gov/.edu/.ac 或學術網域、`<cite>`、參考資料區塊。
- 具體統計數字（Statistics，+33%）：百分比、金額、量化數據。
- 專家引言（Quotation，+41%）：blockquote、`<q>`、「"……" — 某某」attributed quote。

方法移植自 GeoReady / geo-optimizer-skill（MIT, auriti-labs）的 citability.py，改寫成 stdlib 判定。
只讀已保存的 HTML、不發請求。這些是「軟訊號」：缺少不代表內容錯誤，只是比較難被引用，
因此嚴重度壓在 low／info，且只對「有一定篇幅的正文頁」出題（導覽頁、縮圖頁不評）。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from apps.scans.aeo.content import extract_page_content
from apps.scans.models import Finding
from apps.scans.scanners import make_finding
from apps.scans.seo.page_audit import content_size

# 只對有一定篇幅的正文頁評可引用性（content_size 的「英文詞＋中文字÷1.5」換算，偏保守）；
# 短頁、導覽頁、縮圖頁不出題
MIN_PROSE_WORDS = 200
MIN_PROSE_CHARS = 40

_HTML_DOC = re.compile(r"<(?:html|body)\b", re.IGNORECASE)
_CODE_BLOCK = re.compile(r"<(pre|code)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

# 權威來源：政府／教育／學術頂級網域與知名學術網域
_AUTHORITATIVE_TLDS = (".gov", ".edu", ".int", ".mil")
_AUTHORITATIVE_TLDS_MULTI = (".gov.tw", ".edu.tw", ".ac.uk", ".gov.uk", ".go.jp", ".ac.jp")
_AUTHORITATIVE_DOMAINS = (
    "wikipedia.org", "wikidata.org", "who.int", "cdc.gov", "nih.gov", "ncbi.nlm.nih.gov",
    "europa.eu", "oecd.org", "worldbank.org", "un.org", "arxiv.org", "doi.org",
    "nature.com", "science.org", "ieee.org", "acm.org", "jstor.org", "springer.com",
    "sciencedirect.com", "pubmed.ncbi.nlm.nih.gov",
)

_HREF_RE = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_CITE_TAG_RE = re.compile(r"<cite\b", re.IGNORECASE)
_BLOCKQUOTE_RE = re.compile(r"<blockquote\b", re.IGNORECASE)
_Q_TAG_RE = re.compile(r"<q\b", re.IGNORECASE)
_REF_HEADING_RE = re.compile(
    r"<h[2-4]\b[^>]*>\s*(?:[^<]*?)"
    r"(references?|sources?|bibliograph|參考(?:資料|文獻|書目)|引用(?:來源|資料)|資料來源)",
    re.IGNORECASE,
)
# 「"……" — 某某」attributed quote（引號 10–300 字後接破折號與署名），避免跨段誤判不用 DOTALL
_QUOTE_ATTRIB_RE = re.compile(
    r'["“「][^"”」\n]{10,300}["”」]\s*[——–-]\s*\w'
)
# 統計數字：百分比、千分位整數、金額、「N 萬／億」、倍數
_STAT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*%"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|[$€£¥]\s?\d+(?:[.,]\d+)*"
    r"|\bNT\$\s?\d+"
    r"|\d+(?:\.\d+)?\s*(?:萬|億|million|billion|trillion|thousand)"
    r"|\d+(?:\.\d+)?\s*(?:倍|x)\b",
    re.IGNORECASE,
)


def _is_authoritative(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    if host.endswith(_AUTHORITATIVE_TLDS) or host.endswith(_AUTHORITATIVE_TLDS_MULTI):
        return True
    return any(host == d or host.endswith("." + d) or d in host for d in _AUTHORITATIVE_DOMAINS)


def citability_findings(url: str, html: str) -> list[dict]:
    """可引用性三項軟訊號。只對有一定篇幅的正文頁出題。"""
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

    base_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    authoritative = external = 0
    for href in _HREF_RE.findall(clean):
        if not href.lower().startswith(("http://", "https://")):
            continue
        host = (urlparse(href).hostname or "").lower().removeprefix("www.")
        if not host or host == base_host:
            continue
        external += 1
        if _is_authoritative(host):
            authoritative += 1
    cite_tags = len(_CITE_TAG_RE.findall(clean))
    has_refs = bool(_REF_HEADING_RE.search(clean))
    stat_hits = len(_STAT_RE.findall(body))
    quotes = (
        len(_BLOCKQUOTE_RE.findall(clean))
        + len(_Q_TAG_RE.findall(clean))
        + len(_QUOTE_ATTRIB_RE.findall(body))
    )

    findings: list[dict] = []

    # 1. Cite Sources（+27%）：有篇幅卻完全沒有權威引用
    if authoritative < 2 and not has_refs and cite_tags == 0:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.LOW,
            rule_id="geo-citability-no-sources",
            title="內容缺少可追溯的權威來源引用",
            description=(
                "這是一篇有篇幅的內容，但沒有連到政府／學術等權威來源，也沒有「參考資料」區塊或"
                "<cite> 標記。AI 問答引擎會把「有附來源」當成可信與可引用的訊號；補上出處能明顯"
                "提高被引用的機率。"
            ),
            remediation=(
                "在關鍵論述後附上權威出處，格式如「根據〔來源〕(連結)，……」，優先連學術論文、"
                "政府（.gov）或教育（.edu）網站；文末可加「參考資料」清單。"
            ),
            evidence=(
                f"外部連結 {external} 個，其中權威來源 {authoritative} 個；"
                f"參考資料區塊：{'有' if has_refs else '無'}；<cite> 標記：{cite_tags} 個。"
            ),
            evidence_source="rule_engine",
        ))

    # 2. Statistics（+33%）：幾乎沒有具體數據
    if stat_hits < 3:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.INFO,
            rule_id="geo-citability-no-statistics",
            title="內容缺少具體的量化數據",
            description=(
                "內容幾乎沒有百分比、金額或具體數字。AI 問答引擎傾向擷取可驗證的量化事實，"
                "把概括敘述換成具體數據（並註明來源與年份）更容易被引用。"
            ),
            remediation=(
                "把「很多」「大幅成長」這類概括說法改成具體數字，例如「2024 年達 34.2%（來源）」。"
            ),
            evidence=f"偵測到的數據樣式 {stat_hits} 處（門檻 3）。",
            evidence_source="rule_engine",
        ))

    # 3. Quotation（+41%）：沒有任何引言
    if quotes == 0:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.INFO,
            rule_id="geo-citability-no-quotations",
            title="內容沒有可引用的引言",
            description=(
                "內容沒有專家或權威的引述（blockquote／「引文」— 某某）。帶署名的引言是"
                "可驗證、可歸屬的內容，AI 引擎較願意直接摘錄。"
            ),
            remediation=(
                "適度加入 1–2 則專家或官方文件引言，格式「引文」— 姓名，職稱，年份，"
                "並用 <blockquote> 標記。"
            ),
            evidence="未偵測到 blockquote／<q>／署名引言。",
            evidence_source="rule_engine",
        ))

    return findings
