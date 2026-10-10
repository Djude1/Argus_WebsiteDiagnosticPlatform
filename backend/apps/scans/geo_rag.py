"""GEO RAG 分塊就緒（2026-10-10，借鑑 GeoReady/geo-optimizer-skill MIT 的 audit_rag）。

AI 問答引擎多半把頁面切成「區段（chunk）」再檢索引用；區段太長時，一段混了多個主題，
AI 難以擷取乾淨、可引用的片段（SE Ranking 2026：100–150 字的區段被引用率明顯較高）。

`geo_structure` 已處理「長文完全沒有小標題」。這裡補互補的情況：**有小標題、但平均每段仍然過長**
（分段了卻分得不夠細）。以原始 HTML 的小標題數估算平均區段長度，超過建議長度才提醒。
只讀已保存 HTML、不發請求，只對有篇幅的正文頁出題；軟訊號，嚴重度 info，不重扣分。
"""

from __future__ import annotations

import re

from apps.scans.aeo.content import extract_page_content
from apps.scans.models import Finding
from apps.scans.scanners import make_finding
from apps.scans.seo.page_audit import content_size

MIN_PROSE_WORDS = 300  # RAG 分塊只對較長的內容頁有意義
MIN_PROSE_CHARS = 40
MIN_HEADINGS = 2            # 要有小標題（沒有屬 geo_structure 的「長文無小標題」）
SECTION_MAX_WORDS = 280    # 平均每段超過這個長度就算對 RAG 偏大（content_size 偏低估，門檻放寬）

_HTML_DOC = re.compile(r"<(?:html|body)\b", re.IGNORECASE)
_CODE_BLOCK = re.compile(r"<(pre|code)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
# 小標題直接數原始 HTML（與 geo_structure 一致：正文擷取會排除 <header> 裡的標題）
_SUBHEADING = re.compile(r"<h[2-6]\b", re.IGNORECASE)


def rag_findings(url: str, html: str) -> list[dict]:
    html = html or ""
    if not _HTML_DOC.search(html[:5000]):
        return []
    clean = _CODE_BLOCK.sub(" ", html)
    content = extract_page_content(url, clean)
    body = "\n".join(
        p.text for p in content.passages
        if p.region == "main" and not p.is_heading and len(p.text) >= MIN_PROSE_CHARS
    )
    total_words = content_size(body)["word_equivalent"]
    headings = len(_SUBHEADING.findall(clean))
    if total_words < MIN_PROSE_WORDS or headings < MIN_HEADINGS:
        return []

    # 平均每個小標題區段的長度（內容頁多半由小標題開頭，區段數 ≈ 小標題數）
    avg_section = round(total_words / headings)
    if avg_section <= SECTION_MAX_WORDS:
        return []

    return [make_finding(
        category=Finding.Category.GEO,
        severity=Finding.Severity.INFO,
        rule_id="geo-rag-chunking",
        title="內容區段偏長，不利 AI 逐段擷取",
        description=(
            f"頁面有 {headings} 個小標題，但正文約 {total_words} 字，平均每段約 {avg_section} 字，"
            f"超過適合 AI 檢索的長度（約 {SECTION_MAX_WORDS} 字以內）。AI 以區段為單位檢索，"
            "一段混了多個主題會讓它難以擷取乾淨、可引用的片段。"
        ),
        remediation=(
            "把過長的段落再用小標題或清單細分，讓每個主題自成一段（約 100–150 字為佳），"
            "並讓每段開頭就是一句可獨立理解的重點句。"
        ),
        evidence=f"小標題 {headings} 個、正文約 {total_words} 字、平均每段約 {avg_section} 字。",
        evidence_source="rule_engine",
    )]
