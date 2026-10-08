"""GEO 可被 AI 摘要性：內容結構（roadmap §3 GEO 第 3 項）。

AI 摘要與引用是一段一段擷取的。段落過長、可引用區塊太少、缺 main 已由 `scanners.analyze_geo`／
`analyze_geo_fast` 檢查；這裡補兩項規則能客觀判斷的結構問題：

- 長篇內容沒有小標題：正文很長卻沒有 h2–h6 分段，AI 難以切出主題明確的片段。
- 列舉寫成一整段：同一段裡有 3 個以上編號（「(1)…(2)…(3)」「第一、第二、第三」），
  頁面卻沒有清單標記；改成清單，步驟與條件更容易被逐項引用。

「開頭有沒有摘要句」這類寫作品質判斷規則無法可靠判定，刻意不做。只讀已保存的 HTML，不發請求。
"""

from __future__ import annotations

import re

from apps.scans.aeo.content import extract_page_content
from apps.scans.models import Finding
from apps.scans.scanners import make_finding
from apps.scans.seo.page_audit import content_size

# 正文換算成「英文詞＋中文字÷1.5」超過這個量（約中文 1500 字、英文 1000 詞）還沒有小標題，
# 才算長篇未分段；一般新聞稿（800–1500 字）不分段是正常寫法
LONG_CONTENT_WORDS = 1000
# 只算成句的段落：入口網站首頁的正文多半是上百個短連結文字（中華郵政首頁中位數 10 字），不是長文
MIN_PROSE_CHARS = 40
MIN_ENUMERATION_ITEMS = 3
_ENUMERATION = re.compile(
    # 括號編號本身就有分隔，不要求前面是空白或標點：「表單（2）上傳」
    r"[（(]\s*\d{1,2}\s*[)）]"
    r"|(?:^|[\s，。；：:,;])"
    r"(?:\d{1,2}[.、)](?!\d)|第[一二三四五六七八九十]+[、，：:]|[一二三四五六七八九十][、](?=\S))"
)
# 小標題直接數原始 HTML：正文擷取會排除 <header>，
# 部落格常把文章標題放在 <header class="entry-header">
_SUBHEADING = re.compile(r"<h[2-6]\b", re.IGNORECASE)
_HTML_DOC = re.compile(r"<(?:html|body)\b", re.IGNORECASE)
# 程式碼區塊不是文章內容（css-tricks 的 CSS 範例「style(--index: 1)…」會被當成編號列舉）
_CODE_BLOCK = re.compile(r"<(pre|code)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def structure_findings(url: str, html: str) -> list[dict]:
    html = html or ""
    # RSS／XML 等非網頁文件不是給人讀的頁面
    if not _HTML_DOC.search(html[:5000]):
        return []
    content = extract_page_content(url, _CODE_BLOCK.sub(" ", html))
    main = [p for p in content.passages if p.region == "main"]
    body = "\n".join(
        p.text for p in main if not p.is_heading and len(p.text) >= MIN_PROSE_CHARS
    )
    subheadings = len(_SUBHEADING.findall(html))
    findings: list[dict] = []

    size = content_size(body)
    if size["word_equivalent"] >= LONG_CONTENT_WORDS and not subheadings:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.LOW,
            rule_id="geo-long-content-no-subheadings",
            title="長篇內容沒有小標題分段",
            description=(
                "這頁的正文很長，卻沒有用小標題（h2–h6）分段。AI 摘要與引用是一段一段擷取的，"
                "沒有小標題時較難切出主題明確的片段，讀者也不容易找到需要的部分。"
            ),
            remediation="依主題把內容分成幾個段落，每段加上描述該段重點的小標題（h2／h3）。",
            evidence=(
                f"{url}\n正文約 {size['cjk_chars']} 個中文字、{size['latin_words']} 個英文詞；"
                "沒有 h2–h6 小標題"
            ),
            selector="main h2, main h3",
            impact_area="chunkability",
            evidence_json={"url": url, **size},
            priority_score=29,
        ))

    # 清單的每一項會被擷取成獨立段落；同一段裡就有 3 個編號，代表沒有寫成清單
    # （不看整頁有沒有 <ul>：幾乎每個網站的導覽列都是 <ul>）
    enumerated = [
        p.text for p in main
        if not p.is_heading and len(_ENUMERATION.findall(p.text)) >= MIN_ENUMERATION_ITEMS
    ]
    if enumerated:
        findings.append(make_finding(
            category=Finding.Category.GEO,
            severity=Finding.Severity.INFO,
            rule_id="geo-enumeration-not-list",
            title="列舉內容寫成一整段",
            description=(
                f"有 {len(enumerated)} 段文字在同一段裡列了 3 個以上的編號項目，"
                "沒有寫成清單。"
                "步驟、條件與比較寫成清單，AI 與讀者都更容易逐項擷取。"
            ),
            remediation="把這些編號項目改成 <ol>／<ul> 清單，每項一個 <li>。",
            evidence=f"{url}\n" + "\n".join(text[:120] for text in enumerated[:3]),
            selector="main p",
            impact_area="structured",
            evidence_json={"url": url, "paragraphs": len(enumerated)},
        ))
    return findings
