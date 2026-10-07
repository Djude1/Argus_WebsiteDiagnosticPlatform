"""AEO 判定回歸資料集（docs/scan-upgrade-roadmap.md P0-C）。

每個案例是一個小網站（1–2 頁），`expected` 是人工讀過內容後標註的「應有判定」；
只標註人能明確判斷的題目，沒標註的題目不計分。標註依據：

- answered：段落直接寫出可核對的答案（號碼、地址、時間區段、金額、含年度日期、步驟、條件）
- insufficient：段落在談這個主題，但沒有可用的答案（只有宣傳語、「請洽」、日期沒年度）
- conflict：不同頁面給出互相矛盾的答案
- missing：可讀的正文裡沒有任何段落在談這個主題
- 「語意相近但不是答案」（tag near_miss）：例如只寫運費沒寫出貨天數、「如需退款請聯絡客服」
  不是退款規定、「名額有限」不是申請資格——這類最容易被規則誤判成可回答

新增案例：先讀內容、獨立標註，再跑 `manage.py aeo_benchmark` 看規則判得如何；不要為了讓
規則通過而改標註。題目代號見 `aeo/questions.py` 的 INTENTS；網站自己的問句用 `site:<問句>`。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.scans.aeo.evaluate import SitePage

ANSWERABLE = "answerable"
INSUFFICIENT = "insufficient"
CONFLICT = "conflict"
MISSING = "missing"
NEAR_MISS = "near_miss"


@dataclass(frozen=True)
class GoldCase:
    name: str
    pages: tuple[SitePage, ...]
    expected: dict[str, str]
    tags: tuple[str, ...] = field(default_factory=tuple)


# 與任何題目無關的中性段落：讓每個案例的正文都超過 evaluate.MIN_MAIN_TEXT_CHARS，
# 測的是判定，不是「內容太少不評估」。放在所有標題之前，不會被當成任何標題下的答案
# （不可含題庫的觸發詞或關鍵詞）
_FILLER = (
    "<p>本站文字與圖片皆為原創內容，轉載前請先取得同意，並註明出處與原始連結。</p>"
    "<p>頁面內容會不定期更新，若發現錯字或排版問題歡迎指正，謝謝大家長期的閱讀與分享。</p>"
)


def _html(main: str, *, footer: str = "", outside: str = "") -> str:
    return (
        f"<html><body>{outside}<main>{_FILLER}{main}</main>"
        + (f"<footer>{footer}</footer>" if footer else "")
        + "</body></html>"
    )


def _one(url: str, main: str, **kw) -> tuple[SitePage, ...]:
    return (SitePage(url, _html(main, **kw)),)


_CLINIC_INTRO = (
    "<h1>晴光牙醫診所</h1><p>我們提供一般牙科、兒童牙科與植牙矯正服務，"
    "由三位專科醫師看診，並設有無障礙診間與兒童遊戲區，讓全家人都能安心就醫。</p>"
)
_CAFE_INTRO = (
    "<h1>山嵐咖啡</h1><p>我們提供自家烘焙的單品咖啡與手作甜點，店內有插座與安靜座位，"
    "適合工作與閱讀，也接受小型聚會包場與企業下午茶外送訂購。</p>"
)
_COURSE_INTRO = (
    "<h1>碼上學程式</h1><p>我們提供 Python、資料分析與網頁前端的線上課程，"
    "課程由業界工程師錄製，搭配每週直播答疑與作業批改，適合轉職與在職進修。</p>"
)
_SHOP_INTRO = (
    "<h1>森林選物</h1><p>我們提供台灣在地職人手作的生活器物，包含木作餐具、陶瓷杯盤與植物染布品，"
    "每件商品都附有職人介紹，歡迎加入購物車選購。</p>"
)
_SCHOOL_INTRO = (
    "<h1>資訊管理系 招生資訊</h1><p>本系提供資訊管理學士學位課程，"
    "培養企業數位轉型所需的系統分析、資料應用與專案管理人才，並與多家企業合作實習。</p>"
)

GOLD_CASES: tuple[GoldCase, ...] = (
    # ── 可回答 ──────────────────────────────────────────────
    GoldCase(
        "診所：電話、地址、門診時間都寫清楚",
        _one(
            "https://clinic.example/",
            _CLINIC_INTRO
            + "<h2>門診資訊</h2>"
                "<p>地址：台北市大安區復興南路一段100號2樓，交通：捷運大安站步行3分鐘。</p>"
            "<p>服務時間：週一至週五 09:00-18:00，週六 09:00-12:00，採預約制。</p>",
            footer="預約專線：02-2700-1234",
        ),
        {"contact_phone": "answered", "address": "answered", "hours": "answered",
         "about": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "線上課程：方案價格與退款規定",
        _one(
            "https://course.example/pricing",
            _COURSE_INTRO
            + "<h2>方案價格</h2><p>標準方案每月 NT$299，進階方案每月 NT$599，年繳享 85 折。</p>"
            "<h2>退款規定</h2><p>購買後 7 天內且未觀看超過 2 堂課程，可申請全額退款。</p>"
            "<p>訂閱可隨時取消，取消後到期前仍可觀看。</p>",
        ),
        {"price": "answered", "refund": "answered", "about": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "電商：出貨天數與退貨鑑賞期",
        _one(
            "https://shop.example/faq",
            _SHOP_INTRO
            + "<h2>出貨說明</h2><p>訂單成立後 2-3 個工作天內出貨，宅配到府約需 1 天。</p>"
            "<h2>退貨說明</h2><p>商品享有 7 天鑑賞期，未使用且包裝完整即可申請退貨。</p>"
            "<p>付款方式支援信用卡與超商取貨付款。</p>",
        ),
        {"shipping": "answered", "refund": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "招生：含年度的報名期間、步驟與資格",
        _one(
            "https://imd.example/admission",
            _SCHOOL_INTRO
            + "<h2>報名期間</h2><p>2027 學年度報名期間：2026年11月1日至2026年12月15日止。</p>"
            "<h2>申請流程</h2><ol><li>線上填寫報名表</li><li>上傳成績單與自傳</li>"
            "<li>繳交報名費</li></ol>"
            "<h2>申請資格</h2><p>高中職畢業或具同等學力者皆可報名申請。</p>",
        ),
        {"apply_deadline": "answered", "apply_how": "answered", "eligibility": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "工作室：分機電話與 Email",
        _one(
            "https://studio.example/contact",
            "<h1>好日設計工作室</h1><p>我們提供品牌識別、包裝與網站設計服務，"
            "從前期訪談到成品交付都由同一位設計師負責，確保風格一致。</p>"
            "<h2>聯絡我們</h2><p>電話 (02)2345-6789 分機 12，信箱 hello@studio.example。</p>",
        ),
        {"contact_phone": "answered", "contact_email": "answered", "about": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "協會：國際格式電話",
        _one(
            "https://assoc.example/",
            "<h1>台灣步道協會</h1><p>我們提供步道志工培訓、手作步道工作假期與親子自然導覽，"
            "長期與各地社區合作維護郊山步道，推廣友善環境的登山方式。</p>"
            "<p>聯絡電話：+886-2-2322-6000，歡迎來電詢問志工梯次。</p>",
        ),
        {"contact_phone": "answered", "about": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "才藝教室：服務時間與每堂價格",
        _one(
            "https://art.example/",
            "<h1>小樹美術教室</h1><p>我們提供兒童水彩、素描與黏土創作課程，"
            "小班制教學，每班最多八位學生，讓老師能照顧到每個孩子的進度。</p>"
            "<h2>上課時間</h2><p>服務時間：週二至週六 上午10點至晚上8點，可預約試上。</p>"
            "<h2>課程費用</h2><p>收費方式：單堂體驗課 800 元，十堂套票 7,000 元，材料費另計。</p>",
        ),
        {"hours": "answered", "price": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "網站自己的常見問題：一題有答案",
        _one(
            "https://shop2.example/faq",
            "<h1>常見問題</h1><p>我們提供有機蔬果箱訂閱服務，每週從合作小農直送到府，"
            "內容依季節調整，可隨時暫停或更換品項。</p>"
            "<h2>可以開立發票嗎？</h2><p>可以，結帳時填寫統一編號即可開立電子發票，會寄到您的信箱。</p>",
        ),
        {"site:可以開立發票嗎？": "answered", "about": "answered"},
        (ANSWERABLE,),
    ),
    GoldCase(
        "顧問公司：短標題裡的 Email",
        _one(
            "https://consult.example/contact",
            "<h1>遠見顧問</h1><p>我們提供中小企業的數位轉型顧問、流程改善與資安健檢服務，"
            "顧問團隊皆具十年以上產業經驗，協助企業規劃可落地的改善方案。</p>"
            "<h2>聯絡信箱</h2><h3>Email：service@consult.example</h3>",
        ),
        {"contact_email": "answered"},
        (ANSWERABLE,),
    ),
    # ── 資訊不足 ────────────────────────────────────────────
    GoldCase(
        "咖啡店：地址、營業時間與訂位電話都只有一句話",
        _one(
            "https://cafe.example/",
            _CAFE_INTRO
            + "<h2>門市資訊</h2><p>門市位於台北市中心，交通便利，歡迎來店坐坐。</p>"
            "<p>營業時間請見粉絲專頁公告，假日人多建議提早到。</p>"
            "<p>包場訂位請來電洽詢。</p>",
        ),
        {"address": "insufficient", "hours": "insufficient", "contact_phone": "insufficient"},
        (INSUFFICIENT,),
    ),
    GoldCase(
        "招生：截止日沒寫年度",
        _one(
            "https://imd2.example/news",
            _SCHOOL_INTRO + "<h2>最新消息</h2><p>碩士班招生報名截止：3月31日，逾期不受理。</p>",
        ),
        {"apply_deadline": "insufficient"},
        (INSUFFICIENT,),
    ),
    GoldCase(
        "網站自己的常見問題：只有「詳情請洽」",
        _one(
            "https://learn.example/faq",
            _COURSE_INTRO
            + "<h2>課程可以看多久？</h2><p>詳情請洽客服。</p>",
        ),
        {"site:課程可以看多久？": "insufficient"},
        (INSUFFICIENT,),
    ),
    GoldCase(
        "團隊介紹只有宣傳語",
        _one(
            "https://brand.example/",
            "<h1>關於我們</h1><p>我們是最專業、最用心、值得信賴的一流團隊。</p>"
            "<p>最優質的服務，詳情請洽。</p>"
            "<p>歡迎來電洽詢，更多資訊請見官方粉絲專頁，敬請期待我們的新消息與活動公告。</p>",
        ),
        {"about": "insufficient", "contact_phone": "insufficient"},
        (INSUFFICIENT,),
    ),
    # ── 內容衝突 ────────────────────────────────────────────
    GoldCase(
        "兩頁的報名截止日不同",
        (
            SitePage(
                "https://school.example/brochure",
                _html(
                    _SCHOOL_INTRO
                    + "<p>2027 學年度招生，網路報名截止日期為 2026年12月20日，逾期不予受理。</p>"
                ),
            ),
            SitePage(
                "https://school.example/apply",
                _html("<h1>報名專區</h1>"
                    "<p>2027 學年度報名申請開放中，報名截止：2027年1月10日。</p>"),
            ),
        ),
        {"apply_deadline": "conflict"},
        (CONFLICT,),
    ),
    # ── 無可用答案 ──────────────────────────────────────────
    GoldCase(
        "電商：完全沒提退貨規定",
        _one(
            "https://shop3.example/",
            _SHOP_INTRO
            + "<h2>熱銷商品</h2><p>檜木砧板、手拉坯咖啡杯與藍染餐墊，皆可加入購物車一起結帳。</p>",
        ),
        {"refund": "missing", "contact_email": "missing"},
        (MISSING,),
    ),
    GoldCase(
        "招生：沒有寫任何申請資格",
        _one(
            "https://imd3.example/admission",
            _SCHOOL_INTRO
            + "<h2>申請流程</h2><ol><li>線上填寫報名表</li><li>上傳自傳</li></ol>",
        ),
        {"eligibility": "missing"},
        (MISSING,),
    ),
    GoldCase(
        "Email 只出現在導覽列（正文只說歡迎寫信）",
        (
            SitePage(
                "https://ngo.example/",
                _html(
                    "<h1>綠色地球協會</h1><p>我們提供環境教育講座、淨灘活動與校園回收推廣，"
                    "也接受企業 ESG 合作提案；有任何問題歡迎寫信到我們的信箱，會有專人回覆。</p>",
                    outside="<nav>首頁 活動 contact@ngo.example</nav>",
                ),
            ),
        ),
        # 正文說「歡迎寫信到信箱」但沒寫地址：在談這個主題、沒有答案＝資訊不足
        {"contact_email": "insufficient"},
        (INSUFFICIENT,),
    ),
    # ── 語意相近但不是答案 ──────────────────────────────────
    GoldCase(
        "運費不是出貨天數",
        _one(
            "https://shop4.example/",
            _SHOP_INTRO
            + "<h2>配送方式</h2><p>提供宅配與超商取貨，運費依商品重量計算，滿 1,500 元免運費。</p>",
        ),
        {"shipping": "insufficient"},
        (NEAR_MISS,),
    ),
    GoldCase(
        "「如需退款請聯絡客服」不是退款規定",
        _one(
            "https://shop5.example/",
            _SHOP_INTRO + "<h2>售後服務</h2><p>如需退款請聯絡客服，我們會盡快為您處理。</p>",
        ),
        {"refund": "insufficient"},
        (NEAR_MISS,),
    ),
    GoldCase(
        "「名額有限」不是申請資格",
        _one(
            "https://camp.example/",
            "<h1>暑期程式營</h1><p>我們提供為期五天的程式設計營隊，帶學員從零開始完成一個小遊戲，"
            "營期間提供午餐與保險，結業頒發證書。</p>"
            "<p>暑期營隊招生中，歡迎申請。</p><h2>報名方式</h2><p>線上填寫報名表後繳交報名費即完成報名，名額有限，額滿為止。</p>",
        ),
        {"eligibility": "missing", "apply_how": "answered"},
        (NEAR_MISS,),
    ),
    GoldCase(
        "學員心得裡的「必須」不是申請資格",
        _one(
            "https://center.example/course",
            "<h1>課程介紹</h1><p>本中心開設 Excel 資料分析與互動式前端課程，由系上教師授課，"
            "適合在職人士進修，課程招生中，歡迎報名申請。</p>"
            "<h2>學員見證：這門課如何改變他們的職涯！</h2>"
            "<p>由於工作上必須經常把大量資料整理為數據報告，回到母校上課讓我能更有效率地學習，"
            "我希望未來能再參加同類型的進修課程。</p>",
        ),
        {"eligibility": "missing"},
        (NEAR_MISS,),
    ),
    GoldCase(
        "「報名即將截止」沒有日期",
        _one(
            "https://event.example/",
            "<h1>城市路跑活動</h1><p>我們舉辦年度城市路跑，提供 5 公里與 10 公里兩種組別，"
            "完賽可獲得獎牌與紀念衫，歡迎親子與團體一起參加。</p>"
            "<h2>報名資訊</h2><p>報名即將截止，請把握最後機會！</p>",
        ),
        {"apply_deadline": "insufficient"},
        (NEAR_MISS,),
    ),
    GoldCase(
        "網站自己的問句底下只有感謝詞",
        _one(
            "https://shop6.example/faq",
            _SHOP_INTRO
            + "<h2>運費怎麼計算？</h2><p>感謝您一直以來的支持與愛護，我們會持續努力。</p>",
        ),
        {"site:運費怎麼計算？": "insufficient"},
        (NEAR_MISS,),
    ),
    GoldCase(
        "「全年無休」沒有時間區段",
        _one(
            "https://mart.example/",
            "<h1>巷口生鮮超市</h1><p>我們提供每日新鮮蔬果、肉品與日用品，"
            "會員消費可累積點數兌換購物金，也提供滿額外送服務。</p>"
            "<h2>門市資訊</h2><p>本門市全年無休，歡迎來店選購。</p>",
        ),
        {"hours": "insufficient"},
        (NEAR_MISS,),
    ),
    GoldCase(
        "「價格實惠」沒有金額",
        _one(
            "https://saas.example/pricing",
            "<h1>雲端記帳</h1><p>我們提供小型商家的雲端記帳與發票管理工具，"
            "支援手機拍照記帳與自動對帳，報表一鍵匯出給會計師。</p>"
            "<h2>方案與價格</h2><p>價格實惠、方案多元，CP 值超高，歡迎洽詢最適合您的方案。</p>",
        ),
        {"price": "insufficient"},
        (NEAR_MISS,),
    ),
)


# ── 保留集（holdout）──────────────────────────────────────
# 2026-10-07 規則調整「之後」才撰寫與標註、標註前沒有先跑過規則，用來量測規則是否只是
# 擬合了上面的案例。之後調整規則時也不要只為了讓這批通過而改規則。
HOLDOUT = "holdout"

_BNB_INTRO = (
    "<h1>海風民宿</h1><p>我們提供四間海景雙人房與一間家庭房，早餐使用在地小農食材，"
    "也可代訂賞鯨與單車行程，適合想放慢腳步的旅人。</p>"
)
_GYM_INTRO = (
    "<h1>動起來健身房</h1><p>我們提供重訓區、有氧器材與團體課程，"
    "教練皆具國家證照，新會員可免費體驗一次一對一體態評估。</p>"
)

HOLDOUT_CASES: tuple[GoldCase, ...] = (
    GoldCase(
        "民宿：手機號碼與完整地址",
        _one(
            "https://bnb.example/",
            _BNB_INTRO
            + "<h2>交通與地址</h2><p>地址：花蓮縣壽豐鄉中山路123號，自行開車約需 30 分鐘。</p>"
            "<p>訂房電話 0912-345-678，晚上十點後請改用訊息聯絡。</p>",
        ),
        {"address": "answered", "contact_phone": "answered", "about": "answered"},
        (ANSWERABLE, HOLDOUT),
    ),
    GoldCase(
        "補習班：學費金額",
        _one(
            "https://cram.example/",
            "<h1>明德文理補習班</h1><p>我們提供國高中數學、英文與自然科輔導，"
            "採小班教學並定期舉辦模擬考，協助學生掌握學習進度。</p>"
            "<h2>收費標準</h2>"
                "<p>費用：國中數學每期 12,000 元，高中數學每期 15,000 元，皆含講義。</p>",
        ),
        {"price": "answered"},
        (ANSWERABLE, HOLDOUT),
    ),
    GoldCase(
        "健身房：每日營業時間",
        _one(
            "https://gym.example/",
            _GYM_INTRO
            + "<h2>營業時間</h2><p>營業時間：每日 06:00-23:00，國定假日照常營業，課程需預約。</p>",
        ),
        {"hours": "answered", "about": "answered"},
        (ANSWERABLE, HOLDOUT),
    ),
    GoldCase(
        "電商：退貨天數與運費負擔",
        _one(
            "https://shop7.example/",
            _SHOP_INTRO
            + "<h2>退換貨</h2>"
                "<p>收到商品 10 日內可辦理退貨，退貨運費由買方負擔，訂單完成後恕不退換。</p>",
        ),
        {"refund": "answered"},
        (ANSWERABLE, HOLDOUT),
    ),
    GoldCase(
        "研習班：民國年報名期限與年齡資格",
        _one(
            "https://seminar.example/",
            "<h1>社區大學木工研習班</h1><p>本課程由資深木工師傅授課，從工具使用到完成一張小板凳，"
            "共八週十六小時，歡迎對手作有興趣的朋友報名申請。</p>"
            "<h2>報名期限</h2><p>報名期限：民國116年3月1日至3月15日止。</p>"
            "<h2>報名資格</h2><p>年滿 18 歲之社區居民皆可報名，名額 20 人。</p>",
        ),
        {"apply_deadline": "answered", "eligibility": "answered"},
        (ANSWERABLE, HOLDOUT),
    ),
    GoldCase(
        "民宿：網站自己的問句有具體答案",
        _one(
            "https://bnb2.example/faq",
            _BNB_INTRO
            + "<h2>可以帶寵物入住嗎？</h2>"
                "<p>可以，每間房最多一隻中小型犬，需另付清潔費 500 元。</p>",
        ),
        {"site:可以帶寵物入住嗎？": "answered"},
        (ANSWERABLE, HOLDOUT),
    ),
    GoldCase(
        "門市：只寫星期區間",
        _one(
            "https://store.example/",
            "<h1>好鄰居五金行</h1><p>我們提供水電材料、手工具與園藝用品，"
            "也可代客裁切木板與配製鑰匙，來店前可先電話確認庫存。</p>"
            "<h2>門市資訊</h2><p>門市服務時間：星期一至星期六，週日公休。</p>",
        ),
        {"hours": "answered"},
        (ANSWERABLE, HOLDOUT),
    ),
    GoldCase(
        "電商：只說「盡快出貨」",
        _one(
            "https://shop8.example/",
            _SHOP_INTRO + "<h2>出貨方式</h2><p>付款完成後我們會盡快出貨，提供宅配到府服務。</p>",
        ),
        {"shipping": "insufficient"},
        (NEAR_MISS, HOLDOUT),
    ),
    GoldCase(
        "客服專線尚未開通",
        _one(
            "https://startup.example/",
            "<h1>小日子記帳 App</h1><p>我們提供個人記帳與預算提醒功能，"
            "支援多帳戶與信用卡帳單整合，資料皆加密儲存在您的裝置上。</p>"
            "<p>客服專線即將開通，敬請期待。</p>",
        ),
        {"contact_phone": "insufficient"},
        (NEAR_MISS, HOLDOUT),
    ),
    GoldCase(
        "門市只寫行政區",
        _one(
            "https://bakery.example/",
            "<h1>麥香烘焙坊</h1><p>我們提供每日現烤歐式麵包與手工餅乾，"
            "使用天然酵母長時間發酵，不添加人工香料，也接受彌月禮盒訂製。</p>"
            "<h2>門市與交通</h2><p>歡迎到我們位於信義區的門市選購，交通方便。</p>",
        ),
        {"address": "insufficient"},
        (NEAR_MISS, HOLDOUT),
    ),
    GoldCase(
        "「價格依需求報價」沒有金額",
        _one(
            "https://agency.example/",
            "<h1>光點影像製作</h1><p>我們提供企業形象影片、產品攝影與活動紀錄，"
            "從腳本企劃到後製剪輯一條龍服務，作品曾獲多項廣告獎項。</p>"
            "<h2>價格</h2><p>價格依需求客製報價，歡迎與我們討論您的專案。</p>",
        ),
        {"price": "insufficient"},
        (NEAR_MISS, HOLDOUT),
    ),
    GoldCase(
        "網站建置中，沒有任何介紹",
        _one(
            "https://soon.example/",
            "<h1>歡迎光臨</h1><p>網站建置中，敬請期待。</p>",
        ),
        {"about": "missing"},
        (MISSING, HOLDOUT),
    ),
    GoldCase(
        "兩頁的課程報名截止日不同",
        (
            SitePage(
                "https://seminar2.example/a",
                _html("<h1>課程簡章</h1>"
                    "<p>2027 年春季班報名截止日期：2027年2月10日，歡迎申請。</p>"),
            ),
            SitePage(
                "https://seminar2.example/b",
                _html("<h1>最新公告</h1><p>2027 年春季班報名延長至 2027年2月28日截止。</p>"),
            ),
        ),
        {"apply_deadline": "conflict"},
        (CONFLICT, HOLDOUT),
    ),
)

ALL_CASES: tuple[GoldCase, ...] = GOLD_CASES + HOLDOUT_CASES


def labelled_count(cases=ALL_CASES) -> int:
    return sum(len(case.expected) for case in cases)
