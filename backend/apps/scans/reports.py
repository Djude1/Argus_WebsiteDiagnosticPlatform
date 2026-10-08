"""健檢報告產生器（排版產生 .docx，對外只提供轉檔後的 PDF）。

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
import tempfile
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.scans import versions
from apps.scans.ai_bots import summary_line as ai_bots_summary
from apps.scans.coverage import incomplete_checks
from apps.scans.models import Finding, ReportVerification, ScanJob
from apps.scans.pagespeed import summary_lines as pagespeed_summary_lines
from apps.scans.report_pdf import convert_docx_to_pdf
from apps.scans.report_render import RENDERER_VERSION, generate_report
from apps.scans.scan_plan import build_scan_execution_plan
from apps.scans.security.observatory import summary_line as observatory_summary
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

# 分數的算法要寫給讀者看，否則「71 分」無從檢驗（值與 scanners.calculate_scores 同步）
SCORE_NOTE = (
    "分數怎麼算：每個分類從 100 分起算，依該分類的發現扣分——嚴重風險 60、高風險 35、中風險 12、"
    "低風險 4、資訊提示 0；同一條規則在同一分類只扣一次（出現在多頁不重複扣）。"
    "分類分數＝100 × e^(−扣分總和 ÷ 50)，扣越多下降越慢、不會直接歸零；"
    "總分是「已評估」各分類分數的平均，每個分類權重相同。"
    "AEO 例外：以「可回答性」為起始分（每題可回答 1、資訊不足 0.5、內容衝突 0.25、無答案 0，"
    "聯絡、價格、期限等核心題權重較高），再依索引限制、標記錯誤等其他 AEO 問題扣分；"
    "網站內容不足以出題時 AEO 不評分，顯示為未充分評估。"
    "這是 Argus 自訂的健康分數模型，用來追蹤同一個網站的改善趨勢，不是產業標準評分，"
    "請搭配各分類分數與具體問題一起解讀。"
)

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
    "aeo": "訪客或 AI 助理問到這些問題時，網站文字無法直接給出具體、可核對的答案，"
           "對方只能轉向其他來源，或得到不正確的資訊。",
    "geo": "這類問題會讓生成式搜尋引擎難以擷取與理解你的頁面主題，"
           "影響你的內容被 AI 摘要與推薦的機會。",
    "ux": "這類問題會讓訪客在瀏覽或操作時遇到阻礙，"
          "直接反映在跳出率與轉換率上。",
}

# info 有兩種：純提醒（「主動掃描 0 項發現，但目標位於 WAF 之後」）與可改的小問題
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
    "security": "用檢測依據中的網址與請求重現一次（瀏覽器開發者工具或 curl），"
                "確認原本觀察到的回應已不存在；再重新掃描作為輔助確認。",
    "seo": "開啟逐頁證據列出的網址，以「檢視原始碼」確認對應標記已修正；"
           "可再用 Google Search Console 觀察後續索引狀態。",
    "aeo": "修改後重新掃描，確認該題的判定變為「可回答」，且證據指向修改後的段落；"
           "也可以直接在證據列出的頁面搜尋題目中的關鍵詞，確認答案以文字寫在頁面上。",
    "geo": "開啟逐頁證據列出的網址，以「檢視原始碼」確認對應的結構或內容已補上。",
    "ux": "用手機或開發者工具的行動版模式開啟逐頁證據列出的網址，實際操作一次確認問題已不存在。",
}

# 「為什麼要在意」按 rule_id 客製：給出具體後果（會被怎樣、影響誰、花多少成本），
# 而不是只用 CATEGORY_IMPACT 那套通用模板。rule_id 為空或沒列在這裡時退回
# CATEGORY_IMPACT，再退回 generic。report.py 2026-08-30 後新增。
RULE_IMPACT = {
    # --- security ---
    "security-pii-personal-contact":
        "若這些資料不是當事人同意公開，可能構成個資法上的不當揭露，並讓當事人收到詐騙或騷擾；"
        "若是刻意公開的聯絡方式，則不屬於外洩。需要網站管理者逐筆確認。",
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
        "部分 AI 爬蟲與搜尋服務不執行、或只有限度執行 JavaScript（各家做法不同且會變動）。"
        "主要內容若只在 JavaScript 執行後才出現，這些系統較可能讀不到或讀不完整；"
        "Google 會執行 JavaScript，但時間較晚、資源有限。這不代表網站不會被搜尋到，"
        "而是讓「不執行 JavaScript 的讀取者」也能拿到主要內容，降低被遺漏的機會。",
    "GEO_JSON_LD_8B386F956C":
        "結構化資料讓搜尋引擎與 AI 更明確知道頁面在講什麼實體（組織、文章、活動、FAQ）。"
        "沒有它網站仍會被收錄與引用，只是系統要自行從內文推斷；是提升理解穩定度的建議，"
        "不是被搜尋或引用的必要條件。",
    "GEO_GENERAL_0576832FB5":
        "沒有 <main> 等語意標籤時，AI 與螢幕閱讀器只能看到整頁文字流，"
        "難以分辨「這段是導航」「那段是內容」。加上後，你的核心內容會更"
        "容易被擷取為引用片段。",
    "GEO_GENERAL_A8C8023032":
        "AI 摘要與引用時，較容易取用「可獨立成立的段落」——有明確主題、定義、數據來源。"
        "這是 Argus 依內容結構提出的建議，不是任何搜尋服務公布的門檻。",
    "geo-ai-search-bots-blocked":
        "OAI-SearchBot、Claude-SearchBot、PerplexityBot 等爬蟲替 AI 搜尋與對話服務讀取網頁；"
        "被 robots.txt 封鎖時，這些服務比較不會引用、連結你的網站。GPTBot、ClaudeBot、"
        "Google-Extended 等是訓練用爬蟲，封鎖它們不影響搜尋與引用，是可以單獨做的商業選擇。",
}

# 「修好了怎麼確認」按 rule_id 客製：給出具體可執行的驗收指令（curl、瀏覽器、開發者工具），
# 而不是叫使用者「再掃一次 Argus」。
RULE_VERIFY = {
    "seo-index-signals-conflict":
        "打開 sitemap.xml 確認證據列出的網址都已移除或改成正式網址；在 Search Console「網址檢查」"
        "輸入這些網址，確認「Google 選擇的標準網址」與「是否允許檢索」符合預期。",
    "seo-structured-data-required":
        "把「逐頁證據」列出的網址貼到 https://search.google.com/test/rich-results，"
        "確認對應項目沒有「缺少必要欄位」的錯誤。",
    "SECURITY_PII_8B24BB8B28":
        "逐一開啟「逐頁證據」列出的網址，用瀏覽器「檢視原始碼」搜尋報告中遮罩前的號碼開頭，"
        "確認已移除（含 HTML 註解）。",
    "security-pii-personal-contact":
        "逐一開啟「逐頁證據」列出的網址，確認每筆資料都有公開依據；不應公開者移除後，"
        "用「檢視原始碼」確認頁面與 HTML 註解中都已找不到。",
    "SECURITY_CSRF_TOKEN_1BC47D8B6C":
        "檢視表單 HTML（瀏覽器右鍵 → 檢視原始碼）：每個 method=POST 的表單"
        "都應該有隱藏欄位如 csrfmiddlewaretoken 或 _csrf_token，"
        "且值會隨 session 更新。或用 Burp Suite 攔截請求確認。",
    "SECURITY_CSP_BD010B5BE0":
        "不能只看標頭是否存在：執行 curl -sI https://你的網域 | grep -i content-security-policy，"
        "確認①是 Content-Security-Policy（不是只有 -Report-Only）；②有 default-src 或 script-src；"
        "③script-src 沒有 'unsafe-inline'／'unsafe-eval' 或 *；④有 object-src 'none' 與 "
        "frame-ancestors。可貼到 https://csp-evaluator.withgoogle.com 檢查。",
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
        "用瀏覽器開發者工具看每頁 <title> 的字數；Argus 的判定門檻是 10–65 字元"
        "（與「怎麼修」相同）。可在 https://www.seoreviewtools.com/serp-preview/ 預覽顯示效果。",
    "SEO_META_DESCRIPTION_3ABE67FCFF":
        "用瀏覽器開發者工具看每頁 <meta name=description> 內容，"
        "應在 50-160 字元之間且與頁面主題相關。",
    "SEO_CANONICAL_URL_A7D2F47ED2":
        "用瀏覽器開發者工具看每頁 HTML 應有 <link rel=canonical href=...>。"
        "或在 https://search.google.com/search-console 提交 sitemap 觀察索引狀態。",
    "GEO_JAVASCRIPT_EEE24E55B4":
        "比較時要用同一種文字擷取方式，不能拿 HTML 原始碼的字元數和畫面文字量比："
        "在瀏覽器開發者工具停用 JavaScript（Settings → Debugger → Disable JavaScript）"
        "後重新整理，確認主要內容仍然看得到。Argus 的判定方式是對初始 HTML 與執行 "
        "JavaScript 後的頁面，都移除 script／style 與標籤、不計空白後比較文字數，"
        "前者少於後者一半即列出。",
    "GEO_JSON_LD_8B386F956C":
        "用瀏覽器開發者工具的 Elements 面板搜尋 application/ld+json，"
        "應至少有一個 JSON-LD 腳本。到 https://validator.schema.org 驗證語法。",
    "GEO_GENERAL_0576832FB5":
        "用瀏覽器開發者工具的 Elements 面板搜尋 <main，應該找到一個 "
        "（且只有一個）。或到 https://wave.webaim.org 跑無障礙檢查。",
    "GEO_GENERAL_A8C8023032":
        "Argus 以區塊標籤（p、div、li、td、標題等）切段，計算 40 字以上的文字區塊；"
        "少於 2 塊或全頁文字少於 300 字時列出。修改後確認主要內容有 2 段以上、"
        "各自成立的完整段落即可。",
    "geo-ai-search-bots-blocked":
        "在終端機執行 curl -s https://你的網域/robots.txt，確認 OAI-SearchBot、Claude-SearchBot、"
        "PerplexityBot、ChatGPT-User 等爬蟲的群組沒有 Disallow: /，也沒有被 User-agent: * 的 "
        "Disallow: / 涵蓋；重新掃描後網站架構分頁的 AI 爬蟲政策表會顯示「允許」。",
}


# 內容類（SEO／AEO／GEO／UX）建議的「規則依據與適用限制」：讓讀者知道 Argus 用什麼門檻判斷、
# 以及這個結論「不代表」什麼，避免把「缺少 llms.txt」讀成「網站不會被 AI 引用」。
RULE_BASIS = {
    "SEO_META_TITLE_0D9B1FE9E2":
        "依據：title 長度 10–65 字元（常見搜尋結果可完整顯示的範圍）。"
        "限制：長度影響顯示與點擊，不是排名的決定因素。",
    "SEO_META_DESCRIPTION_3ABE67FCFF":
        "依據：meta description 50–160 字元。限制：Google 不以 description 排名，"
        "也可能改用頁面內文當搜尋摘要。",
    "SEO_H1_48F33C13CC":
        "依據：每頁恰好 1 個 H1。限制：HTML 允許多個 H1、搜尋引擎也能處理；"
        "這是讓頁面主題更明確的慣例，不是硬性規定。",
    "SEO_CANONICAL_URL_A7D2F47ED2":
        "依據：頁面是否有 <link rel=canonical>。限制：沒有重複網址的頁面缺 canonical 影響很小。",
    "SEO_OPEN_GRAPH_BF05E222E7":
        "依據：og:title／og:description／og:image／og:url 是否齊全。"
        "限制：只影響社群與通訊軟體的分享預覽，不影響搜尋排名。",
    "SEO_ALT_97B655BF66":
        "依據：img 是否有非空的 alt。限制：裝飾性圖片使用空 alt 是正確做法，"
        "列出的數量可能包含這類圖片。",
    "GEO_JSON_LD_8B386F956C":
        "依據：頁面是否含 application/ld+json。限制：缺少結構化資料不代表網站不會被搜尋或 AI 引"
        "用。",
    "GEO_LLMS_TXT_C8A1E5700E":
        "依據：網站根目錄是否有 /llms.txt。限制：llms.txt 是新興慣例，"
        "尚非主要搜尋或 AI 服務公認的標準，缺少不會讓網站無法被引用。",
    "GEO_JAVASCRIPT_EEE24E55B4":
        "依據：初始 HTML 的可見文字少於執行 JavaScript 後的一半（兩者以相同方式擷取）。"
        "限制：各 AI 服務對 JavaScript 的支援不同，無法推論特定服務一定讀不到。",
    "GEO_GENERAL_A8C8023032":
        "依據：40 字以上的文字區塊少於 2 塊，或全頁文字少於 300 字。"
        "限制：這是 Argus 自訂的門檻，不是搜尋服務公布的標準。",
    "aeo-noindex":
        "依據：頁面的 meta robots 或 X-Robots-Tag 含 noindex。"
        "限制：若頁面本來就不打算公開（會員頁、測試頁），這是預期行為。",
    "aeo-nosnippet":
        "依據：meta robots 或 X-Robots-Tag 含 nosnippet／max-snippet:0。"
        "限制：只影響摘要與引用，不影響頁面被收錄。",
    "aeo-markup-syntax":
        "依據：JSON-LD 無法以 JSON 解析。限制：只檢查語法，不檢查型別是否適合該頁。",
    "geo-entity-organization-missing":
        "依據：已檢查頁面的結構化資料中沒有 Organization、LocalBusiness 等組織實體。"
        "限制：只看本次爬到的頁面；組織標記放在沒爬到的頁面時會誤報。",
    "geo-entity-no-same-as":
        "依據：組織實體沒有 sameAs 欄位。限制：sameAs 是協助辨識實體的建議做法，"
        "不保證被知識圖譜或 AI 採用。",
    "geo-article-author-missing":
        "依據：文章頁（Article 類標記，或 og:type=article 且有發布時間）沒有 JSON-LD author、"
        "author meta 或 rel=author 連結。限制：只寫在內文、沒有標記的作者名稱不會被偵測到。",
    "seo-index-signals-conflict":
        "依據：Google 說明 sitemap 應只列希望出現在搜尋結果的標準網址；noindex 必須讓爬蟲抓得到"
        "才會生效。限制：只比對本次爬到的頁面與讀到的 sitemap 網址（最多頁數上限個），"
        "robots.txt 依 Googlebot 規則判斷。",
    "seo-structured-data-required":
        "依據：Google Search Central 各類型結構化資料說明頁列為必填的欄位（產品、軟體、職缺、"
        "食譜、影片、導覽路徑、活動、在地商家、評論與評分彙總）。限制：只檢查必填欄位是否存在，"
        "不檢查值是否正確；符合資格也不保證 Google 一定顯示複合式搜尋結果。",
    "seo-structured-data-self-serving-reviews":
        "依據：Google 評論摘要說明——LocalBusiness／Organization 的評論由該商家自己控制時，"
        "不顯示星等。限制：無法從標記判斷評論來源，請自行確認是否屬於自家評論。",
    "aeo-markup-mismatch":
        "依據：標記中的問題、答案、電話或 Email 在頁面可見文字中找不到。"
        "限制：以前 16～20 字比對，改寫過的同義文字可能被判為不一致。",
    "aeo-render-dependent":
        "依據：原始 HTML 的正文不到執行 JavaScript 後的 30%。"
        "限制：Google 會執行 JavaScript；這項只說明不執行 JavaScript 的工具會拿到較少內容。",
    "AEO_GENERAL_75C5FFBB7D":
        "依據：頁面出現多個問句，但沒有 dl／details 等問答結構。"
        "限制：問句以標點與字詞推測，可能把一般疑問句也算進去。",
}
CATEGORY_BASIS = {
    "seo": "依據：Argus 規則比對頁面標記。限制：這是可改善的項目，不代表網站不會被搜尋；"
           "排名仍取決於內容品質與外部因素。",
    "aeo": "依據：Argus 以固定規則從網站內容出題（聯絡方式、價格、申請期限等），在已掃描的頁面中"
           "找答案段落，檢查答案是否具體、是否互相矛盾（此版不使用 AI 判讀）。"
           "限制：只涵蓋已掃描的頁面"
           "與題庫中的問題，無法代表特定 AI 服務是否會引用你的網站。",
    "geo": "依據：Argus 規則比對頁面的結構與可讀性訊號。限制：不代表網站不會被 AI 搜尋或引用。",
    "ux": "依據：以行動版視窗實際量測（版面寬度、觸控目標、表單標籤、JavaScript 錯誤）。"
          "限制：只涵蓋可自動量測的項目，不取代實際使用者測試。",
}

AXE_BASIS = (
    "依據：axe-core（Deque Systems 的開源無障礙檢查引擎）在桌面版頁面上執行 WCAG 2.0／2.1／2.2 "
    "A 與 AA 的自動化規則。限制：自動化檢查只能涵蓋部分 WCAG 準則，沒有違規不代表網站符合 WCAG，"
    "仍需人工以鍵盤與螢幕報讀軟體實際操作確認。"
)

# 「判定依據」：高風險以上與 AI 觀察項目固定交代成立條件、實際觀察、尚缺證據與驗證方法，
# 讓讀者判斷評級是否站得住（2026-09-28 報告審查）。掃描器可在 evidence_json["assessment"]
# 提供更貼近個案的內容；沒有時用這裡的預設。
_AGENT_ASSESSMENT = {
    "condition": "攻擊者能利用這項觀察，取得原本拿不到的資訊、權限或繞過既有防護。",
    "observed": "AI Agent 送出的請求與擷取到的回應內容（見檢測依據）。",
    "missing": "AI 對影響的判讀未經工具重現或人工確認；觀察到資訊不等於能被利用。",
    "verify": "依檢測依據重送相同請求確認回應一致，再由資安人員評估該資訊能否被實際利用。",
}
DEFAULT_ASSESSMENT = {
    "agent-observed-security": _AGENT_ASSESSMENT,
    "SECURITY_PII_8B24BB8B28": {
        "condition": "頁面對外公開、未經登入即可讀取，且內容是非刻意公開的真實個人資料。",
        "observed": "頁面內容出現符合個資格式的資料（見檢測依據，報告中已遮罩）。",
        "missing": "規則無法判斷資料是否為刻意公開的聯絡資訊、測試資料，或是否屬於真實當事人。",
        "verify": (
            "由網站管理者逐筆確認資料來源與公開依據；確認為非刻意公開的真實個資時才維持此評級。"
        ),
    },
    "kali-sqlmap-sqli": {
        "condition": "參數可被注入並影響資料庫查詢。",
        "observed": "sqlmap 在授權範圍內實際送出測試請求，並確認注入成立（見檢測依據）。",
        "missing": "尚未評估可讀取或修改的資料範圍。",
        "verify": "以參數化查詢修正後，重新執行授權掃描，確認 sqlmap 不再成立。",
    },
}

AGENT_SEVERITY_CAP = "medium"


def _source_label(finding) -> str:
    """每筆發現的來源：規則、外部工具、主動探測或 AI Agent。"""
    rule = finding.rule_id or ""
    source = finding.evidence_source or ""
    if rule.startswith("agent-") or source == "hermes_agent":
        return "AI Agent 觀察（附擷取證據，未經工具或人工驗證）"
    if rule.startswith("kali-"):
        return "工具驗證（sqlmap 實際確認可利用）"
    if "Template：" in (finding.evidence or ""):
        return "外部工具（Nuclei 範本比對，未另行驗證）"
    if source.startswith("katana"):
        return "外部工具（Katana 探索）"
    if rule.startswith("axe-"):
        return "外部工具（axe-core 無障礙自動化檢查）"
    if rule.startswith("zap-"):
        return "外部工具（OWASP ZAP 被動分析：只檢查已取得的回應，未另行驗證）"
    if source == "exposure_probe":
        return "主動探測（實際請求常見敏感路徑）"
    if rule.split("-")[0] in {"ssl", "dns", "cookie", "sri", "header", "js", "service", "exposure"}:
        return "規則引擎（TLS、DNS、回應標頭等被動檢查）"
    return "規則引擎（爬蟲擷取的頁面內容）"


def _assessment_for(finding) -> dict | None:
    evidence_json = finding.evidence_json if isinstance(finding.evidence_json, dict) else {}
    if isinstance(evidence_json.get("assessment"), dict):
        return evidence_json["assessment"]
    rule = finding.rule_id or ""
    if rule in DEFAULT_ASSESSMENT:
        return DEFAULT_ASSESSMENT[rule]
    if finding.severity in (Finding.Severity.HIGH, Finding.Severity.CRITICAL):
        return {
            "condition": f"「{finding.title}」描述的狀況確實存在於正式網站，且能被外部利用。",
            "observed": "見檢測依據：規則或工具在掃描當下的實際輸出。",
            "missing": "規則或範本比對的結果未經人工重現，可能有誤判。",
            "verify": "依附錄 6.3 的方式重現；確認後再決定是否維持此評級。",
        }
    return None


def _report_severity(finding) -> str:
    """報告顯示的嚴重度：AI 觀察項目上限為中風險（與 agent 新版回報規則一致，涵蓋舊紀錄）。"""
    if (finding.rule_id or "").startswith("agent-") and _severity_rank(finding.severity) < 2:
        return AGENT_SEVERITY_CAP
    return finding.severity


def _report_evidence(finding, evidence: str) -> str:
    """報告用證據：遮罩個資；Cookie 值只留頭尾（舊紀錄可能存了完整值）。"""
    text = mask_pii_evidence(evidence or "")
    if (finding.rule_id or "").startswith("cookie-"):
        from apps.scans.security.cookie_scanner import mask_cookie_line

        first, sep, rest = text.partition("\n")
        if "已遮蔽" not in first:
            text = mask_cookie_line(first) + sep + rest
    return text


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
            # 合併後仍保留每個位置自己的證據（例如每頁實際的 title），讀者才能逐一核對
            group.setdefault("locations", []).append((page_label, finding.evidence or ""))
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
    text = "\n".join(lines).strip()
    # 舊版 agent 回報的措辭（內部代號＋「攻擊性驗證結論另見工具確認項」）改成讀者看得懂、
    # 且明講未經驗證的說法；新版回報已直接用新措辭。
    text = text.replace(
        "Hermes-Agent 在實際操作與 probe 觀察中發現：", "AI Agent 在實際操作網站時觀察到："
    )
    text = text.replace(
        "此為 AI agent 帶證據的觀察型回報；攻擊性驗證結論另見工具確認項。",
        "這是 AI 的觀察與判讀，附有擷取的回應作為證據，但未經工具或人工驗證可被利用。",
    )
    return text or "（無）"


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


_COVERAGE_STATUS_TEXT = {"partial": "部分完成", "failed": "執行失敗", "blocked": "被阻擋"}


def _scan_scope_rows(scan_job: ScanJob) -> dict:
    """掃描範圍。scope 一律取自 scan_plan，不在這裡重複「max_pages==1 代表單頁」。

    「全網站」只是探索方式，不代表每一頁都檢查過：這裡明講實際檢查了幾頁、是否碰到頁數上限、
    有多少頁被擋或回應錯誤，以及哪些檢查這次沒有執行（2026-09-28 報告審查）。
    """
    plan = build_scan_execution_plan(scan_job)
    pages = scan_job.pages.all()
    checked = pages.count()
    blocked = pages.exclude(blocked_reason="").count()
    http_errors = pages.filter(blocked_reason="", status_code__gte=400).count()
    analysed = max(checked - blocked - http_errors, 0)
    if plan.scope == "single":
        scope = "單頁（只檢查輸入的網址）"
    else:
        scope = (
            "全網站模式（從入口頁沿同網域連結探索，"
            f"最多 {scan_job.max_pages} 頁、深度 {scan_job.max_depth}）"
        )
    checked_text = f"已檢查 {checked} 頁"
    if plan.scope != "single" and checked >= scan_job.max_pages:
        checked_text += "（已達頁數上限，網站可能還有未檢查的頁面）"
    rows = {
        "掃描範圍": scope,
        "探測模式": scan_job.get_scan_mode_display(),
        "頁數上限": str(scan_job.max_pages),
        "連結深度上限": str(scan_job.max_depth),
        "實際掃描頁數": checked_text,
        "完整分析的頁數": f"{analysed} 頁",
        "被阻擋／回應錯誤": f"被阻擋 {blocked} 頁、HTTP 4xx／5xx {http_errors} 頁（這些頁不做內"
        "容分析）",
        "遵守 robots.txt": "是" if scan_job.respect_robots else "否",
    }
    skipped = []
    if not plan.run_nuclei:
        skipped.append("Nuclei 範本探測")
    if not plan.run_katana:
        skipped.append("Katana 深度探索")
    if not plan.run_exposure:
        skipped.append("敏感檔案路徑探測")
    if not (settings.ARGUS_AGENT_ENABLED and (plan.run_agent or plan.run_agent_ux)):
        skipped.append("AI Agent 互動測試")
    not_selected = [
        CATEGORY_DISPLAY.get(c, c) for c in Finding.Category.values
        if c not in scan_job.effective_categories
    ]
    if not_selected:
        skipped.append("未勾選的面向：" + "、".join(not_selected))
    rows["本次未執行的檢查"] = "、".join(skipped) if skipped else "無"
    rows["評分版本"] = versions.label(scan_job)
    # 外部效能指標：與 Argus 分數分開列，標明來源與量測方式
    rows.update(pagespeed_summary_lines(scan_job.performance_report or {}))
    incomplete = incomplete_checks(scan_job.coverage)
    if incomplete:
        # 覆蓋契約：有跑但沒完整跑完的檢查要講出來，「沒發現問題」不等於沒有問題
        rows["未完整完成的檢查"] = "；".join(
            f"{item['label']}（{_COVERAGE_STATUS_TEXT.get(item['status'], item['status'])}"
            # 只有「部分完成」附原因（人看得懂的說明）；失敗原因是例外類別，屬內部資訊
            + (f"：{item['reason']}" if item["status"] == "partial" and item["reason"] else "")
            + "）"
            for item in incomplete
        )
    partial = [
        CATEGORY_DISPLAY.get(category, category)
        for category, state in ((scan_job.coverage or {}).get("categories") or {}).items()
        if state == "partial"
    ]
    if partial:
        rows["部分評估的面向"] = (
            "、".join(partial) + "（分數只反映實際完成的檢查）"
        )
    aeo = _aeo_scope_text(scan_job)
    if aeo:
        rows["AEO 問答檢測"] = aeo
    return rows


def _aeo_scope_text(scan_job: ScanJob) -> str:
    report = scan_job.aeo_report or {}
    if not report:
        return ""
    if report.get("status") != "evaluated":
        return report.get("reason") or "未充分評估"
    counts = report.get("counts") or {}
    text = (
        f"測試 {report.get('questions_total', 0)} 題：可回答 {counts.get('answered', 0)}、"
        f"資訊不足 {counts.get('insufficient', 0)}、內容衝突 {counts.get('conflict', 0)}、"
        f"無可用答案 {counts.get('missing', 0)}；"
        f"有答案的問題比例 {round((report.get('answered_ratio') or 0) * 100)}%"
    )
    if report.get("evidence_ratio") is not None:
        text += f"，答案附有原文的比例 {round(report['evidence_ratio'] * 100)}%"
    return text + "（逐題結果見附錄）"


def _aeo_items(scan_job: ScanJob) -> list[dict]:
    """附錄的 AEO 逐題表：題目、判定、證據（原文與位置）或理由。"""
    report = scan_job.aeo_report or {}
    if report.get("status") != "evaluated":
        return []
    items = []
    for question in report.get("questions") or []:
        evidence = question.get("evidence") or []
        if question.get("verdict") == "answered" and evidence:
            first = evidence[0]
            quote = mask_pii_evidence(first["quote"])[:120]
            basis = f"{first['url']}｜{first['location']}｜「{quote}」"
        else:
            basis = question.get("reason") or ""
            if evidence:
                first = evidence[0]
                basis += f"（{first['url']}｜{first['location']}）"
        verdict = question.get("verdict_label", "")
        if question.get("confidence_label"):
            # 可信度（確認／可能／推測）附在判定後，不改 schema（RENDERER_VERSION 15）
            verdict = f"{verdict}（{question['confidence_label']}）"
        items.append({
            "question": question.get("text", ""),
            "verdict": verdict,
            "basis": basis[:400],
        })
    return items


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
    # 部分掃描（docs/business-model-plan.md：Partial Coverage 必須標示）：使用者因點數不足
    # 選了較少頁數，報告要講明這不是完整掃描，避免收件者把結果當成整站結論。
    if 1 < scan_job.max_pages < settings.ARGUS_DEFAULT_MAX_PAGES:
        lines.append(
            f"部分掃描：本次只檢查最多 {scan_job.max_pages} 頁"
            f"（標準完整掃描為 {settings.ARGUS_DEFAULT_MAX_PAGES} 頁），"
            "未檢查到的頁面可能仍有問題，結果不代表整個網站。"
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


def _absent_since(scan_job: ScanJob, previous) -> tuple[list[str], int]:
    """前次有、這次沒有的項目：(確認已修好的標題, 無法確認的數量)。

    覆蓋契約（coverage.absent_issue_status）：只有產生它的檢查本次完整跑完、受影響頁面也有
    重新分析，才算已修好；工具失敗、沒爬到該頁或舊掃描沒有覆蓋紀錄時，只能說「本次未出現」。
    """
    if previous is None:
        return [], 0
    from apps.scans.projects import compare_issues

    _issues, missing = compare_issues(scan_job, previous)
    resolved = [item["title"] for item in missing if item["status"] == "resolved"]
    return resolved, len(missing) - len(resolved)


def _headline(
    scan_job: ScanJob, previous, category_scores: dict, resolved=(), unconfirmed: int = 0
) -> str:
    """一頁摘要的導讀句。只陳述資料本身，不加沒有根據的評價。"""
    score = scan_job.overall_score
    parts = []
    if isinstance(score, int):
        parts.append(f"分數落在「{_score_band_label(score)}」區間")
    if previous is not None and isinstance(score, int) and not versions.comparable(
        scan_job, previous
    ):
        # 評分公式或規則集不同：分數差可能只是規則改了，不能說成網站進步／退步
        parts.append("評分規則與前次不同，分數不宜直接比較")
    elif previous is not None and isinstance(score, int):
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
    if unconfirmed:
        parts.append(f"另有 {unconfirmed} 項本次未出現，但檢查不完整、無法確認已修好")
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


def _sorted_report_groups(scan_job: ScanJob) -> list[dict]:
    """去重分組後排序：先資安、再內容（SEO／AEO／GEO／UX），各自依嚴重度。

    report_render 依此順序分段顯示，先排好編號才會連續。
    """
    grouped = _group_findings_for_report(scan_job.findings.select_related("page").all())
    grouped.sort(
        key=lambda item: (
            item["finding"].category != Finding.Category.SECURITY,
            _severity_rank(_report_severity(item["finding"])),
        )
    )
    return grouped


def _report_finding_entry(scan_job: ScanJob, ref: str, item: dict) -> dict:
    """單一（已合併多頁的）發現項目卡片。"""
    finding = item["finding"]
    pages = item["pages"]
    is_security = finding.category == Finding.Category.SECURITY
    observed_at = timezone.localtime(
        finding.created_at or scan_job.completed_at or timezone.now()
    ).strftime("%Y-%m-%d %H:%M")
    entry = {
        "id": ref,
        "title": finding.title,
        "severity": _render_severity(_report_severity(finding)),
        "category": CATEGORY_DISPLAY.get(finding.category, finding.category.upper()),
        "group": "security" if is_security else "content",
        "scope": _pages_label(pages),
        "problem": _description_for_report(finding),
        "fix": finding.remediation or "（無）",
        # 先遮罩再截斷：反過來做的話 PII 數值可能剛好被截斷點切一半，
        # 殘缺數字命不中 regex，反而以明文殘留。
        "evidence": _report_evidence(finding, finding.evidence)[:_MAX_EVIDENCE_CHARS],
        # 讓每筆結果都能被重新核對：規則、觀測時間與來源（規則／工具／AI）
        "trace": (
            f"規則 {finding.rule_id or '—'}　·　觀測 {observed_at}"
            f"　·　來源：{_source_label(finding)}"
        ),
    }
    if len(pages) > 1:
        locations = item.get("locations") or []
        entry["locations"] = [
            {"url": url, "evidence": _report_evidence(finding, evidence)[:160]}
            for url, evidence in locations[:_MAX_LISTED_PAGES]
        ]
        if len(pages) > _MAX_LISTED_PAGES:
            entry["locations_more"] = (
                f"等，另 {len(pages) - _MAX_LISTED_PAGES} 處"
                "（完整清單見 Argus 網頁版的掃描結果）"
            )
    assessment = _assessment_for(finding)
    if assessment:
        entry["assessment"] = dict(assessment)
        if _report_severity(finding) != finding.severity:
            entry["assessment"]["missing"] += "（AI 觀察項目在報告中以中風險為上限呈現。）"
    if not is_security:
        rule = finding.rule_id or ""
        entry["basis"] = (
            RULE_BASIS.get(rule)
            or (AXE_BASIS if rule.startswith("axe-") else "")
            or CATEGORY_BASIS.get(finding.category, "")
        )
    return entry


def _report_summary(scan_job: ScanJob, previous, grouped: list[dict]) -> dict:
    """摘要：總分、各分類分數、與前次比較。"""
    category_scores = scan_job.category_scores or {}
    scan_date = timezone.localtime(
        scan_job.completed_at or scan_job.created_at or timezone.now()
    ).strftime("%Y-%m-%d")
    resolved, unconfirmed = _absent_since(scan_job, previous)
    summary: dict = {
        "overall_score": scan_job.overall_score or 0,
        "scan_date": scan_date,
        "headline": _headline(scan_job, previous, category_scores, resolved, unconfirmed),
        "score_note": SCORE_NOTE,
        # 全部 5 個分類都列出；未評估的給 null，report_render 會標「未評估」
        # 且不計入顏色。缺鍵＝未評估是 calculate_scores() 的既有契約。
        "categories": [
            {
                "name": CATEGORY_DISPLAY.get(category, category.upper()),
                "score": category_scores.get(category),
            }
            for category in Finding.Category.values
        ],
    }
    if previous is not None:
        summary["previous"] = {
            "date": timezone.localtime(previous.completed_at).strftime("%m-%d"),
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
            summary["new_findings"] = appeared
    return summary


def _report_priorities(scan_job: ScanJob, findings_payload: list[dict]) -> list[dict]:
    """優先改善建議（top_actions），嚴重度與對應卡片一致。"""
    priorities = []
    severity_by_title = {f["title"]: f["severity"] for f in findings_payload}
    for action in scan_job.top_actions or []:
        priorities.append({
            # 與發現項目卡片同一個嚴重度（例如 AI 觀察項目的上限），不各說各話
            "severity": severity_by_title.get(
                action.get("title"), _render_severity(action.get("severity", ""))
            ),
            "problem": action.get("title", ""),
            "category": CATEGORY_DISPLAY.get(
                action.get("category", ""), str(action.get("category", "")).upper()
            ),
            "ref": next(
                (f["id"] for f in findings_payload if f["title"] == action.get("title")), ""
            ),
        })
    return priorities


def _report_why_matters(grouped: list[dict]) -> list[dict]:
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
    return why_matters


def _report_scan_info(scan_job: ScanJob) -> dict:
    """掃描範圍、警示與入口頁截圖。"""
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
    return scan_info


def _report_appendix(
    scan_job: ScanJob, grouped: list[dict], findings_payload: list[dict]
) -> dict:
    """附錄：名詞解釋、技術索引、AEO 逐題、修補驗證、檢測方法與授權聲明。"""
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
    # 修補驗證要和原本的問題一一對應：每一項都給出手動確認方式（有 per-rule 指令用指令，
    # 沒有就用分類通用說明）。並明講「重掃後沒出現」不等於修好——也可能是這次沒爬到或被擋。
    appendix["verify_note"] = (
        "完成修補後可重新執行一次 Argus 掃描，下一份報告的摘要會列出這次不再出現的項目。"
        "但「重新掃描後沒有出現」不一定代表已修好：也可能是這次沒有爬到該頁、頁面被阻擋，"
        "或掃描範圍與設定不同。請先對照新報告第 5 章，確認相同頁面確實有被檢查，"
        "再用下表的方式逐項手動確認。"
        "想更深入了解任何一項：把該項的「問題是什麼」「怎麼修」「檢測依據」三段文字複製起來，"
        "貼給 ChatGPT、Claude 等 AI 助手並補一句「請說明這個問題的影響與具體修復步驟」即可。"
    )
    aeo_items = _aeo_items(scan_job)
    if aeo_items:
        appendix["aeo_items"] = aeo_items
    appendix["verify_items"] = [
        {"ref": f["id"], "title": f["title"], "how": _verify_for(item["finding"])}
        for f, item in zip(findings_payload, grouped, strict=True)
    ]
    agent_refs = [
        f["id"] for f, item in zip(findings_payload, grouped, strict=True)
        if _source_label(item["finding"]).startswith("AI Agent")
    ]
    method = [
        "每一項發現都標示了來源（見卡片中的「來源」）：「規則引擎」是 Argus 以固定規則比對"
        "爬蟲擷取的頁面、回應標頭、TLS 與 DNS；「外部工具」是 Nuclei 等工具的範本比對結果；"
        "「主動探測」是實際對網站送出請求所得。這些項目的判斷不使用 AI。",
    ]
    if agent_refs:
        method.append(
            f"第 {'、'.join(agent_refs)} 項由 AI Agent 在實際操作網站時提出，"
            "附有擷取的回應作為證據，"
            "但其影響判讀由 AI 產生、未經工具或人工驗證，請以「判定依據」自行確認；"
            "報告中這類項目以中風險為上限。"
        )
    method.append("本報告未經人工逐項確認，文字內容未經 AI 改寫。")
    appendix["method_note"] = "".join(method)
    consent = getattr(scan_job, "authorization_consent", None)
    if consent is not None:
        # 刻意不寫 ip_address / user_agent / 授權帳號：報告會被下載轉寄給第三方，
        # 授權人的 IP 與瀏覽器指紋是個資，對收件者零價值只增加外洩面。
        appendix["authorization"] = {
            "授權網域": consent.authorized_domain,
            # 與封面、頁首一致用本地時區（先前直接印 UTC，比封面時間早 8 小時）
            "授權時間": timezone.localtime(consent.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            "主動測試授權": "是" if consent.active_testing_authorized else "否（僅被動偵測）",
            "授權聲明": consent.statement,
        }
    else:
        appendix["authorization"] = {
            "授權紀錄": "查無授權紀錄。若這份報告要作為稽核依據，請先確認授權來源。"
        }
    return appendix


def build_report_payload(scan_job: ScanJob) -> dict:
    """把一次掃描轉成 report_render 的輸入 JSON（契約見 report_render/schema.json）。

    這裡是報告的「資料層」：去重分組、評分、與前次比較、術語過濾、per-rule 文案、
    PII 遮罩全部發生在這一支，排版完全交給 report_render。分開的好處是排版可以整套
    抽換（本次就是），而這些領域規則與它們的測試一行都不用動。

    每一節由各自的函式組成（_report_summary、_report_finding_entry、_report_priorities、
    _report_why_matters、_report_scan_info、_report_appendix），鍵的順序即報告章節順序。
    """
    grouped = _sorted_report_groups(scan_job)
    previous = _previous_completed_scan(scan_job)
    findings_payload = [
        _report_finding_entry(scan_job, f"4.{index}", item)
        for index, item in enumerate(grouped, start=1)
    ]
    payload: dict = {
        "meta": {
            "site_url": scan_job.normalized_url,
            "report_id": build_report_number(scan_job),
            "generated_at": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "summary": _report_summary(scan_job, previous, grouped),
        "findings": findings_payload,
    }
    priorities = _report_priorities(scan_job, findings_payload)
    if priorities:
        payload["priorities"] = priorities
    why_matters = _report_why_matters(grouped)
    if why_matters:
        payload["why_matters"] = why_matters
    site_profile = _report_site_profile(scan_job)
    if site_profile:
        payload["site_profile"] = site_profile
    payload["scan_info"] = _report_scan_info(scan_job)
    payload["appendix"] = _report_appendix(scan_job, grouped, findings_payload)
    return payload


def _report_site_profile(scan_job: ScanJob) -> dict:
    """網站概況（site_profile.py）轉成報告用的事實表與優點清單；舊掃描沒有就回空 dict。"""
    profile = scan_job.site_profile or {}
    infra = profile.get("infrastructure") or {}
    strengths = [
        {
            "title": s["title"],
            "detail": s["detail"],
            "category": s.get("category", ""),
            "evidence": s.get("evidence", ""),
            "confidence": s.get("confidence", "confirmed"),
        }
        for s in profile.get("strengths") or []
    ]
    facts = []
    if infra.get("hostname"):
        edge = infra.get("edge")
        facts.append({"label": "網域", "value": infra["hostname"]})
        if edge:
            target = f"{edge['provider']} 邊緣節點（CDN／反向代理）"
        elif infra.get("scan_target") == "origin":
            target = "網站主機（未偵測到 CDN／反向代理）"
        else:
            target = "無法判斷"
        facts.append({"label": "實際掃描到", "value": target})
        addresses = infra.get("addresses") or []
        if addresses:
            facts.append({"label": "IP 與反解", "value": "；".join(
                a["ip"] + "（" + "・".join(
                    x for x in (f"{a['network']} 網段" if a.get("network") else "",
                                a.get("rdns") or "無反解") if x
                ) + "）"
                for a in addresses
            )})
        if infra.get("cname"):
            facts.append({"label": "CNAME", "value": "、".join(infra["cname"])})
        if infra.get("nameservers"):
            facts.append({"label": "DNS 代管", "value": "、".join(infra["nameservers"])})
        if edge and edge.get("evidence"):
            facts.append({"label": "判斷依據", "value": "；".join(edge["evidence"][:3])})
    if profile.get("ai_bots"):
        facts.append({"label": "AI 爬蟲政策", "value": ai_bots_summary(profile["ai_bots"])})
    if profile.get("observatory"):
        facts.append(
            {"label": "安全標頭等第", "value": observatory_summary(profile["observatory"])}
        )
    if not facts and not strengths:
        return {}
    return {"notice": infra.get("notice", ""), "facts": facts, "strengths": strengths}


def report_output_path(scan_job: ScanJob) -> Path:
    """報告檔案位置（PDF）。views.py 判斷快取時也用這支，避免兩邊各寫一次檔名慣例。"""
    return Path(settings.MEDIA_ROOT) / "reports" / f"scan-{scan_job.id}-report.pdf"


def render_report_docx(scan_job: ScanJob, output_path: Path | None = None) -> str:
    """只產生排版用的 .docx（不寫防偽紀錄）。

    資料層與排版層分離：本模組只負責把掃描結果整理成 report_render 的輸入
    （build_report_payload），版面、配色、圖表、浮水印全部由 report_render 決定。
    分開的好處是排版可以整套抽換，而領域規則與它們的測試一行都不用動。
    內容測試直接讀這份 .docx；對外交付的是 build_scan_report 轉出的 PDF。
    """
    if output_path is None:
        output_path = Path(settings.MEDIA_ROOT) / "reports" / f"scan-{scan_job.id}-report.docx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generate_report(build_report_payload(scan_job), str(output_path))
    return str(output_path)


def build_scan_report(scan_job: ScanJob) -> str:
    """產生 PDF 報告並寫入防偽紀錄，回傳 PDF 路徑。

    .docx 只是中間產物，寫在暫存目錄、轉完即刪；磁碟上與使用者手上只有 PDF。
    """
    output_path = report_output_path(scan_job)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    generated_at = timezone.now()
    with tempfile.TemporaryDirectory(prefix="argus-report-") as workdir:
        docx_path = Path(workdir) / f"scan-{scan_job.id}-report.docx"
        render_report_docx(scan_job, docx_path)
        convert_docx_to_pdf(docx_path, output_path)

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
            "report_number": build_report_number(scan_job),
            "content_sha256": content_sha256,
            "generated_at": generated_at,
            "renderer_version": RENDERER_VERSION,
            "previous_sha256": history,
        },
    )
    return str(output_path)
