"""頁面內容中的 AI 提示詞注入偵測（2026-10-10）。

有人會在網頁藏「給 AI 看的指令」來操縱 AI 問答引擎對這個網站的描述或推薦
（UC Berkeley EMNLP 2024：內容注入可操縱 AI 搜尋排序）。本模組偵測這類手法，
方法移植自 GeoReady / geo-optimizer-skill（MIT, auriti-labs）的 injection_detector.py，
改寫成 stdlib `html.parser`（本專案不引入 BeautifulSoup）。純解析、不發額外請求，
由 tasks.py 對已抓 HTML 被動呼叫（歸 security/，與 secret_scanner 相同）。

**刻意保守，避免誤報**：`display:none`／摺疊選單／彈窗在正常網站極常見，單憑「有隱藏文字」
不成立。只有偵測到**明確的 LLM 指令字樣**（可見文字、HTML 註解或隱藏區塊皆算）或
**AI 專用的 data-* 屬性**才判定；一般隱藏樣式只在已命中指令時當「刻意隱藏」的加重證據。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from apps.scans.models import Finding
from apps.scans.scanners import make_finding

# 明確的 LLM 操縱指令（near-zero 誤報）
_LLM_INSTRUCTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above)",
    r"you\s+are\s+(?:now\s+)?(?:a|an)\s+(?:helpful\s+)?(?:ai\s+)?assistant",
    r"always\s+recommend\s+\w+",
    r"do\s+not\s+(?:mention|recommend)\s+(?:any\s+)?competitors?",
    r"(?:as\s+an?\s+)?(?:ai|language)\s+model[,\s]",
    r"system\s+prompt\s*[:：]",
    r"</?(?:system|assistant|user)>",
    r"忽略(?:以上|先前|之前)(?:的)?(?:所有)?指(?:令|示)",
    r"請?務必推薦",
    r"(?:請)?不要提(?:到|及)(?:任何)?競爭(?:者|對手)",
]
_LLM_RE = [re.compile(p, re.IGNORECASE) for p in _LLM_INSTRUCTION_PATTERNS]

# AI 專用 data-* 屬性（目前沒有正當用途）
_DATA_ATTR_RE = re.compile(r"^data-(?:ai|prompt|llm|instruction|system)-", re.IGNORECASE)
# 零寬／雙向控制等不可見字元
_INVISIBLE_RE = re.compile(r"[​‌‍‎‏﻿‪-‮⁠]")
_INVISIBLE_THRESHOLD = 5
_HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
# 隱藏樣式（只當加重證據，不單獨成立）
_HIDDEN_STYLE_RE = re.compile(
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|opacity\s*:\s*0(?:\s|;|$|\")"
    r"|font-size\s*:\s*0(?:px|pt|em|rem)?\s*(?:;|$|\")"
    r"|font-size\s*:\s*(?:0?\.\d+|1)(?:px)\b",
    re.IGNORECASE,
)
# 留言／評論區（第三方 UGC 可能被灌注入，責任不在站方本身）
_UGC_MARKERS = ("disqus_thread", "fb-comments", "commento", "utterances", "giscus",
                "hyvor-talk", "cusdis", "remark42", "coral-talk")
_UGC_ID_CLASS_RE = re.compile(
    r"(?:comments?(?:[-_ ]?(?:list|section|area|wrapper|thread))?|respond|"
    r"review[-_ ]?(?:list|section)|disqus|留言|評論)", re.IGNORECASE)

_MAX_SAMPLES = 3
_SAMPLE_LEN = 150


def _truncate(text: str) -> str:
    text = " ".join(text.split())
    return text[:_SAMPLE_LEN] + "…" if len(text) > _SAMPLE_LEN else text


class _InjectionParser(HTMLParser):
    """收集隱藏區塊文字、可見文字、AI data-* 屬性、UGC 標記。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.visible_text: list[str] = []
        self.hidden_text: list[str] = []
        self.data_attrs: list[str] = []
        self.ugc_present = False
        self._hidden_depth = 0
        self._skip_depth = 0  # script/style 內容不算文字

    def handle_starttag(self, tag, attrs):
        attr_map = {k: (v or "") for k, v in attrs}
        for name in attr_map:
            if _DATA_ATTR_RE.match(name) and name not in self.data_attrs:
                self.data_attrs.append(name)
        ident = f"{attr_map.get('id', '')} {attr_map.get('class', '')}"
        if any(m in ident.lower() for m in _UGC_MARKERS) or _UGC_ID_CLASS_RE.search(ident):
            self.ugc_present = True
        hidden = (
            attr_map.get("aria-hidden", "").lower() == "true"
            or attr_map.get("hidden") is not None
            or bool(_HIDDEN_STYLE_RE.search(attr_map.get("style", "")))
        )
        if tag in ("script", "style"):
            self._skip_depth += 1
        if self._hidden_depth or hidden:
            self._hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        if self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._hidden_depth:
            self.hidden_text.append(text)
        else:
            self.visible_text.append(text)


def _instruction_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pat in _LLM_RE:
        for m in pat.finditer(text):
            start, end = max(0, m.start() - 20), min(len(text), m.end() + 20)
            hits.append(_truncate(text[start:end]))
            if len(hits) >= _MAX_SAMPLES:
                return hits
    return hits


def detect_content_injection(html: str) -> dict:
    """回傳偵測結果。不產生 finding（由 build_injection_finding 轉）。"""
    html = html or ""
    result: dict = {
        "instruction_samples": [],
        "concealed": False,
        "in_comment": False,
        "data_attrs": [],
        "invisible_unicode": 0,
        "ugc_present": False,
    }
    if not html:
        return result

    parser = _InjectionParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    samples: list[str] = []
    # 1. 可見文字裡的指令
    visible = "\n".join(parser.visible_text)
    samples += _instruction_hits(visible)
    # 2. 隱藏區塊裡的指令（= 刻意隱藏）
    hidden_hits = _instruction_hits("\n".join(parser.hidden_text))
    if hidden_hits:
        result["concealed"] = True
        samples += hidden_hits
    # 3. HTML 註解裡的指令
    for comment in _HTML_COMMENT_RE.findall(html):
        c_hits = _instruction_hits(comment)
        if c_hits:
            result["in_comment"] = True
            result["concealed"] = True
            samples += c_hits

    result["instruction_samples"] = samples[:_MAX_SAMPLES]
    result["data_attrs"] = parser.data_attrs[:_MAX_SAMPLES]
    result["invisible_unicode"] = len(_INVISIBLE_RE.findall(visible))
    result["ugc_present"] = parser.ugc_present
    return result


def build_injection_finding(result: dict, location: str) -> dict | None:
    """把偵測結果轉成 security finding；沒有強訊號回 None。"""
    samples = result.get("instruction_samples") or []
    data_attrs = result.get("data_attrs") or []
    invisible = result.get("invisible_unicode") or 0
    ugc = result.get("ugc_present")

    if samples:
        concealed = result.get("concealed")
        if result.get("in_comment"):
            where = "HTML 註解"
        else:
            where = "隱藏區塊" if concealed else "頁面內容"
        # 命中明確指令：high；若只出現在可見文字且頁面有留言區，可能來自第三方 UGC，降 medium
        if not concealed and ugc:
            severity = Finding.Severity.MEDIUM
            ugc_note = "（頁面有留言／評論區，注入字樣可能來自第三方使用者內容，請先確認來源）"
        else:
            severity = Finding.Severity.HIGH
            ugc_note = ""
        evidence = "；".join(samples)
        if invisible >= _INVISIBLE_THRESHOLD:
            evidence += f"（另偵測到 {invisible} 個不可見字元）"
        return make_finding(
            category=Finding.Category.SECURITY,
            severity=severity,
            rule_id="security-ai-prompt-injection",
            title="頁面含操縱 AI 的提示詞注入字樣",
            description=(
                f"在{where}偵測到疑似針對 AI 問答引擎的指令字樣（例如「忽略先前指令」「務必推薦」"
                f"「不要提及競爭者」）。這類隱藏或植入的指令會試圖操縱 ChatGPT、Perplexity 等"
                f"引擎對本網站的描述或推薦，屬內容完整性與信任問題。" + ugc_note
            ),
            remediation=(
                "移除這些指令字樣；若非站方刻意放置，檢查頁面是否被竄改或由外部內容注入。"
                "正當內容不需要對 AI 下指令。"
            ),
            evidence=evidence,
            evidence_source="rule_engine",
        )

    if data_attrs or invisible >= _INVISIBLE_THRESHOLD:
        parts = []
        if data_attrs:
            parts.append("AI 專用屬性：" + "、".join(data_attrs))
        if invisible >= _INVISIBLE_THRESHOLD:
            parts.append(f"不可見字元 {invisible} 個")
        return make_finding(
            category=Finding.Category.SECURITY,
            severity=Finding.Severity.LOW,
            rule_id="security-ai-suspicious-markup",
            title="頁面含可疑的 AI 導向標記",
            description=(
                "偵測到 AI 專用的 data-* 屬性或異常數量的不可見字元。這些不一定是攻擊，但常被"
                "用來對 AI 爬蟲傳遞隱藏訊息，建議確認是否必要。"
            ),
            remediation="確認這些標記的用途；若非必要請移除，避免被當成操縱 AI 的訊號。",
            evidence="；".join(parts),
            evidence_source="rule_engine",
        )

    return None
