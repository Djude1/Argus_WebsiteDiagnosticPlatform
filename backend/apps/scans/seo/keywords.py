"""目標關鍵字：沒有 GSC 時，檢查使用者設定的關鍵字有沒有出現在頁面的重要位置。

只做字面比對（不分大小寫、全形空白視為空白）；中文不斷詞，以子字串判斷。
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

MAX_KEYWORDS = 20
MAX_KEYWORD_CHARS = 60
_WS = re.compile(r"[\s　]+")

# 出現位置與權重：Title 與 H1 最重要
PLACES = (
    ("title", "Title", 3),
    ("h1", "H1", 3),
    ("description", "Description", 2),
    ("headings", "H2–H6", 1),
    ("url", "網址", 1),
    ("body", "正文", 1),
)


def normalize_keywords(raw) -> list[str]:
    """清理使用者輸入：去頭尾空白、合併空白、去重（不分大小寫），超過上限的丟棄。"""
    if not isinstance(raw, list):
        raise ValueError("keywords 必須是字串清單。")
    seen: set[str] = set()
    keywords: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("keywords 必須是字串清單。")
        keyword = _WS.sub(" ", item).strip()
        if not keyword:
            continue
        if len(keyword) > MAX_KEYWORD_CHARS:
            raise ValueError(f"每個關鍵字最多 {MAX_KEYWORD_CHARS} 字。")
        key = keyword.casefold()
        if key not in seen:
            seen.add(key)
            keywords.append(keyword)
    if len(keywords) > MAX_KEYWORDS:
        raise ValueError(f"最多設定 {MAX_KEYWORDS} 個關鍵字。")
    return keywords


def _norm(text: str) -> str:
    return _WS.sub(" ", text or "").casefold()


def _places(audit: dict) -> dict[str, str]:
    path = unquote(urlsplit(audit["final_url"]).path).replace("-", " ").replace("_", " ")
    return {
        "title": _norm(audit["title"]),
        "h1": _norm(" ".join(audit["h1"])),
        "description": _norm(audit["description"]),
        "headings": _norm(" ".join(h["text"] for h in audit["headings"] if h["level"] > 1)),
        "url": _norm(path),
        "body": _norm(audit["main_text"]),
    }


def keyword_report(keywords: list[str], audits: list[dict]) -> list[dict]:
    """每個關鍵字：出現在哪些頁、哪些位置、最相關的頁面與建議。"""
    page_places = [(audit, _places(audit)) for audit in audits if audit["status_code"] == 200]
    report = []
    for keyword in keywords:
        needle = _norm(keyword)
        pages = []
        for audit, places in page_places:
            found = [label for key, label, _w in PLACES if needle in places[key]]
            if not found:
                continue
            score = sum(w for key, _label, w in PLACES if needle in places[key])
            pages.append({
                "page_id": audit["page_id"],
                "url": audit["final_url"],
                "title": audit["title"],
                "places": found,
                "body_count": places["body"].count(needle),
                "score": score,
            })
        pages.sort(key=lambda p: (-p["score"], -p["body_count"], p["url"]))
        best = pages[0] if pages else None
        if not pages:
            advice = "沒有任何頁面提到這個關鍵字；若是重要主題，建立專門的頁面。"
        elif not ({"Title", "H1"} & set(best["places"])):
            advice = "有頁面提到，但沒有出現在 Title 或 H1；在最相關頁面的標題中自然地加入。"
        else:
            advice = ""
        report.append({
            "keyword": keyword,
            "pages_found": len(pages),
            "best_page": best,
            "pages": pages[:10],
            "advice": advice,
        })
    return report
