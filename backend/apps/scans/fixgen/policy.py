"""事實政策三級驗證（spec：docs/specs/0002-fix-output.md）。

產生後強制執行的驗證步驟——LLM 越界輸出會在這裡被攔截取代：

- 識別類（機構名、地址、電話、社群連結、圖片網址）：值必須出現在爬取
  語料中，不符即取代為統一樣式的佔位符【請填寫：…】。
- 結構類（@context、og:type、og:url、twitter:card）：由規則推導，免驗證。
- 文案類（meta description、FAQ 答案、llms.txt 摘要）：只能改寫爬到的
  內文；硬事實（數字、網址、email）不在語料即視為新增事實，整欄退回
  爬取內容的逐字摘錄（extracted）。
"""

from __future__ import annotations

import re

from apps.scans.fixgen.facts import CrawledFacts, normalize_for_match

PLACEHOLDER = "【請填寫：{label}】"

# 硬事實 token：URL / email / 含數字的連續片段（百分比、年份、數量）
_HARD_FACT_RE = re.compile(r"https?://[^\s\"'<>）)，。；]+|[\w.+-]+@[\w.-]+\.\w+|\d[\d,，.%]*\d|\d")


def identity_field(
    facts: CrawledFacts, value: str, label: str
) -> tuple[str, dict]:
    """驗證識別類欄位：語料可支撐 → 原值＋verified；否則 → 佔位符。"""
    value = (value or "").strip()
    if value and normalize_for_match(value) in facts.corpus_norm:
        return value, {"status": "verified", "source_url": find_source_url(facts, value)}
    return PLACEHOLDER.format(label=label), {"status": "placeholder"}


def find_source_url(facts: CrawledFacts, value: str) -> str | None:
    """回傳第一個文字內容包含此值的頁面 URL（來源頁標註用）。"""
    normalized = normalize_for_match(value)
    for page in facts.pages:
        if normalized in normalize_for_match(" ".join(page.lines)):
            return page.url
    return None


def copy_field(
    facts: CrawledFacts, value: str, label: str
) -> tuple[str, dict]:
    """驗證文案類欄位：硬事實全部可在語料找到 → 原值；否則退回逐字摘錄。"""
    value = (value or "").strip()
    if value and not new_hard_facts(value, facts):
        return value, {
            "status": "verified",
            "source_url": facts.home.url if facts.home else None,
        }
    fallback = extractive_description(facts)
    if fallback:
        return fallback, {
            "status": "extracted",
            "source_url": facts.home.url if facts.home else None,
        }
    # 連退回內容都沒有（首頁沒文字）→ 佔位符
    return PLACEHOLDER.format(label=label), {"status": "placeholder"}


def new_hard_facts(text: str, facts: CrawledFacts) -> list[str]:
    """列出不在語料中的硬事實 token；空清單＝文案未新增事實。"""
    problems = []
    for token in _HARD_FACT_RE.findall(text or ""):
        token = token.rstrip(".,;、。")
        if not token:
            continue
        if normalize_for_match(token) not in facts.corpus_norm:
            problems.append(token)
    return problems


def extractive_description(facts: CrawledFacts) -> str:
    """文案驗證失敗時的逐字摘錄：首頁 meta description 優先，其次首頁首段文字。"""
    if facts.meta_description:
        return facts.meta_description
    if facts.home:
        text = " ".join(line for line in facts.home.lines if len(line) > 10)
        if text:
            return text[:120].rstrip() + ("…" if len(text) > 120 else "")
    return ""
