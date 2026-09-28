"""AEO 第 4 層：結構化資料是否正確、是否與頁面可見文字一致。

只檢查網站**已經有**的標記；不因為沒有 FAQPage／HowTo 就要求補上——Google 已停止顯示
FAQ 複合搜尋結果，「補了 FAQ Schema 就更容易出現在 AI 答案」不能當成結論。
"""

from __future__ import annotations

import json
import re

_NORMALIZE = re.compile(r"[\s\W_]+", re.UNICODE)
_DIGITS = re.compile(r"\D+")


def _norm(text: str) -> str:
    return _NORMALIZE.sub("", text or "").lower()


def _iter_nodes(data):
    """展開 JSON-LD（list、@graph、巢狀物件）成節點序列。"""
    if isinstance(data, list):
        for item in data:
            yield from _iter_nodes(item)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in data:
                yield from _iter_nodes(data[key])


def _types(node: dict) -> set[str]:
    raw = node.get("@type", [])
    raw = raw if isinstance(raw, list) else [raw]
    return {str(t).lower() for t in raw}


def _answer_text(question: dict) -> str:
    answer = question.get("acceptedAnswer") or question.get("suggestedAnswer") or {}
    if isinstance(answer, list):
        answer = answer[0] if answer else {}
    text = answer.get("text", "") if isinstance(answer, dict) else ""
    return re.sub(r"<[^>]+>", " ", str(text))


def _visible(fragment: str, visible_norm: str, prefix: int = 16) -> bool:
    """標記內容的開頭（去掉空白與標點）是否出現在頁面可見文字中。"""
    probe = _norm(fragment)[:prefix]
    return bool(probe) and probe in visible_norm


def check_markup(json_ld_blocks: list[str], visible_text: str) -> list[dict]:
    """回傳問題清單：{"kind": "syntax"|"mismatch", "field", "value", "detail"}。"""
    issues: list[dict] = []
    visible_norm = _norm(visible_text)
    visible_digits = _DIGITS.sub("", visible_text or "")
    for index, block in enumerate(json_ld_blocks, start=1):
        try:
            data = json.loads(block)
        except (ValueError, TypeError) as exc:
            issues.append(
                {
                    "kind": "syntax",
                    "field": f"第 {index} 個 JSON-LD 區塊",
                    "value": block.strip()[:120],
                    "detail": f"JSON 語法錯誤：{exc}",
                }
            )
            continue
        for node in _iter_nodes(data):
            types = _types(node)
            if "question" in types:
                name = str(node.get("name", ""))
                if name and not _visible(name, visible_norm):
                    issues.append(
                        {
                            "kind": "mismatch",
                            "field": "FAQPage 問題（Question.name）",
                            "value": name[:120],
                            "detail": "頁面可見文字中找不到這個問題",
                        }
                    )
                answer = _answer_text(node)
                if answer.strip() and not _visible(answer, visible_norm, prefix=20):
                    issues.append(
                        {
                            "kind": "mismatch",
                            "field": "FAQPage 答案（acceptedAnswer.text）",
                            "value": answer.strip()[:120],
                            "detail": "頁面可見文字中找不到這段答案",
                        }
                    )
            telephone = node.get("telephone")
            if isinstance(telephone, str) and telephone.strip():
                digits = _DIGITS.sub("", telephone)[-8:]
                if digits and digits not in visible_digits:
                    issues.append(
                        {
                            "kind": "mismatch",
                            "field": "telephone",
                            "value": telephone[:60],
                            "detail": "頁面可見文字中沒有這支電話",
                        }
                    )
            email = node.get("email")
            if isinstance(email, str) and "@" in email:
                if email.replace("mailto:", "").strip().lower() not in (visible_text or "").lower():
                    issues.append(
                        {
                            "kind": "mismatch",
                            "field": "email",
                            "value": email[:80],
                            "detail": "頁面可見文字中沒有這個 Email",
                        }
                    )
    return issues
