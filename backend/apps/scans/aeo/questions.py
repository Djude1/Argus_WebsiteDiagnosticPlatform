"""AEO 第 2 層（上）：從網站主題與頁面內容建立一組具體問題。

第一版刻意只用**可重現的規則**：同一份內容永遠產生同一組題目，站方改完內容重掃，
能逐題比對是否解決。題目來源有兩種：

1. 意圖題庫（INTENTS）：每個意圖有觸發詞與答案型態。常駐意圖（聯絡方式、提供什麼）
   每個網站都問；其餘意圖要在網站正文中出現足夠的觸發詞才問——例如整站提到「招生」
   「報名」，才會問「申請截止日是何時？」，不會對咖啡店問招生問題。
2. 網站自己寫的問題：小標題／dt／summary 以問號結尾的句子（FAQ 常見寫法）。

同業常見問句（2026-10-08，roadmap §2 第 5 項）：付款方式（電商、課程、健身房等收費網站）與
預約／訂位（診所、餐廳、工作室）也以觸發詞決定要不要問，答案要有可核對的付款方式名稱或
預約管道。不從一般小標題（例如「交通資訊」）自動造題：那一段本身就是答案，幾乎一定判成
可回答，只會灌高分數。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 答案型態（answers.py 依此找「答案值」）
PHONE = "phone"
EMAIL = "email"
ADDRESS = "address"
HOURS = "hours"
PRICE = "price"
DATE = "date"
STEPS = "steps"
DURATION = "duration"
DEFINITION = "definition"
CRITERIA = "criteria"
PAYMENT = "payment"
BOOKING = "booking"
FREEFORM = "freeform"


@dataclass(frozen=True)
class Intent:
    key: str
    question: str
    answer_type: str
    # 找答案段落用的關鍵詞（任一出現即為候選；越多越相關）
    keywords: tuple[str, ...]
    # 決定要不要問這題的觸發詞；空＝每個網站都問
    triggers: tuple[str, ...] = ()
    min_trigger_hits: int = 2
    # 權重：核心資訊（聯絡、期限、價格）缺了影響較大
    weight: float = 1.0
    # 補充說明：答案應包含什麼（寫進報告的「成立條件」）
    expect: str = ""
    # 答案蘊含：段落（或其小標題）必須出現其中一個主題詞，答案值才算回答了這題。
    # 例如「必須」出現在學員心得裡，不代表那段在講申請資格。空＝不額外要求。
    anchors: tuple[str, ...] = ()


INTENTS: tuple[Intent, ...] = (
    Intent(
        "contact_phone",
        "聯絡電話是多少？",
        PHONE,
        ("電話", "聯絡", "客服", "專線", "來電", "撥打", "tel", "phone", "call"),
        weight=1.0,
        expect="頁面文字中有完整電話號碼",
    ),
    Intent(
        "contact_email",
        "聯絡 Email 是什麼？",
        EMAIL,
        # 只用 Email 專屬詞：「聯絡客服」這類泛稱不代表有提到 Email
        ("信箱", "email", "e-mail", "電子郵件", "mail"),
        weight=0.6,
        expect="頁面文字中有 Email 地址",
    ),
    Intent(
        "about",
        "這個網站（組織）提供什麼服務或內容？",
        DEFINITION,
        (
            "提供",
            "服務",
            "我們",
            "致力",
            "專注",
            "簡介",
            "關於",
            "宗旨",
            "about",
            "offer",
            "provide",
        ),
        weight=0.8,
        expect="至少一段具體描述提供的服務、產品或內容，而非只有標語",
    ),
    Intent(
        "address",
        "地址或所在位置在哪裡？",
        ADDRESS,
        ("地址", "位置", "位於", "交通", "門市", "據點", "校區", "address", "location"),
        triggers=("地址", "門市", "據點", "校區", "交通", "來店", "辦公室", "address", "location"),
        weight=0.8,
        expect="有可辨識的地址（縣市、路街、號）",
    ),
    Intent(
        "hours",
        "營業或服務時間是什麼時候？",
        HOURS,
        # 「全年無休」「24 小時」也是在講營業時間（2026-10-07 回歸資料集）
        (
            "營業", "時間", "服務時間", "開放", "週一", "星期", "假日", "無休", "全天",
            "hours", "open",
        ),
        triggers=("營業", "門市", "來店", "開放時間", "服務時間", "預約", "客服時間", "hours"),
        weight=0.8,
        expect="有具體的時間區段（例如 09:00–18:00）或星期",
    ),
    Intent(
        "price",
        "價格或費用是多少？",
        PRICE,
        (
            "價格",
            "費用",
            "收費",
            "方案",
            "售價",
            "定價",
            "學費",
            "元",
            "nt$",
            "ntd",
            "$",
            "price",
            "fee",
            "cost",
        ),
        triggers=(
            "價格",
            "費用",
            "收費",
            "學費",
            "方案",
            "購買",
            "訂閱",
            "售價",
            "報價",
            "price",
            "pricing",
        ),
        weight=1.0,
        expect="有明確金額與對應的項目或方案",
    ),
    Intent(
        "apply_how",
        "如何申請或報名？",
        STEPS,
        (
            "申請",
            "報名",
            "流程",
            "步驟",
            "填寫",
            "上傳",
            "繳交",
            "註冊",
            "apply",
            "register",
            "how to",
        ),
        triggers=("申請", "報名", "招生", "入學", "註冊", "徵才", "應徵", "admission", "apply"),
        weight=0.9,
        expect="有可照做的步驟、所需文件或申請入口",
    ),
    Intent(
        "apply_deadline",
        "申請或報名截止日期是何時？",
        DATE,
        ("截止", "期限", "日期", "期間", "時程", "開始", "結束", "至", "deadline", "due"),
        triggers=("申請", "報名", "招生", "入學", "徵件", "活動", "admission", "deadline"),
        weight=1.0,
        expect="有具體日期，且標明適用年度或梯次",
        anchors=("截止", "期限", "報名", "申請", "開課", "梯次", "deadline", "due"),
    ),
    Intent(
        "eligibility",
        "申請資格或條件是什麼？",
        CRITERIA,
        ("資格", "條件", "對象", "需具備", "限", "須", "年滿", "requirement", "eligib"),
        triggers=("資格", "條件", "適用對象", "申請", "招生", "徵才", "eligib"),
        weight=0.7,
        expect="列出具體的資格條件（學歷、年齡、身分、年資等）",
        anchors=("資格", "條件", "對象", "招收", "年滿", "具備", "requirement", "eligib"),
    ),
    Intent(
        "refund",
        "退款或退貨規定是什麼？",
        CRITERIA,
        ("退款", "退貨", "退費", "取消", "鑑賞期", "refund", "return", "cancel"),
        triggers=("購買", "訂單", "付款", "商品", "購物車", "訂閱", "結帳", "checkout", "order"),
        weight=0.8,
        expect="寫明可否退款／退貨、期限與方式",
        anchors=("退款", "退貨", "退費", "鑑賞期", "refund", "return"),
    ),
    Intent(
        "shipping",
        "配送或出貨需要多久？",
        DURATION,
        ("配送", "出貨", "運送", "寄送", "到貨", "運費", "shipping", "delivery"),
        triggers=("配送", "出貨", "運費", "宅配", "購物車", "shipping", "delivery"),
        weight=0.6,
        expect="有具體天數或時間範圍",
        anchors=("配送", "出貨", "運送", "寄送", "到貨", "shipping", "delivery"),
    ),
    Intent(
        "payment",
        "可以使用哪些付款方式？",
        PAYMENT,
        ("付款", "支付", "付費", "繳費", "繳納", "信用卡", "轉帳", "結帳", "payment"),
        triggers=("付款", "結帳", "購物車", "訂單", "繳費", "付費", "checkout", "payment"),
        weight=0.6,
        expect="列出可用的付款方式（例如信用卡、ATM 轉帳、行動支付、貨到付款）",
        # 只寫「結帳時可用優惠券」不是在講付款方式
        anchors=("付款", "支付", "付費", "繳費", "繳納", "payment"),
    ),
    Intent(
        "booking",
        "如何預約或訂位？",
        BOOKING,
        ("預約", "訂位", "預訂", "掛號", "booking", "reserv"),
        triggers=("預約", "訂位", "預訂", "掛號", "booking", "reservation"),
        weight=0.7,
        expect="寫出預約管道（線上系統、表單、電話、LINE）或可照做的步驟",
        anchors=("預約", "訂位", "預訂", "掛號", "booking", "reserv"),
    ),
)

MAX_SITE_QUESTIONS = 8
_SITE_QUESTION = re.compile(r"[？?]\s*$")
_QUESTION_WORDS = re.compile(
    r"什麼|如何|怎麼|為何|為什麼|哪|是否|能否|可以|多少|何時|嗎"
    r"|\b(?:what|how|when|why|where|can|is|are|do|does)\b",
    re.IGNORECASE,
)


@dataclass
class Question:
    key: str
    text: str
    answer_type: str
    keywords: tuple[str, ...]
    weight: float
    source: str  # "intent"：題庫；"site"：網站自己寫的問題
    expect: str = ""
    origin_url: str = ""
    origin_heading: str = ""
    trigger_hits: int = 0
    anchors: tuple[str, ...] = ()
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "text": self.text,
            "answer_type": self.answer_type,
            "source": self.source,
            "weight": self.weight,
            "expect": self.expect,
            "origin_url": self.origin_url or None,
        }


def _count_hits(text_lower: str, words: tuple[str, ...]) -> int:
    return sum(text_lower.count(w.lower()) for w in words)


def _question_keywords(text: str) -> tuple[str, ...]:
    """網站自寫問題的檢索詞：去掉疑問詞與標點後的中文雙字詞與英文單字。"""
    core = _QUESTION_WORDS.sub(" ", text)
    core = re.sub(r"[？?！!，,。．.、：:；;（）()「」\"'\s]+", " ", core)
    words: list[str] = []
    for chunk in core.split():
        if re.fullmatch(r"[A-Za-z0-9-]+", chunk):
            if len(chunk) >= 3:
                words.append(chunk.lower())
            continue
        cjk = re.sub(r"[^一-鿿]", "", chunk)
        words.extend(cjk[i : i + 2] for i in range(max(len(cjk) - 1, 0)))
    # 保持順序去重
    return tuple(dict.fromkeys(w for w in words if w))[:12]


# 付款與預約的觸發詞只算小標題與成句段落：學校、醫院網站選單上的「心理諮商線上預約」
# 「出納付款查詢」連結不代表網站在提供這類服務（2026-10-08 ntub.edu.tw 實測）
_PROSE_TRIGGER_TYPES = {PAYMENT, BOOKING}
_MIN_PROSE_CHARS = 15


def build_question_set(pages) -> list[Question]:
    """pages：PageContent 清單（已擷取正文）。回傳本站要檢測的題目。"""
    corpus = "\n".join(p.text for p in pages).lower()
    prose_corpus = "\n".join(
        passage.text
        for page in pages
        for passage in page.passages
        if passage.region == "main"
        and (passage.is_heading or len(passage.text.strip()) >= _MIN_PROSE_CHARS)
    ).lower()
    questions: list[Question] = []
    for intent in INTENTS:
        text = prose_corpus if intent.answer_type in _PROSE_TRIGGER_TYPES else corpus
        hits = _count_hits(text, intent.triggers) if intent.triggers else 0
        if intent.triggers and hits < intent.min_trigger_hits:
            continue
        questions.append(
            Question(
                key=intent.key,
                text=intent.question,
                answer_type=intent.answer_type,
                keywords=intent.keywords,
                weight=intent.weight,
                source="intent",
                expect=intent.expect,
                trigger_hits=hits,
                anchors=intent.anchors,
            )
        )

    seen: set[str] = set()
    site_questions = 0
    for page in pages:
        for passage in page.passages:
            text = passage.text.strip()
            if not passage.is_heading or not _SITE_QUESTION.search(text):
                continue
            if not (4 <= len(text) <= 80) or text in seen:
                continue
            seen.add(text)
            keywords = _question_keywords(text)
            if not keywords:
                continue
            questions.append(
                Question(
                    key=f"site_{site_questions + 1}",
                    text=text,
                    answer_type=FREEFORM,
                    keywords=keywords,
                    weight=0.6,
                    source="site",
                    expect="問題下方有直接回答的內容",
                    origin_url=page.url,
                    origin_heading=text,
                )
            )
            site_questions += 1
            if site_questions >= MAX_SITE_QUESTIONS:
                return questions
    return questions
