"""Trust Stack 五層信任分（2026-10-10，借鑑 GeoReady/geo-optimizer-skill MIT 的 trust_stack）。

把 Argus **已經算出來**的訊號換個角度聚合成「AI／搜尋引擎眼中的可信度輪廓」，分五層。
**不產生問題、不改分數、不發請求**，和 observatory（安全標頭等第）一樣是資訊參考，呈現在
「網站架構」與報告。輸入只用既有的 observatory 分數與本次 findings 的規則代號（不重新偵測）。

- 技術信任：HTTPS／安全標頭（直接取 observatory 分數）
- 身分信任：組織結構化資料、文章作者
- 社群信任：sameAs（連到維基／社群）
- 學術信任：權威來源引用、量化數據（接 geo_citability）
- 一致性信任：有日期、無索引訊號矛盾、無多頁同標題、內容不易過時

每層只在對應維度有掃到時才評分（否則「未評估」）；總分為已評估各層的平均。
"""

from __future__ import annotations

TOOL = "argus-trust-stack-v1"

# 各層：(代號, 標籤, 需要的維度, [(扣分, 出現即扣的規則代號前綴/完整代號)])
# 分數 = 100 − 命中規則的扣分合計，下限 0。前綴以 "*" 結尾表示 startswith。
_LAYERS = [
    ("identity", "身分信任", "geo", [
        (40, "geo-entity-organization-missing"),
        (30, "geo-article-author-missing"),
    ]),
    ("social", "社群信任", "geo", [
        (40, "geo-entity-no-same-as"),
    ]),
    ("academic", "學術信任", "geo", [
        (45, "geo-citability-no-sources"),
        (25, "geo-citability-no-statistics"),
    ]),
    ("consistency", "一致性信任", "geo", [
        (25, "geo-article-date-missing"),
        (20, "geo-article-date-invalid"),
        (20, "geo-article-date-inconsistent"),
        (20, "geo-content-decay"),
        (20, "seo-index-signals-conflict"),
        (20, "seo-duplicate-titles"),
    ]),
]

_GRADE_BANDS = ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (0, "F"))


def _grade(score: int) -> str:
    for threshold, letter in _GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


def evaluate(
    *,
    findings_rules: set[str],
    observatory: dict | None,
    categories: set[str],
) -> dict:
    """回傳 {tool, overall_score, overall_grade, layers:[...]}；沒有任何一層可評估時回空 dict。

    每個 layer＝{key,label,score,grade,evaluated,reasons}。"""
    layers: list[dict] = []

    # 技術層：直接沿用 observatory 分數（已涵蓋 HTTPS／HSTS／CSP 等）
    obs_score = (observatory or {}).get("score")
    tech_evaluated = "security" in categories and isinstance(obs_score, int)
    layers.append({
        "key": "technical",
        "label": "技術信任",
        "evaluated": tech_evaluated,
        "score": obs_score if tech_evaluated else None,
        "grade": _grade(obs_score) if tech_evaluated else "",
        "reasons": ["沿用安全標頭參考等第（observatory）"] if tech_evaluated else [],
    })

    for key, label, dim, rules in _LAYERS:
        evaluated = dim in categories
        if not evaluated:
            layers.append({"key": key, "label": label, "evaluated": False,
                           "score": None, "grade": "", "reasons": []})
            continue
        penalty = 0
        reasons: list[str] = []
        for weight, rule in rules:
            if rule in findings_rules:
                penalty += weight
                reasons.append(rule)
        score = max(0, 100 - penalty)
        layers.append({"key": key, "label": label, "evaluated": True,
                       "score": score, "grade": _grade(score), "reasons": reasons})

    scored = [item["score"] for item in layers if item["evaluated"]]
    if not scored:
        return {}
    overall = round(sum(scored) / len(scored))
    return {
        "tool": TOOL,
        "overall_score": overall,
        "overall_grade": _grade(overall),
        "layers": layers,
    }


def summary_line(trust_stack: dict) -> str:
    """報告「網站架構」用的一行摘要。"""
    if not trust_stack:
        return ""
    parts = [
        f"{item['label']} {item['score']}（{item['grade']}）"
        for item in trust_stack.get("layers", [])
        if item.get("evaluated")
    ]
    if not parts:
        return ""
    return (
        f"信任輪廓總分 {trust_stack['overall_score']}（{trust_stack['overall_grade']}）："
        + "、".join(parts)
        + "。此為既有訊號的聚合參考，不計入 Argus 分數。"
    )
