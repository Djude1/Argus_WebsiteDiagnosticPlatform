"""AI 爬蟲的 robots.txt 政策（roadmap §10 第 1 項、第 9 項之四）。

把常見 AI 爬蟲依用途分成三類，逐一判斷 robots.txt 對它們的規則，讓網站主看清楚商業取捨：

- **訓練**（training）：抓內容訓練模型，例如 GPTBot、ClaudeBot、Google-Extended、CCBot。封鎖是正當的
  商業選擇，**不影響**這些公司的搜尋或 AI 回答引用
  （例如 Google-Extended 不影響 Google 搜尋與 AI 摘要）。
- **AI 搜尋**（search）：建立 AI 搜尋／回答的索引，
  例如 OAI-SearchBot、Claude-SearchBot、PerplexityBot。
  封鎖後，這些服務的回答比較不會引用、連結到你的網站。
- **使用者觸發**（user）：使用者在對話中要求讀取某個網頁時才發出，例如 ChatGPT-User。依廠商說明，
  這類請求不一定遵守 robots.txt。

規則比對依 RFC 9309：robots.txt 有點名這個 bot 的群組就只用該群組，否則用 `*`；
Allow／Disallow 取路徑
最長的那條，一樣長時 Allow 優先。只判斷首頁（`/`）是否允許，另記錄是否有其他 Disallow（部分限制）。
只分析爬蟲已讀到的 robots.txt，不另發請求。
"""

from __future__ import annotations

import re

TRAINING = "training"
SEARCH = "search"
USER = "user"
PURPOSE_LABELS = {
    TRAINING: "模型訓練",
    SEARCH: "AI 搜尋與回答",
    USER: "使用者觸發讀取",
}

# (User-Agent 產品名稱, 廠商, 用途, 補充說明)
AI_BOTS: tuple[tuple[str, str, str, str], ...] = (
    ("GPTBot", "OpenAI", TRAINING, ""),
    ("ClaudeBot", "Anthropic", TRAINING, ""),
    ("Google-Extended", "Google", TRAINING,
     "只控制 Gemini 等模型的訓練與使用，不影響 Google 搜尋與 AI 摘要"),
    ("Applebot-Extended", "Apple", TRAINING, "不影響 Siri、Spotlight 等搜尋功能"),
    ("CCBot", "Common Crawl", TRAINING, "公開資料集，常被拿來訓練各家模型"),
    ("Meta-ExternalAgent", "Meta", TRAINING, ""),
    ("Bytespider", "ByteDance", TRAINING, ""),
    ("OAI-SearchBot", "OpenAI", SEARCH, "ChatGPT 搜尋"),
    ("Claude-SearchBot", "Anthropic", SEARCH, "Claude 的網路搜尋"),
    ("PerplexityBot", "Perplexity", SEARCH, ""),
    ("ChatGPT-User", "OpenAI", USER, ""),
    ("Claude-User", "Anthropic", USER, ""),
    ("Perplexity-User", "Perplexity", USER, ""),
)

ALLOWED = "allowed"
PARTIAL = "partial"
BLOCKED = "blocked"
STATUS_LABELS = {ALLOWED: "允許", PARTIAL: "部分限制", BLOCKED: "封鎖整個網站"}


def parse_groups(robots_text: str) -> list[tuple[set[str], list[tuple[bool, str]]]]:
    """robots.txt → [(user-agent 集合（小寫）, [(是否 Allow, 路徑)])]。

    連續的 User-agent 行屬同一群組。
    """
    groups: list[tuple[set[str], list[tuple[bool, str]]]] = []
    agents: set[str] = set()
    rules: list[tuple[bool, str]] = []
    last_was_agent = False
    for raw in robots_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if not last_was_agent and agents:
                groups.append((agents, rules))
                agents, rules = set(), []
            agents.add(value.lower())
            last_was_agent = True
        elif key in {"allow", "disallow"}:
            if agents:
                rules.append((key == "allow", value))
            last_was_agent = False
        else:
            last_was_agent = False
    if agents:
        groups.append((agents, rules))
    return groups


def _pattern(path: str) -> re.Pattern:
    regex = re.escape(path).replace(r"\*", ".*")
    if regex.endswith(r"\$"):
        regex = regex[:-2] + "$"
    return re.compile(regex)


def _allowed(rules: list[tuple[bool, str]], url_path: str) -> bool:
    best: tuple[int, bool] | None = None
    for allow, path in rules:
        if not path:  # 空的 Disallow＝允許全部，不參與比對
            continue
        if _pattern(path).match(url_path):
            candidate = (len(path), allow)
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and allow):
                best = candidate
    return True if best is None else best[1]


def _rules_for(groups, token: str) -> tuple[list[tuple[bool, str]], bool]:
    """回傳 (適用的規則, 是否有點名這個 bot)。"""
    name = token.lower()
    named = [rules for agents, rules in groups if name in agents]
    if named:
        return [r for rules in named for r in rules], True
    wildcard = [rules for agents, rules in groups if "*" in agents]
    return [r for rules in wildcard for r in rules], False


def analyze_policy(robots_text: str | None) -> dict:
    """{robots_found, bots: [{agent, vendor, purpose, note, status, explicit}]}。

    robots_text 為 None＝沒有 robots.txt。
    """
    groups = parse_groups(robots_text or "")
    bots = []
    for agent, vendor, purpose, note in AI_BOTS:
        rules, explicit = _rules_for(groups, agent)
        if not _allowed(rules, "/"):
            status = BLOCKED
        elif any(not allow and path for allow, path in rules):
            status = PARTIAL
        else:
            status = ALLOWED
        bots.append({
            "agent": agent, "vendor": vendor, "purpose": purpose, "note": note,
            "status": status, "explicit": explicit,
        })
    return {"robots_found": robots_text is not None, "bots": bots}


def blocked(policy: dict, *purposes: str) -> list[dict]:
    return [
        b for b in (policy or {}).get("bots") or []
        if b["status"] == BLOCKED and (not purposes or b["purpose"] in purposes)
    ]


def summary_line(policy: dict) -> str:
    """報告「網站架構」表的一列。"""
    if not policy or not policy.get("bots"):
        return ""
    if not policy.get("robots_found"):
        return "沒有 robots.txt，所有 AI 爬蟲都可抓取"
    parts = []
    for purpose, label in PURPOSE_LABELS.items():
        names = [b["agent"] for b in blocked(policy, purpose)]
        parts.append(f"{label}：" + ("封鎖 " + "、".join(names) if names else "未封鎖"))
    return "；".join(parts)
