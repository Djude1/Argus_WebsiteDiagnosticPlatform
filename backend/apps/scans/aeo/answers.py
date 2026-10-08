"""AEO 第 2 層（下）與第 3 層：在已掃描的頁面中找答案段落，並判斷答案是否可用。

判定只有四種，每一種都附原文證據：

- answered：找到含具體答案值（電話、日期、金額、步驟…）的段落
- insufficient：提到相關主題，但沒有具體答案（只有宣傳語、日期沒寫年度…）
- conflict：不同頁面給出互相矛盾的答案（截止日期、同一項目的價格、營業時間、客服專線；
  其餘多值多半是正常情況，見 _value_conflict）
- missing：整站找不到提到這個主題的段落

規則刻意保守：寧可判「資訊不足」讓站方確認，也不把模糊內容當成答案。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.scans.aeo import questions as q
from apps.scans.aeo.content import Passage
from apps.scans.evidence import contacts

ANSWERED = "answered"
INSUFFICIENT = "insufficient"
CONFLICT = "conflict"
MISSING = "missing"

VERDICT_LABELS = {
    ANSWERED: "可回答",
    INSUFFICIENT: "資訊不足",
    CONFLICT: "內容衝突",
    MISSING: "無可用答案",
}
# 答案可信度（roadmap §2 AEO 第 4 項）：可回答與內容衝突才有，說明規則確認到什麼程度
CONFIRMED = "confirmed"
LIKELY = "likely"
POSSIBLE = "possible"
CONFIDENCE_LABELS = {CONFIRMED: "確認", LIKELY: "可能", POSSIBLE: "推測"}
CONFIDENCE_LIMITS = {
    CONFIRMED: "答案值（號碼、金額、時間、日期等）逐字出現在引用的原文中；仍需確認是否為最新資訊。",
    LIKELY: "依規則判斷段落列出步驟或條件，或位於網站自己的問題標題下方；未逐字核對答案是否完整。",
    POSSIBLE: "只確認相關段落有具體敘述，規則無法判斷是否真的回答了問題，建議人工確認。",
}
# 答案值有固定格式、能逐字比對的題型
_EXACT_TYPES = {q.PHONE, q.EMAIL, q.ADDRESS, q.HOURS, q.PRICE, q.DATE, q.DURATION, q.PAYMENT}

# 計分：可回答 1、資訊不足 0.5、內容衝突 0.25、無答案 0
VERDICT_VALUE = {ANSWERED: 1.0, INSUFFICIENT: 0.5, CONFLICT: 0.25, MISSING: 0.0}

# 聯絡類問題可以用頁尾內容回答；其餘只看正文
_FOOTER_OK = {q.PHONE, q.EMAIL, q.ADDRESS, q.HOURS}
MAX_CANDIDATES = 3
_QUOTE_RADIUS = 70

# ---------- 答案值 ----------

# Email 與電話的格式與資安共用（evidence/contacts.py，P0-B），兩邊對同一頁的判斷才會一致
_PHONE = contacts.PHONE_PATTERN
_EMAIL = contacts.EMAIL_PATTERN
_ADDRESS = re.compile(
    r"(?:[一-鿿]{1,4}[縣市])?[一-鿿]{1,4}[區鄉鎮市]"
    r"[一-鿿\d]{0,12}(?:路|街|大道)(?:[一二三四五六七八九十\d]+段)?"
    r"(?:[\d一二三四五六七八九十]+巷)?(?:[\d一二三四五六七八九十]+弄)?\d+(?:之\d+)?號"
    r"|\d{1,5}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Blvd\.?)",
)
_HOURS = re.compile(
    r"\d{1,2}[:：]\d{2}\s*(?:[-~–—至到]|to)\s*\d{1,2}[:：]\d{2}"
    r"|(?:週|星期|周)[一二三四五六日天]\s*(?:[-~–—至到])\s*(?:週|星期|周)?[一二三四五六日天]"
    r"|(?:上午|下午|早上|晚上)\s*\d{1,2}\s*[點時:：]",
)
_PRICE = re.compile(
    r"(?:NT\$|NTD|新臺幣|新台幣|US\$|USD|\$)\s?\d[\d,]*(?:\.\d+)?"
    r"|\d[\d,]*(?:\.\d+)?\s?(?:元|塊)(?!素)",
    re.IGNORECASE,
)
_DATE_WITH_YEAR = re.compile(
    r"(?:\d{4}|民國\s?\d{2,3}|\d{3})\s?[年/.-]\s?\d{1,2}\s?[月/.-]\s?\d{1,2}\s?日?"
    r"|(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}",
    re.IGNORECASE,
)
_DATE_NO_YEAR = re.compile(r"(?<![\d年/.-])\d{1,2}\s?月\s?\d{1,2}\s?日")
_DURATION = re.compile(
    r"\d+\s?(?:[-~–至到]\s?\d+\s?)?(?:個)?"
    r"(?:工作天|工作日|天|日|小時|週|星期|business days?|days?|hours?)",
    re.IGNORECASE,
)
_STEP_MARKERS = re.compile(
    r"步驟|第[一二三四五1-5]步|首先|接著|然後|最後|step\s?\d|^\s*\d+[.、)]", re.IGNORECASE
)
_STEP_VERBS = re.compile(
    r"填寫|上傳|繳交|送出|點選|登入|下載|選擇|註冊|提交|寄送|完成|submit|upload|fill|register|click",
    re.IGNORECASE,
)
_CRITERIA = re.compile(
    r"年滿\s?\d+|\d+\s?歲|學歷|畢業|具備|持有|設籍|國籍|年資|應屆|\d+\s?(?:天|日)內"
    r"|鑑賞期|不得|須|需|限|至少|以上|以下|或同等",
)
_VAGUE = re.compile(
    r"詳情請|歡迎(?:來電|洽詢|聯絡)|請洽|請來電|敬請期待|另行公告|最優質|一流|頂尖|值得信賴|用心|最專業|"
    r"更多資訊|如有疑問|請見|請參考|contact us for|learn more"
    # 感謝詞不是答案（網站自己的問句底下只放一句感謝，2026-10-07 回歸資料集）
    r"|感謝您|謝謝您|支持與愛護|持續努力|敬請見諒",
    re.IGNORECASE,
)
_CONDITIONAL = re.compile(r"如需|若需|如須|若須|如有需要|若有需要")
_DEADLINE_WORDS = re.compile(r"截止|期限|截至|止|deadline|due", re.IGNORECASE)

# ---------- 價格／營業時間／客服專線的衝突（2026-10-08，roadmap §2 AEO 第 2 項）----------
# 多個值多半是正常的（不同方案、平日與假日、各門市、各單位），只有「同一個標籤」在不同頁面
# 寫出不同的值才算衝突。標籤＝值前面、同一句話裡的文字。
_SENTENCE_END = re.compile(r"[。；;！!？?\n]")
_LABEL_NOISE = re.compile(r"[\d\s\W_]+")
_LABEL_WINDOW = 20
# 標籤或小標題帶這些字的值是刻意不同的價格或時段，不拿來比（只看標籤，不看整段：
# 「週一至週五 09:00-18:00，週末公休」的「週末」講的是另一件事）
_QUALIFIED = re.compile(
    r"原價|特價|優惠|早鳥|折扣|折|會員價|團體|學生價|平日|假日|連假|週末|周末|夏季|冬季|寒假|暑假"
    r"|春節|過年|國定|臨時|試上|體驗"
)
# 價格標籤去掉這些泛用詞後，還要剩下項目名稱，才知道兩頁說的是同一個東西
_PRICE_GENERIC = re.compile(
    r"價格|費用|收費|售價|定價|學費|報名費|每人|每位|每月|每堂|每次|只要|僅|約|起|ntd|nt|新台幣|新臺幣|元|"
    r"us|usd",
    re.IGNORECASE,
)
_TIME_RANGE = re.compile(
    r"(\d{1,2})[:：](\d{2})\s*(?:[-~–—至到]|to)\s*(\d{1,2})[:：](\d{2})", re.IGNORECASE
)
# 客服專線類：同一個功能的電話不該有兩支（各單位、各門市的電話本來就不同，不比）
_HOTLINE_LABEL = re.compile(r"客服|服務專線|訂購專線|訂房專線|預約專線|總機")
# 網站有多個據點時，營業時間與電話本來就會不同
_MULTI_LOCATION = re.compile(r"分店|分館|分院|分校|據點|校區|各門市|門市資訊|門市據點|分公司")
# 心得、見證、評價：描述個人經驗，不是站方對事實的陳述，不能拿來回答題庫問題
_TESTIMONIAL_HEADING = re.compile(
    r"見證|心得|感想|評價|好評|學員分享|顧客分享|testimonial|review", re.IGNORECASE
)
_FIRST_PERSON = re.compile(r"我(?!們)")

# 付款方式名稱（2026-10-08，roadmap §2 第 5 項）
_PAYMENT_METHOD = re.compile(
    r"信用卡|金融卡|簽帳卡|ATM|轉帳|匯款|貨到付款|取貨付款|超商代碼|超商付款|行動支付"
    r"|LINE\s?Pay|街口|Apple\s?Pay|Google\s?Pay|Samsung\s?Pay|台灣\s?Pay|全支付|悠遊付"
    r"|悠遊卡|一卡通|PayPal|現金|Visa|Mastercard|JCB|銀聯|分期付款"
    r"|credit card|debit card|bank transfer|wire transfer|cash on delivery",
    re.IGNORECASE,
)
# 預約管道：線上系統、表單、LINE、電話號碼，或「點選／填寫」這類可照做的動作
_BOOKING_CHANNEL = re.compile(
    r"線上預約|網路預約|預約系統|預約表單|預約平台|線上掛號|網路掛號|現場掛號|電話預約"
    # 「inline」單獨出現多半是英文單字（inline style），只認「inline 訂位」；平台名稱本身
    # （EZTABLE 有權取消此訂單）不是預約管道
    r"|來電|撥打|\bLINE\b|官方帳號|表單|點選|填寫|inline\s?訂位|book online"
    rf"|{_PHONE.pattern}",
    re.IGNORECASE,
)

# 付款與預約：只看成句的段落。選單連結文字（「出納付款查詢」「心理諮商線上預約」，
# 2026-10-08 ntub.edu.tw 實測）不是在回答怎麼付款、怎麼預約
_PROSE_ONLY = {q.PAYMENT, q.BOOKING}
_MIN_PROSE_CHARS = 15

_VALUE_FINDERS = {
    q.PHONE: _PHONE,
    q.EMAIL: _EMAIL,
    q.ADDRESS: _ADDRESS,
    q.HOURS: _HOURS,
    q.PRICE: _PRICE,
    q.DURATION: _DURATION,
    q.PAYMENT: _PAYMENT_METHOD,
    q.BOOKING: _BOOKING_CHANNEL,
}


@dataclass
class Evidence:
    page_url: str
    location: str
    quote: str
    value: str = ""

    def as_dict(self) -> dict:
        return {
            "url": self.page_url,
            "location": self.location,
            "quote": self.quote,
            "value": self.value or None,
        }


@dataclass
class QuestionResult:
    question: q.Question
    verdict: str
    reason: str
    evidence: list[Evidence] = field(default_factory=list)
    candidates_checked: int = 0

    @property
    def value_in_quote(self) -> bool:
        """答案值是否真的出現在引用的原文中（第一版規則下應恆為 True，作為自我檢查）。"""
        return any(e.value and e.value in e.quote for e in self.evidence)

    @property
    def confidence(self) -> str:
        """確認＝格式化的答案值逐字出現在原文；可能＝步驟／條件規則或網站自己的問題；推測＝其餘。"""
        if self.verdict == CONFLICT:
            return CONFIRMED if self.value_in_quote else LIKELY
        if self.verdict != ANSWERED:
            return ""
        if self.question.answer_type in _EXACT_TYPES:
            return CONFIRMED if self.value_in_quote else LIKELY
        if (
            self.question.answer_type in {q.STEPS, q.CRITERIA, q.BOOKING}
            or self.question.source == "site"
        ):
            return LIKELY
        return POSSIBLE

    def as_dict(self) -> dict:
        confidence = self.confidence
        return {
            **self.question.as_dict(),
            "verdict": self.verdict,
            "verdict_label": VERDICT_LABELS[self.verdict],
            "confidence": confidence or None,
            "confidence_label": CONFIDENCE_LABELS.get(confidence),
            "limitation": CONFIDENCE_LIMITS.get(confidence),
            "reason": self.reason,
            "evidence": [e.as_dict() for e in self.evidence],
            "candidates_checked": self.candidates_checked,
        }


# ---------- 檢索 ----------


def _passage_score(question: q.Question, passage: Passage) -> float:
    text = passage.text.lower()
    heading = (passage.heading or "").lower()
    hits = sum(1 for kw in question.keywords if kw.lower() in text)
    heading_hits = sum(1 for kw in question.keywords if kw.lower() in heading)
    # 小標題就是主題（例如「申請資格」底下列條件）時，段落本身常不重複主題詞
    return hits + heading_hits


def retrieve_candidates(question: q.Question, passages: list[Passage]) -> list[Passage]:
    """依關鍵詞相關度排序的候選段落（同分時保留原本頁面順序）。"""
    if question.source == "site":
        # 網站自己寫的問題：答案就是問題標題下方的段落
        own = [
            p
            for p in passages
            if p.page_url == question.origin_url
            and not p.is_heading
            and p.heading == question.origin_heading
        ]
        if own:
            return own[:MAX_CANDIDATES]
    scored = []
    for passage in passages:
        if passage.is_heading:
            continue
        if passage.region == "footer" and question.answer_type not in _FOOTER_OK:
            continue
        score = _passage_score(question, passage)
        finder = _VALUE_FINDERS.get(question.answer_type)
        if finder and finder.search(passage.text):
            # 聯絡資訊常只有號碼本身（例如頁尾一行電話），答案值也算相關性
            score += 1.5
        if score >= 1:
            scored.append((score, passage))
    scored.sort(key=lambda item: -item[0])
    return [p for _, p in scored[: MAX_CANDIDATES * 3]]


def _quote(text: str, value: str) -> str:
    if not value or value not in text or len(text) <= 2 * _QUOTE_RADIUS:
        return text[: 2 * _QUOTE_RADIUS]
    start = max(text.index(value) - _QUOTE_RADIUS, 0)
    end = min(text.index(value) + len(value) + _QUOTE_RADIUS, len(text))
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def _evidence(passage: Passage, value: str = "") -> Evidence:
    return Evidence(passage.page_url, passage.location(), _quote(passage.text, value), value)


# ---------- 答案蘊含（段落是否真的在回答這一題） ----------


def is_testimonial(passage: Passage) -> bool:
    if _TESTIMONIAL_HEADING.search(passage.heading or ""):
        return True
    # 第一人稱單數敘事（「我」而非「我們」）出現兩次以上，視為個人經驗分享
    return len(_FIRST_PERSON.findall(passage.text)) >= 2


def entails(question: q.Question, passage: Passage) -> bool:
    """段落是否在講這個主題，而不只是碰巧含有答案型態的字（例如心得裡的「必須」）。"""
    if not question.anchors:
        return True
    haystack = f"{passage.heading or ''} {passage.text}".lower()
    return any(anchor.lower() in haystack for anchor in question.anchors)


# ---------- 判定 ----------


def _find_value(answer_type: str, passage: Passage) -> str:
    text = passage.text
    finder = _VALUE_FINDERS.get(answer_type)
    if finder:
        match = finder.search(text)
        return match.group(0).strip() if match else ""
    if answer_type == q.DATE:
        match = _DATE_WITH_YEAR.search(text)
        return match.group(0).strip() if match else ""
    if answer_type == q.STEPS:
        markers = len(_STEP_MARKERS.findall(text))
        verbs = _STEP_VERBS.findall(text)
        if markers >= 1 and verbs or len(set(verbs)) >= 2:
            return verbs[0] if verbs else text[:20]
        return ""
    if answer_type == q.CRITERIA:
        # 「如需退款請聯絡客服」的「需」是假設語氣，不是條件
        match = _CRITERIA.search(_CONDITIONAL.sub("", text))
        return match.group(0) if match and len(text) >= 12 else ""
    if answer_type == q.DEFINITION:
        if len(text) >= 30 and not _only_vague(text):
            return text[:24]
        return ""
    if answer_type == q.FREEFORM:
        return text[:24] if len(text) >= 15 and not _only_vague(text) else ""
    return ""


def _only_vague(text: str) -> bool:
    """只有宣傳或引導語、沒有具體內容（去掉宣傳詞後剩不到 20 字）。"""
    if not _VAGUE.search(text):
        return False
    stripped = _VAGUE.sub("", text)
    return len(re.sub(r"\W", "", stripped)) < 20


def _steps_from_list(candidates: list[Passage]) -> str:
    """步驟常寫成清單：同一小標題下 2 段以上都有動作詞，也算有步驟。"""
    by_heading: dict[tuple[str, str], int] = {}
    for p in candidates:
        if _STEP_VERBS.search(p.text):
            key = (p.page_url, p.heading)
            by_heading[key] = by_heading.get(key, 0) + 1
    return next((h for (_, h), n in by_heading.items() if n >= 2 and h), "")


def judge(
    question: q.Question, candidates: list[Passage], all_passages: list[Passage]
) -> QuestionResult:
    if question.source == "intent":
        candidates = [p for p in candidates if not is_testimonial(p)]
    if not candidates:
        return QuestionResult(
            question,
            MISSING,
            f"已掃描的頁面中找不到提到這個主題的段落（檢索詞：{'、'.join(question.keywords[:6])}）。",
        )

    on_topic = [p for p in candidates if entails(question, p)]
    if question.answer_type in _PROSE_ONLY:
        on_topic = [p for p in on_topic if len(p.text.strip()) >= _MIN_PROSE_CHARS]
    if not on_topic:
        # 只碰到「必須」「限」這類泛用字，沒有任何段落真的在講這個主題
        return QuestionResult(
            question,
            MISSING,
            f"已掃描的頁面中沒有段落在談這個主題（主題詞：{'、'.join(question.anchors[:6])}）。",
            candidates_checked=len(candidates),
        )
    candidates = on_topic
    with_value = [(p, _find_value(question.answer_type, p)) for p in candidates]
    with_value = [(p, v) for p, v in with_value if v]

    if question.answer_type == q.STEPS and not with_value:
        heading = _steps_from_list(
            [
                p
                for p in all_passages
                if not p.is_heading
                and p.region == "main"
                and any(kw in p.heading for kw in question.keywords)
            ]
        )
        if heading:
            items = [p for p in all_passages if p.heading == heading and not p.is_heading][:3]
            return QuestionResult(
                question,
                ANSWERED,
                f"「{heading}」下方列出了可照做的步驟。",
                [
                    _evidence(p, _STEP_VERBS.search(p.text).group(0))
                    for p in items
                    if _STEP_VERBS.search(p.text)
                ],
                len(candidates),
            )

    if question.answer_type == q.DATE:
        return _judge_date(question, candidates, with_value)

    if with_value:
        conflict = _value_conflict(question, candidates, all_passages)
        if conflict:
            return conflict
        best, value = with_value[0]
        others = [_evidence(p, v) for p, v in with_value[1:MAX_CANDIDATES]]
        return QuestionResult(
            question,
            ANSWERED,
            f"找到具體答案：{value}",
            [_evidence(best, value), *others],
            len(candidates),
        )

    vague = [p for p in candidates if _VAGUE.search(p.text)]
    if vague:
        reason = "相關段落只有宣傳或引導語（例如「詳情請洽」），沒有具體資訊；" + (
            question.expect or ""
        )
    else:
        expected = question.expect or "直接回答問題的敘述"
        reason = f"有提到相關主題，但沒有具體答案。應有的內容：{expected}。"
    return QuestionResult(
        question,
        INSUFFICIENT,
        reason,
        [_evidence(p) for p in candidates[:MAX_CANDIDATES]],
        len(candidates),
    )


def _label(text: str, start: int) -> str:
    """值前面、同一句話裡的文字（最多 _LABEL_WINDOW 字），去掉數字與標點後當比對用的標籤。"""
    before = _SENTENCE_END.split(text[:start])[-1][-_LABEL_WINDOW:]
    return _LABEL_NOISE.sub("", before).lower()


def _labelled_values(answer_type: str, passage: Passage) -> list[tuple[str, str, str]]:
    """段落裡可比對的 (標籤, 正規化的值, 原文寫法)。"""
    text = passage.text
    found = []
    if answer_type == q.PRICE:
        for m in _PRICE.finditer(text):
            label = _label(text, m.start())
            if not _PRICE_GENERIC.sub("", label):
                continue  # 只有「學費」「每月」這類泛用詞，不知道是哪個項目
            found.append((label, re.sub(r"[^\d.]", "", m.group(0)), m.group(0).strip()))
    elif answer_type == q.HOURS:
        for m in _TIME_RANGE.finditer(text):
            h1, m1, h2, m2 = m.groups()
            value = f"{int(h1):02d}:{m1}-{int(h2):02d}:{m2}"
            found.append((_label(text, m.start()), value, m.group(0).strip()))
    elif answer_type == q.PHONE:
        for m in _PHONE.finditer(text):
            hotline = _HOTLINE_LABEL.search(_label(text, m.start()))
            if hotline:
                # 標籤只取功能名稱：「請撥打客服專線」與「客服專線」是同一支電話
                found.append(
                    (hotline.group(0), contacts.normalize_phone(m.group(0)), m.group(0).strip())
                )
    heading = passage.heading or ""
    return [item for item in found if not _QUALIFIED.search(f"{heading} {item[0]}")]


def _value_conflict(
    question: q.Question, candidates: list[Passage], all_passages: list[Passage]
) -> QuestionResult | None:
    """同一個標籤在不同頁面寫了不同的值（價格、營業時間、客服專線）。"""
    if question.answer_type not in {q.PRICE, q.HOURS, q.PHONE}:
        return None
    if question.answer_type != q.PRICE and any(
        _MULTI_LOCATION.search(f"{p.heading or ''} {p.text}") for p in all_passages
    ):
        return None
    by_label: dict[str, dict[str, tuple[Passage, str]]] = {}
    for passage in candidates:
        for label, value, raw in _labelled_values(question.answer_type, passage):
            by_label.setdefault(label, {}).setdefault(value, (passage, raw))
    for values in by_label.values():
        pages = {p.page_url for p, _raw in values.values()}
        if len(values) >= 2 and len(pages) >= 2:
            shown = [(p, raw) for p, raw in values.values()][:MAX_CANDIDATES]
            return QuestionResult(
                question,
                CONFLICT,
                "不同頁面對同一項目寫了不同的答案："
                + "、".join(raw for _p, raw in shown)
                + "；請確認哪一個才正確，或標明適用的方案、時段或對象。",
                [_evidence(p, raw) for p, raw in shown],
                len(candidates),
            )
    return None


def _judge_date(question: q.Question, candidates: list[Passage], with_year) -> QuestionResult:
    no_year = []
    for p in candidates:
        m = _DATE_NO_YEAR.search(p.text)
        if m and not _DATE_WITH_YEAR.search(p.text):
            no_year.append((p, m.group(0)))

    if with_year:
        deadline_values: dict[str, Passage] = {}
        for p, v in with_year:
            if _DEADLINE_WORDS.search(p.text):
                deadline_values.setdefault(re.sub(r"\s", "", v), p)
        pages = {p.page_url for p in deadline_values.values()}
        if len(deadline_values) >= 2 and len(pages) >= 2:
            ev = [_evidence(p, v) for v, p in list(deadline_values.items())[:MAX_CANDIDATES]]
            return QuestionResult(
                question,
                CONFLICT,
                "不同頁面寫了不同的截止日期："
                + "、".join(deadline_values)
                + "；請確認哪一個才正確、是否為不同梯次。",
                ev,
                len(candidates),
            )
        best, value = with_year[0]
        return QuestionResult(
            question, ANSWERED, f"找到具體日期：{value}", [_evidence(best, value)], len(candidates)
        )
    if no_year:
        return QuestionResult(
            question,
            INSUFFICIENT,
            "有提到日期但沒有標明年度（例如「"
            + no_year[0][1]
            + "」），讀者與 AI 無法判斷是否為今年的資訊。",
            [_evidence(p, v) for p, v in no_year[:MAX_CANDIDATES]],
            len(candidates),
        )
    return QuestionResult(
        question,
        INSUFFICIENT,
        f"有提到相關主題，但沒有具體日期。應有的內容：{question.expect}。",
        [_evidence(p) for p in candidates[:MAX_CANDIDATES]],
        len(candidates),
    )
