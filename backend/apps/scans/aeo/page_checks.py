"""AEO 逐頁檢查（analyze_page 的 aeo 維度）：第 1 層的存取限制＋第 4 層的標記一致性。

站台層級的「能否回答問題」在 evaluate.py，於所有頁面分析完後執行一次。
"""

from __future__ import annotations

from apps.scans.aeo.content import (
    blocks_indexing,
    blocks_snippets,
    extract_page_content,
    nosnippet_block_count,
    robots_directives,
)
from apps.scans.aeo.markup import check_markup


def analyze_page_aeo(page_input, parser) -> list[dict]:
    from apps.scans.models import Finding
    from apps.scans.scanners import make_finding

    findings: list[dict] = []
    url = page_input.final_url or page_input.url
    directives = robots_directives(page_input.html, page_input.headers)
    source_text = "；".join(f"{k}（{v}）" for k, v in directives.items())

    if blocks_indexing(directives):
        findings.append(
            make_finding(
                category=Finding.Category.AEO,
                severity=Finding.Severity.MEDIUM,
                rule_id="aeo-noindex",
                title="頁面設定為不可被索引，內容無法成為搜尋或 AI 回答的來源",
                description=(
                    "此頁用 noindex 要求搜尋引擎不要收錄。未收錄的頁面不會出現在搜尋結果，"
                    "也不會被搜尋引擎的 AI 功能引用。若這是刻意的（例如會員頁、測試頁），可以忽略。"
                ),
                remediation=(
                    "確認此頁是否應被收錄；若應被收錄，移除 meta robots 或 X-Robots-Tag 的 noindex"
                    "。"
                ),
                evidence=f"{url}\n索引指令：{source_text}",
                impact_area="answer_engine",
                evidence_json={"url": url, "directives": directives},
            )
        )
    elif blocks_snippets(directives):
        findings.append(
            make_finding(
                category=Finding.Category.AEO,
                severity=Finding.Severity.MEDIUM,
                rule_id="aeo-nosnippet",
                title="頁面禁止顯示摘要，搜尋結果與 AI 功能無法引用內文",
                description=(
                    "nosnippet 或 max-snippet:0 會讓搜尋結果不顯示摘要；Google 說明這些摘要控制"
                    "也適用於"
                    "其搜尋中的 AI 功能，因此內文較難被直接引用。"
                ),
                remediation=(
                    "若希望內容能被引用，移除 nosnippet／max-snippet:0，只對確實不想被引用的段落使"
                    "用 data-nosnippet。"
                ),
                evidence=f"{url}\n摘要指令：{source_text}",
                impact_area="answer_engine",
                evidence_json={"url": url, "directives": directives},
            )
        )

    nosnippet_blocks = nosnippet_block_count(page_input.html)
    if nosnippet_blocks:
        findings.append(
            make_finding(
                category=Finding.Category.AEO,
                severity=Finding.Severity.INFO,
                rule_id="aeo-data-nosnippet",
                title="部分段落標記為不可摘要（data-nosnippet）",
                description=(
                    f"此頁有 {nosnippet_blocks} 個元素標了 data-nosnippet，這些段落不會被用作摘要。"
                    "請確認其中沒有訪客常問的答案（例如價格、期限、聯絡方式）。"
                ),
                remediation="只對確實不想被引用的內容保留 data-nosnippet。",
                evidence=f"{url}\ndata-nosnippet 元素：{nosnippet_blocks} 個",
                impact_area="answer_engine",
            )
        )

    if parser.json_ld_blocks:
        content = extract_page_content(url, page_input.html)
        visible = "\n".join(p.text for p in content.passages)
        issues = check_markup(parser.json_ld_blocks, visible)
        syntax = [i for i in issues if i["kind"] == "syntax"]
        mismatch = [i for i in issues if i["kind"] == "mismatch"]
        if syntax:
            findings.append(
                make_finding(
                    category=Finding.Category.AEO,
                    severity=Finding.Severity.MEDIUM,
                    rule_id="aeo-markup-syntax",
                    title="結構化資料（JSON-LD）有語法錯誤，整段會被忽略",
                    description="JSON-LD 解析失敗時，搜尋引擎會忽略整個區塊，裡面的資訊等於沒寫。",
                    remediation=(
                        "修正 JSON 語法（常見：多餘逗號、未跳脫的引號），再用 Google 複合式搜尋結果"
                        "測試工具驗證。"
                    ),
                    evidence="\n".join(
                        f"{i['field']}：{i['detail']}；開頭：{i['value']}" for i in syntax
                    )[:1500],
                    impact_area="answer_engine",
                    evidence_json={"url": url, "issues": syntax},
                )
            )
        if mismatch:
            findings.append(
                make_finding(
                    category=Finding.Category.AEO,
                    severity=Finding.Severity.LOW,
                    rule_id="aeo-markup-mismatch",
                    title="結構化資料的內容與頁面可見文字不一致",
                    description=(
                        "結構化資料應描述頁面上看得到的內容。標記裡有、頁面上看不到的問答或聯絡"
                        "資訊，"
                        "可能被視為不一致而不被採用，也會讓答案來源無法追溯。"
                    ),
                    remediation="讓標記內容與頁面可見文字一致：更新標記，或把對應內容放到頁面上。",
                    evidence="\n".join(
                        f"{i['field']}「{i['value']}」：{i['detail']}" for i in mismatch
                    )[:1500],
                    impact_area="answer_engine",
                    evidence_json={"url": url, "issues": mismatch},
                )
            )
    return findings
