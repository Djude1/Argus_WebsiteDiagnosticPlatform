"""Word（.docx）健檢報告產生器。

報告的讀者是網站主，不是資安工程師（見 docs/scan-report-quality-audit-2026-08-30.md）。
所以這裡的原則是：

- 內部識別碼（rule_id、evidence_source、evidence_type）不進正文，rule_id 收進附錄
  的技術索引供工程師查用。
- 每一筆發現固定回答四個問題：問題是什麼 / 為什麼要在意 / 怎麼修 / 修好了怎麼確認。
  舊版依 severity 給同一個結構三種標題（風險描述／改善重點／建議優化），讀者會以為
  是三種不同的東西。
- 名詞解釋只列這份報告裡真的出現過的術語，不是貼一份固定清單。
- 資訊要有結構（表格、分頁、頁碼、嚴重度顏色），不是 300 段純文字流。

內容邊界（哪些欄位不得寫進報告）見 backend/apps/scans/CLAUDE.md「報告內容契約」。
"""

import hmac
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.scans.models import Finding, ReportVerification, ScanJob
from apps.scans.report_render import RENDERER_VERSION, generate_report
from apps.scans.scan_plan import build_scan_execution_plan
from apps.scans.security.redaction import redact_pii_in_text

# --- 品牌與嚴重度配色 -------------------------------------------------
# frontend/src/styles.css 的 token 是為深色背景設計的，--argus-cyan (#38bdf8)
# 印在白紙上對比不足，所以標題改用 --argus-cyan-deep，cyan 只當強調線。
ARGUS_NAVY = "0A1535"        # --argus-navy-800
ARGUS_CYAN = "38BDF8"        # --argus-cyan（強調線用）
ARGUS_CYAN_DEEP = "0C4A6E"   # --argus-cyan-deep（白底可讀的標題色）
ARGUS_MUTED = "5B6B7C"

SEVERITY_COLOR = {
    "critical": "B02418",
    "high": "C4600F",
    "medium": "8A6A00",
    "low": "1F6591",
    "info": "5B4B8A",
}

SEVERITY_DISPLAY = {
    "critical": "嚴重風險",
    "high": "高風險",
    "medium": "中風險",
    "low": "低風險",
    "info": "資訊提示",
}

CATEGORY_DISPLAY = {
    "seo": "SEO 搜尋引擎最佳化",
    "aeo": "AEO 問答引擎最佳化",
    "geo": "GEO 生成式引擎最佳化",
    "security": "資訊安全",
    "ux": "使用者體驗",
}

SCORE_BANDS = [
    (80, "良好", "持續維持即可，建議定期複檢。"),
    (60, "需改善", "有幾項體質問題值得排入維護排程。"),
    (40, "建議儘快處理", "累積的問題已可能影響流量或安全，建議近期處理。"),
    (0, "需優先處理", "存在較高風險的項目，建議優先安排修補。"),
]

# 只列這份報告裡真的出現過的術語。key 會拿去比對報告文字。
GLOSSARY = {
    "HSTS": "強制瀏覽器之後一律以加密連線（HTTPS）連到你的網站，避免被降級成未加密連線。",
    "CSP": "內容安全政策。告訴瀏覽器這個網頁只能載入哪些來源的程式與資源，"
           "用來擋掉被植入的惡意腳本。",
    "CSRF": "跨站請求偽造。攻擊者誘導已登入的使用者在不知情下送出操作（例如改密碼、轉帳）。",
    "SPF": "在 DNS 上公告「哪些伺服器有資格用我的網域寄信」，別人冒名寄信時較容易被擋下。",
    "DMARC": "搭配 SPF 使用，告訴收信方「查到冒名信件時要怎麼處理」（放行、隔離或退回）。",
    "DNSSEC": "為 DNS 查詢結果加上數位簽章，避免有人竄改網域解析把訪客導到假網站。",
    "SRI": "子資源完整性。為外部載入的 JS/CSS 加上指紋，檔案被竄改時瀏覽器會拒絕執行。",
    "CORS": "跨來源資源共用。控制哪些其他網站可以用瀏覽器讀取你的 API 回應。",
    "X-Frame-Options": "限制你的網頁能不能被別的網站嵌入框架，用來防止點擊劫持。",
    "X-Content-Type-Options": "要求瀏覽器嚴格照宣告的檔案類型處理，不要自行猜測。",
    "canonical": "標準網址。同一份內容有多個網址時，指定哪一個才是正式版本，避免搜尋權重被分散。",
    "JSON-LD": "一種結構化資料格式，讓搜尋引擎與 AI 更準確理解頁面在講什麼。",
    "robots.txt": "放在網站根目錄的檔案，用來告訴各種爬蟲哪些路徑可以抓、哪些不要抓。",
    "llms.txt": "類似 robots.txt 的新興慣例，用來對 AI 模型說明網站內容與可引用範圍。",
    "WAF": "網站應用防火牆。擋在網站前面過濾惡意請求的防護層。",
    "PII": "個人可識別資訊，例如 Email、手機號碼、身分證字號。",
    "TLS": "網路傳輸加密協定，HTTPS 底層用的就是它（早期稱為 SSL）。",
    "OWASP": "國際公認的網站安全風險分類，A01~A10 代表十大類風險。",
    "CWE": "國際通用的軟體弱點編號系統，用來精確指出是哪一種弱點。",
}

# 「為什麼要在意」：只陳述該分類的一般性後果，不臆測個案細節。
CATEGORY_IMPACT = {
    "security": "這類問題會被攻擊者利用，可能導致網站被入侵、使用者資料外洩，"
                "或你的網域被冒用來寄送釣魚信件，連帶損害品牌信任。",
    "seo": "這類問題會讓搜尋引擎較難正確理解與收錄你的頁面，"
           "潛在客戶用關鍵字搜尋時，你的網站可能排在競爭對手後面。",
    "aeo": "這類問題會讓 AI 助理在回答使用者提問時，較難引用你的內容，"
           "等於在新的搜尋入口上失去曝光機會。",
    "geo": "這類問題會讓生成式搜尋引擎難以擷取與理解你的頁面主題，"
           "影響你的內容被 AI 摘要與推薦的機會。",
    "ux": "這類問題會讓訪客在瀏覽或操作時遇到阻礙，"
          "直接反映在跳出率與轉換率上。",
}

# info 有兩種：正向指標（「探針被 WAF 擋下，代表防護有效」）與可改的小問題
# （缺 X-Content-Type-Options、缺 canonical）。scan 28 的 5 個 info 裡只有 1 個
# 是正向。所以這段文字兩者都要成立——既不能套 CATEGORY_IMPACT 那套「會被攻擊者
# 利用」（對正向指標完全相反），也不能宣告「不需要任何修補動作」（對另外 4 個
# 是叫人別管一個其實可以改的東西，而且下一行就印出修補方式，自相矛盾）。
INFO_NOTE = (
    "這是一項影響較小的觀察項目，不屬於需要立即處理的風險。"
    "若下方列有修補方式，可視情況安排。"
)

SEVERITY_URGENCY = {
    "critical": "這是本次掃描中最高等級的風險，建議立即處理。",
    "high": "建議優先排入處理，不要拖過本次維護週期。",
    "medium": "建議排入近期的維護排程。",
    "low": "屬於體質項目，可與其他改善一起處理。",
}

CATEGORY_VERIFY = {
    "security": "修補後重新執行一次 Argus 掃描，確認此項目不再出現。"
                "若要立即自行確認，可請你的網站維護人員依上方「怎麼修」的步驟逐項檢查。",
    "seo": "修補後重新執行一次 Argus 掃描確認此項目消失，"
           "並可用 Google Search Console 觀察後續的索引狀態。",
    "aeo": "修補後重新執行一次 Argus 掃描確認此項目消失。",
    "geo": "修補後重新執行一次 Argus 掃描確認此項目消失。",
    "ux": "修補後重新執行一次 Argus 掃描確認此項目消失，並請實際操作一次該流程。",
}

# 「為什麼要在意」按 rule_id 客製：給出具體後果（會被怎樣、影響誰、花多少成本），
# 而不是只用 CATEGORY_IMPACT 那套通用模板。rule_id 為空或沒列在這裡時退回
# CATEGORY_IMPACT，再退回 generic。report.py 2026-08-30 後新增。
RULE_IMPACT = {
    # --- security ---
    "SECURITY_PII_8B24BB8B28":
        "這類個資外洩通常會登上新聞。依台灣《個資法》第 27 條與第 29 條，"
        "未盡安全維護義務可處新台幣 5 萬至 50 萬元罰鍰；若個資被盜用，"
        "還可能面對每位當事人 500 至 30,000 元的團體訴訟賠償（消保法第 51 條，"
        "可乘以消費者人數）。品牌信任流失的長期成本更難量化。",
    "SECURITY_CSRF_TOKEN_1BC47D8B6C":
        "CSRF 漏洞可讓攻擊者在你不知情下，用你的身份在已登入狀態執行操作——"
        "例如變更密碼、修改收件地址、下單、或在後台發文。常見情境是攻擊者誘導"
        "管理員點一個連結，就在後台新增了一個管理員帳號。",
    "SECURITY_CSP_BD010B5BE0":
        "沒有 CSP 等同於網頁被植入惡意腳本時（XSS 攻擊成功後），瀏覽器不會"
        "擋下任何外連請求。攻擊者可把你的使用者資料送到自己的伺服器，"
        "或在他們控制的頁面重新顯示你的內容做釣魚。",
    "SECURITY_HSTS_6A08D9EE20":
        "使用者第一次用 HTTP 連到你的網站（被人偷偷改 DNS、在咖啡廳 wifi 被"
        "劫持、或點了一個寫錯協定的舊連結），就可能被導向假網站並輸入密碼。"
        "HSTS 強迫瀏覽器之後一律走 HTTPS，消掉這個窗口。",
    "dns-spf-missing":
        "沒設 SPF 等於公開邀請別人用你的網域寄詐騙信。攻擊者註冊一台主機、"
        "用你的網域當寄件者，銀行、PayPal、客戶收到的「釣魚信」看起來就像"
        "你公司寄的。常見後果：客戶被騙後提告、你的網域被各大郵件商列入黑名單，"
        "連正常信件都送不到客戶信箱。",
    "dns-dnssec-missing":
        "沒有 DNSSEC，DNS 回應可以被中間人竄改——使用者輸入你的網址，"
        "卻被導向攻擊者的假網站。雖然目前 ISP 多半還沒全面支援 DNSSEC 驗證，"
        "但攻擊者只挑沒驗證的網站下手時你不會知道。",
    "dns-dmarc-policy-weak":
        "DMARC p=none 等於只記錄、不執行的稽核日誌。收件端看到冒名信時不會"
        "擋，照樣送進使用者信箱。建議至少 p=quarantine 進垃圾信件匣。",
    "SECURITY_X_FRAME_OPTIONS_A7A326FEA9":
        "沒有 X-Frame-Options（或 frame-ancestors CSP），你的頁面可以被任意"
        "嵌入 iframe 做「點擊劫持」——使用者以為在點按鈕，實際點到 iframe 裡"
        "攻擊者的隱形按鈕。常見情境：使用者被誘導在你的網站上「按同意」"
        "轉帳或刪除資料。",
    "SECURITY_X_CONTENT_TYPE_OPTIONS_89053405E6":
        "少了這個 header，舊版 IE 會主動「猜測」副檔名——例如把上傳的圖片"
        "當 JavaScript 執行。現代瀏覽器大多有預設保護，但仍建議明確加上。",

    # --- seo ---
    "SEO_H1_48F33C13CC":
        "Google 會把第一個 H1 視為頁面主題的主要訊號。多個 H1 或沒有 H1 都會"
        "降低搜尋引擎對「這頁在講什麼」的信心，自然排序會略低於同業。",
    "SEO_META_TITLE_0D9B1FE9E2":
        "title 太短（<10 字）浪費了 SEO 訊號，太長（>65 字）在搜尋結果會被截斷。"
        "中文常見最佳長度是 20-30 字。會直接影響點擊率——使用者看搜尋結果時，"
        "看得到但不吸引人的 title 會被跳過。",
    "SEO_META_DESCRIPTION_3ABE67FCFF":
        "Google 不會把 meta description 當排名因素，但會直接拿來當搜尋結果的"
        "說明文字。缺這段時 Google 會從頁面自動抓一段，常抓得不理想（會出現"
        "導航文字、亂碼）。直接影響搜尋結果的點擊率。",
    "SEO_CANONICAL_URL_A7D2F47ED2":
        "沒有 canonical 時，同一份內容若有多個網址（HTTP/HTTPS、含/不含 www、"
        "加上 UTM 參數等），Google 會各自收錄並互相競爭排名。設定後 Google"
        "只把搜尋權重集中到指定的那個網址。",

    # --- geo / aeo ---
    "GEO_JAVASCRIPT_EEE24E55B4":
        "ChatGPT Search、Perplexity、Google AI Overview 等生成式搜尋引擎"
        "不會執行 JavaScript——它們只看伺服器回傳的初始 HTML。你的核心內容"
        "如果只在 JavaScript 渲染後才出現，等於在新的搜尋入口上完全隱形。"
        "目前的客戶若改用 AI 搜尋，你的網站就搜不到。",
    "GEO_JSON_LD_8B386F956C":
        "沒有結構化資料時，AI 搜尋引擎只能用「猜的」方式理解你的頁面主題。"
        "加上 JSON-LD 後，AI 能精準辨識 Organization、Product、FAQ 等實體，"
        "回答使用者問題時更可能引用你。",
    "GEO_GENERAL_0576832FB5":
        "沒有 <main> 等語意標籤時，AI 與螢幕閱讀器只能看到整頁文字流，"
        "難以分辨「這段是導航」「那段是內容」。加上後，你的核心內容會更"
        "容易被擷取為引用片段。",
    "GEO_GENERAL_A8C8023032":
        "AI 引用內容時偏好「可獨立成立的段落」——有明確主題、定義、數據來源。"
        "段落太短（< 50 字）或只有一句話時，AI 會跳過不引用。",
    "GEO_ROBOTS_TXT_AI_AFFA24D778":
        "robots.txt 阻擋了 GPTBot / ClaudeBot / Google-Extended，代表這些"
        "AI 系統不會抓你的內容做訓練與引用——會大幅降低你在 AI 回答中的"
        "曝光。如果你希望被 AI 引用，需要把這些 User-Agent 從 robots 移除"
        "或在 /llms.txt 提供可引用範圍。",
}

# 「修好了怎麼確認」按 rule_id 客製：給出具體可執行的驗收指令（curl、瀏覽器、開發者工具），
# 而不是叫使用者「再掃一次 Argus」。
RULE_VERIFY = {
    "SECURITY_PII_8B24BB8B28":
        "在終端機執行 curl -s https://你的網域 | grep -E \"@|09[0-9]{8}\"，"
        "應找不到明文個資。或用瀏覽器開發者工具搜尋頁面原始碼，確認電話、"
        "Email、身分證字號都已遮罩或移除。",
    "SECURITY_CSRF_TOKEN_1BC47D8B6C":
        "檢視表單 HTML（瀏覽器右鍵 → 檢視原始碼）：每個 method=POST 的表單"
        "都應該有隱藏欄位如 csrfmiddlewaretoken 或 _csrf_token，"
        "且值會隨 session 更新。或用 Burp Suite 攔截請求確認。",
    "SECURITY_CSP_BD010B5BE0":
        "在終端機執行 curl -I https://你的網域 | grep -i content-security-policy，"
        "應看到 CSP header。或開瀏覽器開發者工具 → Network → 點首頁 → 看 Response Headers。",
    "SECURITY_HSTS_6A08D9EE20":
        "在終端機執行 curl -I https://你的網域 | grep -i strict-transport-security，"
        "應看到 max-age=31536000 之類的設定。或到 https://hstspreload.org 查詢你的網域。",
    "dns-spf-missing":
        "在終端機執行 dig TXT 你的網域，應看到 v=spf1 ... -all 的記錄。"
        "再到 https://mxtoolbox.com/spf.aspx 線上驗證語法正確性。",
    "dns-dnssec-missing":
        "在終端機執行 dig DNSKEY 你的網域，應有 DNSKEY 記錄。"
        "或到 https://dnssec-analyzer.verisignlabs.com 線上查驗。",
    "dns-dmarc-policy-weak":
        "在終端機執行 dig TXT _dmarc.你的網域，應看到 v=DMARC1; p=quarantine 或 p=reject。"
        "再到 https://mxtoolbox.com/dmarc.aspx 線上驗證。",
    "SECURITY_X_FRAME_OPTIONS_A7A326FEA9":
        "在終端機執行 curl -I https://你的網域 | grep -i x-frame-options，"
        "應看到 DENY 或 SAMEORIGIN。CSP 的 frame-ancestors 也算合格。",
    "SECURITY_X_CONTENT_TYPE_OPTIONS_89053405E6":
        "在終端機執行 curl -I https://你的網域 | grep -i x-content-type-options，"
        "應看到 nosniff。",
    "SEO_H1_48F33C13CC":
        "在每個頁面的 HTML 中應該只有一個 <h1> 標籤。用瀏覽器開發者工具的"
        "Elements 面板搜尋 <h1，確認數量 = 1。",
    "SEO_META_TITLE_0D9B1FE9E2":
        "用瀏覽器開發者工具看每頁 <title> 的字元數（含空白），應在 20-60 字元。"
        "或在 https://www.seoreviewtools.com/serp-preview/ 預覽 Google 顯示效果。",
    "SEO_META_DESCRIPTION_3ABE67FCFF":
        "用瀏覽器開發者工具看每頁 <meta name=description> 內容，"
        "應在 50-160 字元之間且與頁面主題相關。",
    "SEO_CANONICAL_URL_A7D2F47ED2":
        "用瀏覽器開發者工具看每頁 HTML 應有 <link rel=canonical href=...>。"
        "或在 https://search.google.com/search-console 提交 sitemap 觀察索引狀態。",
    "GEO_JAVASCRIPT_EEE24E55B4":
        "在終端機執行 curl -s https://你的網域 | wc -m，數字應接近「用瀏覽器"
        "開啟後可見到的文字量」（差異 < 30%）。若 curl 看到的字數明顯少於"
        "瀏覽器看到的，代表核心內容依賴 JavaScript。",
    "GEO_JSON_LD_8B386F956C":
        "用瀏覽器開發者工具的 Elements 面板搜尋 application/ld+json，"
        "應至少有一個 JSON-LD 腳本。到 https://validator.schema.org 驗證語法。",
    "GEO_GENERAL_0576832FB5":
        "用瀏覽器開發者工具的 Elements 面板搜尋 <main，應該找到一個 "
        "（且只有一個）。或到 https://wave.webaim.org 跑無障礙檢查。",
    "GEO_GENERAL_A8C8023032":
        "每個頁面至少要有 3 段以上、每段 50 字以上的文字內容（不含導航、"
        "選單、頁尾）。可在開發者工具 Console 執行 document.querySelectorAll('p').length "
        "看段落數量。",
    "GEO_ROBOTS_TXT_AI_AFFA24D778":
        "在終端機執行 curl -s https://你的網域/robots.txt，"
        "應不再有 Disallow: / 對 GPTBot、ClaudeBot、Google-Extended。"
        "或到 https://support.google.com/webmasters/answer/6062596 測試 robots 規則。",
}


def _impact_for(finding) -> str:
    """依 rule_id 找客製文案，找不到退回 CATEGORY_IMPACT，再退回通用字串。

    順序：RULE_IMPACT[rule_id] → CATEGORY_IMPACT[category] → "請依你的業務情境評估影響。"
    """
    rule_id = (finding.rule_id or "").strip()
    if rule_id in RULE_IMPACT:
        return RULE_IMPACT[rule_id]
    category = (finding.category or "").lower()
    if category in CATEGORY_IMPACT:
        return CATEGORY_IMPACT[category]
    return "請依你的業務情境評估影響。"


def _verify_for(finding) -> str:
    """同 _impact_for，但用於「修好了怎麼確認」段落。"""
    rule_id = (finding.rule_id or "").strip()
    if rule_id in RULE_VERIFY:
        return RULE_VERIFY[rule_id]
    category = (finding.category or "").lower()
    if category in CATEGORY_VERIFY:
        return CATEGORY_VERIFY[category]
    return "修補後重新執行一次 Argus 掃描確認此項目消失。"

DISCLAIMER = (
    "免責聲明：本報告僅反映掃描當下、從網際網路可觀測到的外部特徵，"
    "不等同完整滲透測試或原始碼稽核，也不構成法律或合規意見。"
    "未列出的項目不代表不存在風險。實際修補請由具備權限的維運人員評估後執行。"
)

_CJK_FONT = "Microsoft JhengHei"


def build_report_number(scan_job: ScanJob) -> str:
    """產生對外揭露的報告編號：ARGUS-{掃描編號}-{日期}-{4 碼驗證碼}。

    驗證碼用 SECRET_KEY 做 HMAC，讓編號無法被憑空捏造出「看起來合理」的值；
    只取 4 碼是因為它防的是隨手偽造，真正的比對靠查驗端點與內容雜湊。

    刻意只用 scan_job 的固定欄位（不含產生時間），所以**重新產生報告時編號不變**
    ——報告一旦交付就可能被轉寄存檔，換編號會讓已流出的副本失效。
    """
    issued = scan_job.completed_at or scan_job.created_at or timezone.now()
    token = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"argus-report:{scan_job.pk}".encode(),
        sha256,
    ).hexdigest()[:4].upper()
    return f"ARGUS-{scan_job.pk}-{issued.strftime('%Y%m%d')}-{token}"


# 報告用的品牌圖檔必須放在 backend/ 之內：backend image 只有 COPY backend ./backend，
# 不含 frontend/。放在 frontend/public/ 時 exists() 一律為 False，封面會靜默退回
# 純文字——本機與測試都看不出來，只有正式站的報告少了藝術字。
_REPORT_ASSETS = Path(__file__).resolve().parent / "report_assets"


def get_severity_display(severity: str) -> str:
    return SEVERITY_DISPLAY.get(severity, severity or "未知")


def _render_severity(severity: str) -> str:
    """給 report_render 用的嚴重度標籤。

    必須是 report_render/theme.py SEVERITY 表裡的值——它會直接拿去查色塊與排序，
    查不到就 KeyError、整份報告產不出來。未知等級退回「資訊提示」：報告少一格
    顏色，好過因為某個 scanner 寫了新等級就整份掛掉。
    """
    label = get_severity_display(severity)
    return label if label in SEVERITY_DISPLAY.values() else "資訊提示"


def mask_pii_evidence(text: str) -> str:
    """報告展示層遮罩：evidence 含原始個資（email/手機/身分證/信用卡）就地遮罩。

    這份 .docx 會被下載、轉寄、存檔，直接印出原始內容有明確合規風險。只保留頭尾供
    人工比對，不修改 DB 內的原始 Finding 記錄。

    對「所有」finding 的 evidence 都套用（不靠 rule_id 前綴判斷是否為 PII finding）：
    除了 scanners.py::analyze_data_exposure() 產生的 SECURITY_PII_* finding，
    security/exposure_scanner.py 的敏感檔案外洩 finding 也會把命中檔案的原始內容
    片段放進 evidence，一樣可能含未遮罩個資，用 rule_id 白名單很容易漏掉這類來源；
    正則對不含 PII 樣式的文字（如 header 名稱、URL）是無操作，不會誤傷正常內容。
    """
    return redact_pii_in_text(text)


def _group_findings_for_report(findings) -> list[dict]:
    """同一個 rule_id 的 finding 合併成一筆，受影響頁面收斂成清單。

    合併鍵只用 rule_id。rule_id 由 scanners._default_rule_id() 從 category + title
    的雜湊產生，同一種問題不論出現在哪一頁都一致。舊版把 evidence 也放進鍵裡，
    但 evidence 帶的是該頁專屬內容（例如那一頁實際的 title 文字），於是同一個問題
    出現在 N 頁就被拆成 N 筆顯示——scan 25 的報告因此把「Meta title 長度不理想」
    列了 4 次、「核心內容高度依賴 JavaScript 渲染」列了 3 次。

    rule_id 為空時退回 finding.pk，避免不同問題只因為「都沒有 rule_id」被錯誤
    合併成一筆。只影響 .docx 呈現順序與分組，不改資料庫裡的原始 Finding 記錄。
    """
    groups: OrderedDict[str, dict] = OrderedDict()
    for finding in findings:
        key = finding.rule_id or f"_finding:{finding.pk}"
        group = groups.get(key)
        if group is None:
            group = {"finding": finding, "pages": []}
            groups[key] = group
        page_label = finding.page.final_url if finding.page else "站台層級"
        if page_label not in group["pages"]:
            group["pages"].append(page_label)
    return list(groups.values())


# --- 低階排版工具 -----------------------------------------------------


def _previous_completed_scan(scan_job: ScanJob):
    """同一位使用者、同一個 origin 的上一次完成掃描。

    只看本人的掃描：同一個網址可能被不同使用者掃過，拿別人的結果當「前次」
    既不合理也會洩漏他人的掃描存在。未完成或沒有分數的掃描不算。
    """
    if scan_job.completed_at is None:
        return None
    return (
        ScanJob.objects.filter(
            user_id=scan_job.user_id,
            origin=scan_job.origin,
            status=ScanJob.Status.COMPLETED,
            overall_score__isnull=False,
            completed_at__lt=scan_job.completed_at,
        )
        .exclude(pk=scan_job.pk)
        .order_by("-completed_at")
        .first()
    )


# 受影響頁面最多列這麼多個，其餘收成「等，另 N 處」。完整清單見掃描頁面清單。
_MAX_LISTED_PAGES = 5
# 證據顯示上限。放寬的話單一項目就能吃掉大半頁。
_MAX_EVIDENCE_CHARS = 300


def _pages_label(pages: list[str]) -> str:
    if len(pages) == 1:
        return pages[0]
    return f"影響 {len(pages)} 個頁面"


def _description_for_report(finding) -> str:
    """去掉 description 開頭與報告行為矛盾的警語。

    scanners.py 的 PII finding 在 description 開頭寫「⚠️ 此項目顯示原始個資，
    請依個資法妥善處理本報告。」——那句對前端成立（依使用者要求，API/畫面顯示
    未遮罩的 evidence），但報告會遮罩（09******90），照搬進來就是假話。報告本來
    就會在「檢測依據」下輸出自己那句正確的遮罩提示，不需要這一句。

    規則故意寫得寬鬆（剝掉開頭所有 ⚠️ 起始行）而不是比對特定字串：警語措辭改了
    也不會漏掉，而 description 的實質內容不會以 ⚠️ 開頭。
    """
    lines = (finding.description or "").splitlines()
    while lines and lines[0].lstrip().startswith("⚠️"):
        lines.pop(0)
    return "\n".join(lines).strip() or "（無）"


def _collect_glossary_terms(grouped_findings) -> list[tuple[str, str]]:
    """只挑這份報告裡真的出現過的術語，不是貼一份固定清單。"""
    corpus_parts: list[str] = []
    for item in grouped_findings:
        finding = item["finding"]
        corpus_parts += [
            finding.title or "", finding.description or "",
            finding.remediation or "", finding.evidence or "",
            finding.owasp_category or "", finding.cwe_id or "",
        ]
    corpus = "\n".join(corpus_parts).lower()
    return [
        (term, explanation)
        for term, explanation in GLOSSARY.items()
        if term.lower() in corpus
    ]


def _scan_scope_rows(scan_job: ScanJob) -> dict:
    """掃描範圍。scope 一律取自 scan_plan，不在這裡重複「max_pages==1 代表單頁」。"""
    scope = "單頁" if build_scan_execution_plan(scan_job).scope == "single" else "全網站"
    return {
        "掃描範圍": scope,
        "探測模式": scan_job.get_scan_mode_display(),
        "頁數上限": str(scan_job.max_pages),
        "連結深度上限": str(scan_job.max_depth),
        "實際掃描頁數": str(scan_job.pages.count()),
        "遵守 robots.txt": "是" if scan_job.respect_robots else "否",
    }


def _scan_warning_lines(scan_job: ScanJob) -> list[str]:
    """對收件者有意義的掃描警示。

    內部運維資訊（settlement_error 的計費結算、agent 的 token 用量）刻意不輸出。
    截圖失敗與「頁面擷取失敗」措辭必須分開：截圖失敗的那一頁其實有抓到也分析過。
    """
    warnings = scan_job.warning_summary or {}
    lines: list[str] = []
    if warnings.get("scan_effectiveness") == "no_pages_crawled":
        lines.append(
            "掃描有效性警示：本次未抓到任何頁面（目標可能不可達或全部逾時）。"
            "SEO 與 AEO 未評估，分數僅反映站台層級檢查，不應解讀為「網站沒有問題」。"
        )
    for key, template in (
        ("blocked_urls", "依 robots.txt 或掃描範圍限制，略過 {n} 個頁面未檢查。"),
        ("failed_urls", "有 {n} 個頁面擷取失敗（逾時或回應異常），未納入本次分析。"),
        (
            "screenshot_failures",
            "有 {n} 個頁面的截圖未能保存（不影響該頁的檢測結果，僅少了畫面佐證）。",
        ),
    ):
        value = warnings.get(key) or []
        if isinstance(value, list) and value:
            lines.append(template.format(n=len(value)))
    tech_stack = warnings.get("tech_stack") or []
    if isinstance(tech_stack, list) and tech_stack:
        lines.append(f"偵測到的技術棧：{'、'.join(str(item) for item in tech_stack)}")
    return lines


def _entry_screenshot(scan_job: ScanJob) -> Path | None:
    """入口頁截圖。只放一張——全頁截圖體積大，整份塞進去會讓 .docx 失控。

    路徑慣例與 views.py 的 screenshot action 一致：相對於 BASE_DIR。
    """
    entry = scan_job.pages.exclude(screenshot_path="").order_by("depth", "id").first()
    if entry is None:
        return None
    path = Path(settings.BASE_DIR) / entry.screenshot_path
    return path if path.exists() else None


def _severity_rank(severity: str) -> int:
    order = ["critical", "high", "medium", "low", "info"]
    return order.index(severity) if severity in order else len(order)


def _resolved_since(previous, grouped) -> list[str]:
    """前次有、這次沒有的項目＝已解決。"""
    if previous is None:
        return []
    current = {item["finding"].rule_id for item in grouped if item["finding"].rule_id}
    return [
        title
        for rule, title in previous.findings.values_list("rule_id", "title")
        if rule and rule not in current
    ]


def _headline(scan_job: ScanJob, previous, category_scores: dict, resolved=()) -> str:
    """一頁摘要的導讀句。只陳述資料本身，不加沒有根據的評價。"""
    score = scan_job.overall_score
    parts = []
    if isinstance(score, int):
        parts.append(f"分數落在「{_score_band_label(score)}」區間")
    if previous is not None and isinstance(score, int):
        delta = score - previous.overall_score
        if delta > 0:
            parts.append(f"較前次進步 {delta} 分")
        elif delta < 0:
            parts.append(f"較前次下降 {abs(delta)} 分")
        else:
            parts.append("與前次持平")
    # schema 沒有 resolved 欄位，但「修好了 N 項」是回訪使用者最想看到的資訊，
    # 收進導讀句而不是讓它消失。
    if resolved:
        parts.append(f"已解決 {len(resolved)} 項")
    weakest = sorted(
        ((name, value) for name, value in category_scores.items() if isinstance(value, int)),
        key=lambda item: item[1],
    )[:2]
    if weakest:
        names = "與".join(CATEGORY_DISPLAY.get(c, c.upper()).split()[0] for c, _ in weakest)
        parts.append(f"主要待補強的是{names}")
    return "這一頁讓你 30 秒掌握整體狀況：" + "；".join(parts) + "。細節見後續章節。"


def _score_band_label(score: int) -> str:
    for threshold, label, _ in SCORE_BANDS:
        if score >= threshold:
            return label
    return "需優先處理"


def build_report_payload(scan_job: ScanJob) -> dict:
    """把一次掃描轉成 report_render 的輸入 JSON（契約見 report_render/schema.json）。

    這裡是報告的「資料層」：去重分組、評分、與前次比較、術語過濾、per-rule 文案、
    PII 遮罩全部發生在這一支，排版完全交給 report_render。分開的好處是排版可以整套
    抽換（本次就是），而這些領域規則與它們的測試一行都不用動。
    """
    grouped = _group_findings_for_report(scan_job.findings.select_related("page").all())
    # 依嚴重度排序後才編號：report_render 會依嚴重度分組顯示，先排好編號才會連續。
    grouped.sort(key=lambda item: _severity_rank(item["finding"].severity))

    category_scores = scan_job.category_scores or {}
    previous = _previous_completed_scan(scan_job)
    scan_date = (scan_job.completed_at or scan_job.created_at or timezone.now()).strftime(
        "%Y-%m-%d"
    )

    findings_payload = []
    ref_by_rule: dict[str, str] = {}
    for index, item in enumerate(grouped, start=1):
        finding = item["finding"]
        pages = item["pages"]
        ref = f"4.{index}"
        if finding.rule_id:
            ref_by_rule[finding.rule_id] = ref
        entry = {
            "id": ref,
            "title": finding.title,
            "severity": _render_severity(finding.severity),
            "category": CATEGORY_DISPLAY.get(finding.category, finding.category.upper()),
            "scope": _pages_label(pages),
            "problem": _description_for_report(finding),
            "fix": finding.remediation or "（無）",
            # 先遮罩再截斷：反過來做的話 PII 數值可能剛好被截斷點切一半，
            # 殘缺數字命不中 regex，反而以明文殘留。
            "evidence": mask_pii_evidence(finding.evidence or "")[:_MAX_EVIDENCE_CHARS],
        }
        if len(pages) > 1:
            shown = "、".join(pages[:_MAX_LISTED_PAGES])
            if len(pages) > _MAX_LISTED_PAGES:
                shown += f" 等，另 {len(pages) - _MAX_LISTED_PAGES} 處"
            entry["urls"] = shown
        findings_payload.append(entry)

    payload: dict = {
        "meta": {
            "site_url": scan_job.normalized_url,
            "report_id": build_report_number(scan_job),
            "generated_at": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "summary": {
            "overall_score": scan_job.overall_score or 0,
            "scan_date": scan_date,
            "headline": _headline(
                scan_job, previous, category_scores, _resolved_since(previous, grouped)
            ),
            # 全部 5 個分類都列出；未評估的給 null，report_render 會標「未評估」
            # 且不計入顏色。缺鍵＝未評估是 calculate_scores() 的既有契約。
            "categories": [
                {
                    "name": CATEGORY_DISPLAY.get(category, category.upper()),
                    "score": category_scores.get(category),
                }
                for category in Finding.Category.values
            ],
        },
        "findings": findings_payload,
    }

    if previous is not None:
        payload["summary"]["previous"] = {
            "date": previous.completed_at.strftime("%m-%d"),
            "score": previous.overall_score,
        }
        previous_rules = {
            rule for rule in previous.findings.values_list("rule_id", flat=True) if rule
        }
        appeared = [
            item["finding"].title
            for item in grouped
            if item["finding"].rule_id and item["finding"].rule_id not in previous_rules
        ]
        if appeared:
            payload["summary"]["new_findings"] = appeared

    priorities = []
    for action in scan_job.top_actions or []:
        priorities.append({
            "severity": _render_severity(action.get("severity", "")),
            "problem": action.get("title", ""),
            "category": CATEGORY_DISPLAY.get(
                action.get("category", ""), str(action.get("category", "")).upper()
            ),
            "ref": next(
                (f["id"] for f in findings_payload if f["title"] == action.get("title")), ""
            ),
        })
    if priorities:
        payload["priorities"] = priorities

    # 分類的「沒處理會怎樣」講一次；只列有非 info 發現的分類——某分類若只有正向的
    # 資訊提示（例如只偵測到 WAF 保護），寫「會被攻擊者利用」就是把好消息說成威脅。
    why_matters = []
    seen_categories: set[str] = set()
    for item in grouped:
        finding = item["finding"]
        if finding.severity == Finding.Severity.INFO or finding.category in seen_categories:
            continue
        seen_categories.add(finding.category)
        why_matters.append({
            "category": CATEGORY_DISPLAY.get(finding.category, finding.category.upper()),
            "consequence": _impact_for(finding),
        })
    if why_matters:
        payload["why_matters"] = why_matters

    scan_info: dict = {"scope": _scan_scope_rows(scan_job)}
    warning_lines = _scan_warning_lines(scan_job)
    if warning_lines:
        scan_info["warnings"] = warning_lines
    screenshot = _entry_screenshot(scan_job)
    if screenshot is not None:
        scan_info["screenshot"] = str(screenshot)
        entry_page = scan_job.pages.exclude(screenshot_path="").order_by("depth", "id").first()
        scan_info["screenshot_caption"] = (
            f"{entry_page.final_url or entry_page.url}（掃描當下擷取）"
        )
    payload["scan_info"] = scan_info

    appendix: dict = {}
    glossary = _collect_glossary_terms(grouped)
    if glossary:
        appendix["glossary"] = [
            {"term": term, "explanation": explanation} for term, explanation in glossary
        ]
    if grouped:
        appendix["tech_index"] = [
            {
                "ref": item_ref,
                "rule_id": item["finding"].rule_id or "—",
                "owasp_cwe": (
                    f"{item['finding'].owasp_category or '—'} / {item['finding'].cwe_id or '—'}"
                ),
            }
            for item_ref, item in zip(
                [f["id"] for f in findings_payload], grouped, strict=True
            )
        ]
    # 通用說明與 AI 用法一定要在，per-rule 驗收指令是補充而不是取代——只給
    # per-rule 的話，沒有對應 rule 的發現就完全沒有驗證指引，AI 用法也整段消失。
    verify_notes = [
        "完成修補後，重新執行一次 Argus 掃描，確認對應項目不再出現；"
        "下一份報告的摘要會列出這次解決了哪些項目。",
        "想更深入了解任何一項：把該項的「問題是什麼」「怎麼修」「檢測依據」"
        "三段文字複製起來，貼給 ChatGPT、Claude 等 AI 助手並補一句"
        "「請說明這個問題的影響與具體修復步驟」即可。",
    ]
    # 只取真正的 per-rule 驗收指令，不用 _verify_for()——它在沒有對應規則時會退回
    # CATEGORY_VERIFY，而那段文字本來就含「重新執行一次 Argus 掃描」，會與上面的
    # 通用說明重複。per-rule 是補充，通用說明已經涵蓋沒有對應規則的情況。
    for item in grouped:
        note = RULE_VERIFY.get(item["finding"].rule_id or "")
        if note and note not in verify_notes:
            verify_notes.append(note)
    appendix["verify_note"] = " ".join(verify_notes)
    consent = getattr(scan_job, "authorization_consent", None)
    if consent is not None:
        # 刻意不寫 ip_address / user_agent / 授權帳號：報告會被下載轉寄給第三方，
        # 授權人的 IP 與瀏覽器指紋是個資，對收件者零價值只增加外洩面。
        appendix["authorization"] = {
            "授權網域": consent.authorized_domain,
            "授權時間": consent.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "主動測試授權": "是" if consent.active_testing_authorized else "否（僅被動偵測）",
            "授權聲明": consent.statement,
        }
    else:
        appendix["authorization"] = {
            "授權紀錄": "查無授權紀錄。若這份報告要作為稽核依據，請先確認授權來源。"
        }
    payload["appendix"] = appendix
    return payload


def report_output_path(scan_job: ScanJob) -> Path:
    """報告檔案位置。views.py 判斷快取時也用這支，避免兩邊各寫一次檔名慣例。"""
    return Path(settings.MEDIA_ROOT) / "reports" / f"scan-{scan_job.id}-report.docx"


def build_scan_report(scan_job: ScanJob) -> str:
    """產生 Word 報告。

    資料層與排版層分離：本模組只負責把掃描結果整理成 report_render 的輸入
    （build_report_payload），版面、配色、圖表、浮水印全部由 report_render 決定。
    分開的好處是排版可以整套抽換，而領域規則與它們的測試一行都不用動。
    """
    output_path = report_output_path(scan_job)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = build_report_payload(scan_job)
    generated_at = timezone.now()
    generate_report(payload, str(output_path))

    # 雜湊算完才寫防偽紀錄：報告本身不印雜湊（印了就循環相依——雜湊要涵蓋整份
    # 檔案，而檔案裡又要有雜湊），收件者拿編號到查驗頁取得雜湊自行比對。
    #
    # 重產時舊雜湊要留下來。排版升級會讓同一次掃描產出不同位元組的檔案，若直接
    # 覆蓋 content_sha256，先前已經寄出去的那份報告在查驗頁就會被判定成「對不上」
    # ——等於我們自己把交付過的正本變成偽造品。歷史只留雜湊，不留檔案。
    content_sha256 = sha256(output_path.read_bytes()).hexdigest()
    existing = ReportVerification.objects.filter(scan_job=scan_job).first()
    history = list(existing.previous_sha256 or []) if existing else []
    if existing and existing.content_sha256 not in (content_sha256, *history):
        history.append(existing.content_sha256)
    ReportVerification.objects.update_or_create(
        scan_job=scan_job,
        defaults={
            "report_number": payload["meta"]["report_id"],
            "content_sha256": content_sha256,
            "generated_at": generated_at,
            "renderer_version": RENDERER_VERSION,
            "previous_sha256": history,
        },
    )
    return str(output_path)
