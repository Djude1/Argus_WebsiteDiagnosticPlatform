"""把 HermesAgent 跑成 async function，給 Celery task 在掃描流程中呼叫。

入場策略：
- 從本次掃描已成功爬到（blocked_reason 空）的 Page 中挑第一個作為起點。
- 沒有可用 Page → 直接 return None，不視為失敗。
- ARGUS_AGENT_ENABLED=False（預設）時 return None，向下相容既有掃描流程。

安全：
- 所有請求先套用 public target policy，主文件與 WebSocket 再強制 same-origin；
  Service Worker 停用，避免繞過 Playwright request interception。
- 沿用專案 User-Agent（SiteSense-AI-Scanner）。
- Playwright Chromium 路徑由 settings 已注入環境變數的 PLAYWRIGHT_BROWSERS_PATH 決定。
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from asgiref.sync import sync_to_async
from config.egress import playwright_launch_kwargs
from django.conf import settings
from playwright.async_api import async_playwright

from apps.scans.models import ScanJob
from apps.scans.services import (
    PublicScanTargetError,
    assert_public_http_url,
    assert_public_websocket_url,
)

from .findings import persist_agent_issues, persist_agent_security_findings
from .loop import AgentRunResult, HermesAgent
from .providers import ProviderChain, build_default_chain
from .tools import ToolExecutor, build_tool_schemas

DEFAULT_TASK_PROMPT_TEMPLATE = """你正在測試 {origin} 這個網站，已開啟頁面 {url}。
請執行以下測試：
1. 先呼叫 get_dom_summary 取得頁面互動元素摘要。
2. 找出最重要的呼叫行動按鈕（如「立即購買」、「免費試用」、「註冊」），嘗試點擊。
3. 若進入表單或結帳流程，請嘗試填入示意資料（test@example.com），並送出觀察結果。
4. 過程中任何 UX 問題（按鈕無反應、流程斷裂、文案歧義、看不到必要回饋），請呼叫 report_ux_issue。
5. 完成或無法繼續時呼叫 finish，並附短總結。

請不要操作他站資源、不要繞過驗證、不要送出破壞性 payload。"""

# 僅在 deep_mode（active + authorized）使用：雙 session 分工滲透（pentest-ai-agents
# 的 role 化概念）。單 session 塞全部工作會互相搶步數（#17~#22 實測：recon 的
# probe 序列與 auth 的登入後測試擠在同一 context，token 上限先爆），拆成
# 偵察／認證攻擊兩個角色，各自專屬提示詞與乾淨 context，序列執行後合併結果。
# 只描述「可用什麼工具觀察到什麼」，不給特定端點答案。
RECON_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（偵察角色），
已開啟頁面 {url}。
你只負責「未登入狀態」的偵察與驗證；不要註冊或登入帳號（那是另一位 agent 的工作）。

1. 呼叫 get_network_requests 取得本頁瀏覽器實際發出的 API 請求（XHR/fetch）；
   也可用 get_dom_summary 觀察互動元素。SPA 的後端 API 端點通常只出現在
   網路流量裡，不出現在頁面連結裡。
2. 從觀察到的端點中，自行判斷哪些「本站同源、且帶 query 參數（URL 含 ?xxx=）」
   最可能存在注入風險（例如接受使用者輸入的查詢、搜尋、篩選端點），對每一個
   呼叫 probe_sql_injection(url) 進行 SQL injection 主動驗證。系統會自動判定，
   確認可注入時記錄為 critical 漏洞（確認後你無需再 report）。
3. 對看起來「應該需要登入才能存取」的端點（個人資料、訂單、購物車、後台管理、
   內部 API 等），呼叫 probe_unauthorized_access(url) 以匿名請求重放：若匿名
   仍取得實質資料（非 401/403、非空回應），這就是未授權存取漏洞——用
   report_security_issue 回報，evidence 附上你觀察到的回應內容。
4. 過程中觀察到的其他資安線索（敏感資料顯示在頁面、錯誤訊息洩漏內部路徑、
   回應中的敏感欄位等）也用 report_security_issue 回報並附證據；不要臆測。
5. 完成、或已系統性覆蓋以上三類後，呼叫 finish 附短總結。

限制：只對本站同源 URL 使用 probe 工具；跨站 URL、無 query 參數的 SQLi
目標會被系統拒絕。"""

AUTH_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（認證攻擊角色），
已開啟頁面 {url}。
你負責「登入後」的存取控制與 business logic 驗證。

1. 若網站有註冊／登入功能：**優先直接打 API 而不是操作 UI 表單**——從
   network log 找到註冊與登入端點，用 replay_request 先 POST 註冊一個測試
   帳號（test 類信箱與隨機密碼），再 POST 登入並以 store_token_key 把回應
   token 存進瀏覽器。登入後再次 get_network_requests，觀察新出現的授權
   端點（購物車、訂單、個人資料等常帶數字 id）。
2. 跨帳號存取（IDOR，系統性遍歷）：把 network log 中**每一個**帶數字 id 的
   資源端點（購物車、訂單、錢包、留言、評論、回收、個人資料……）的 id 改成
   1、2 與你自己 id 以外的值重放——200 且回傳**不屬於此帳號**的資料即為
   讀取型 IDOR，逐一記錄。讀取型之外，更新類端點
   （PUT/PATCH，如修改購物車項目、個人資料）也以同法改 id 測試——若能成功
   修改**他人**的資源，這是更嚴重的寫入型 IDOR。兩種發現都立即
   report_security_issue，附上請求與回應證據。
3. Business logic：觀察到的數量／金額類欄位，送負值或極端值——若被接受
   （200 且資料寫入），這是 business logic 漏洞；寫入後重新 GET 該資源
   確認資料真的變了，連同驗證結果一起 report_security_issue。
4. 登入繞過：登入端點本身以 replay_request 送標準的 SQL injection 登入繞過
   探測值（如信箱欄填 ' OR 1=1-- 之類的無害查詢型 payload）——若回應異常
   成功（回傳 token／登入成功），即為登入繞過漏洞，report 時附請求與回應。
5. **密碼重置鏈（帳號接管，OWASP WSTG-ATHN-09 方法論）**：若目標有
   忘記密碼／安全問題流程，走完整鏈驗證：
   a. 從 network log 找 reset／forgot 類端點與安全問題清單端點
      （GET 通常匿名可讀）。
   b. **答案來源推理**：安全問題答案常可從網站既有公開面推得——
      先蒐集目標帳號的可得資訊（公開個人頁、留言／評論文字、
      產品描述、備份檔、回應中的 metadata），交叉比對後再答。
   c. 送出答案→拿重置 token／連結→重設新密碼→以新密碼登入驗證
      ——四步全通即為帳號接管，立即 report（最高證據等級）。
   d. 重置 token 重放：同一 token 用第二次若仍成功＝一次性失效缺陷。
   優先對「你自己註冊的測試帳號」走通全鏈證明流程缺陷；對他人
   帳號只在答案已從公開資訊推得時驗證，不猜測爆破。
6. 完成、或已系統性覆蓋以上後呼叫 finish 附短總結。

注意：寫入型測試先用**你自己的**資源 id——登入回應或 whoami 類端點通常會
回傳你帳號的 id 與購物車／資源 id（例如 bid 欄位），用那個值，不要猜；
對「他人」的寫入測試只在更新端點（PUT/PATCH）上做，不要對他人資源做
建立或刪除。
限制：**全程只用 API 工具（replay_request／get_network_requests），不要使用
click／type_text 操作頁面 UI**——表單操作極耗步數且你已有更快的 API 路徑。
只對本站同源 URL 操作；不要操作他站資源。"""

INJECT_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（注入攻擊角色），
已開啟頁面 {url}。
你專責「輸入點注入」類驗證；不負責 IDOR／未授權存取（其他角色已涵蓋）。

1. **登入繞過（SQL injection in authentication）**：從 network log 找登入
   端點，用 replay_request 送標準的無害登入繞過 payload——常見型如
   信箱欄填 ' OR 1=1-- 、admin'-- ，密碼欄填任意值。若回應 200 且含
   token／authentication（對照：用亂填的假帳密登入會得到 401），即為
   登入繞過漏洞——report_security_issue 附上完整請求 body 與回應。
   多試幾種變形（' OR '1'='1 、" )) OR ((" 1 "=" 1 等）再下結論。
2. **XSS 反射探測（瀏覽器執行驗證優先）**：多數輸入點是 query 參數
   （從 network log 找）——把無害探測字串（<img src=x onerror=print(1)>
   級）組進 URL，用 navigate_and_observe 導航到**前端頁面 URL**（SPA 的
   輸入由 /#/ hash 路由頁渲染；API 端點回 JSON 不渲染，導航 API URL 驗
   不了 XSS）。dialogs 出現 alert／confirm＝已執行；渲染 DOM 出現未跳脫
   標籤＝注入成立。端點只能 UI 觸發時才 type_text 送出後檢查。
3. **非 SQL 注入家族（NoSQL／模板 SSTi／XXE／指令注入／路徑穿越 LFI）**：
   對每個可疑輸入點用 probe_payload_injection 一次跑整組家族 payload——
   GET 端點給 query_param，POST 端點給 body＋inject_field。回傳的
   markers_hit 非空（如 49＝模板求值成功、ARGUSCMDPROBE＝指令執行、
   root:＝讀到系統檔）即為疑似命中，以 report_security_issue 附
   payload kind 與命中標記回報。
4. **其他輸入點異常**：CAPTCHA／OTP／驗證碼類端點——重放同一請求兩次，
   若舊碼可重用或回應可直接給出答案，即為設計缺陷；觀察回應中的錯誤
   訊息是否洩漏內部資訊（堆疊、SQL 片段、內部路徑），有就 report。
5. 完成或已系統性覆蓋後 finish 附短總結。

限制：payload 限無害顯示型（alert()/print()/console.log 級，alert 為業界
XSS 驗證標準訊號，優先用），不要嘗試刪除、修改資料的 payload；
只對本站同源操作。"""

LOGIC_ABUSE_AGENT_PROMPT = """【鐵律：每次驗證成功的下一個動作就是 report_security_issue，
不是繼續下一個測試——未回報的發現等於不存在。】
你正在對 {origin} 進行【已授權的主動資安測試】（商業邏輯濫用角色），
已開啟頁面 {url}。
你專責 business logic 類漏洞；不負責 IDOR／SQLi（其他角色已涵蓋）。

1. 先取得登入態：從 network log 找註冊／登入端點，replay_request 打 API
   註冊測試帳號並登入（store_token_key 存 token）；登入回應／whoami 類
   端點會給你自己的資源 id（例如 bid），後續寫入測試用它。
2. **數值邊界**：對數量／金額／折扣／庫存類欄位（加購物車、結帳、優惠券），
   以 replay_request 送負值、零、極大值、小數——被接受（200 且寫入）即為
   business logic 漏洞；**寫入後重新 GET 該資源確認資料真的變了**，
   連同驗證結果 report_security_issue。
3. **流程順序**：觀察到的多步驟流程（結帳、付款、密碼重設）——嘗試跳步
   重放（例如直接打結帳端點而未經過前置步驟），被接受即為流程繞過。
4. **重用性**：CAPTCHA／OTP／一次性 token 類端點——同一值重放兩次，
   第二次仍成功即為重用缺陷。
5. **跳轉濫用**：redirect／continue 類端點的參數若可指定任意外部網址
   （open redirect），回報之（攻擊者可架釣魚前置）。
5. 完成或已系統性覆蓋後 finish 附短總結。

限制：只在**你自己的**資源上做寫入；payload 不具破壞性；只對本站同源操作。"""

# deep_mode 的 specialist 角色庫——orchestrator 依偵察情報動態挑選派工
# （pentest-ai-agents 的 swarm-orchestrator＋NousResearch/hermes-agent 的
# 能力目錄化概念：每個角色帶 desc＋when，指揮官從目錄「知道手中有什麼、
# 何時用」；dispatch_specialist 的 role enum 也由本目錄動態生成）
INFO_LEAK_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（資訊洩漏獵手角色），
已開啟頁面 {url}。
你專責「資訊洩漏」面的深入挖掘。

1. 從 network log 找出所有回應過的端點，逐一以 replay_request 重放並檢查
   回應內容：找**不該對外公開的資訊**——內部路徑、堆疊、SQL 片段、
   帳號清單、設定值、金鑰格式字串、備份內容。
2. 對偵察提示或自行觀察到的可疑路徑（檔案、目錄、隱藏端點）以
   replay_request GET 探測；回 200 且內容非 SPA fallback 即記錄。
3. 錯誤路徑測試：對 API 端點送不完整／型別錯誤的請求，檢查錯誤回應
   是否洩漏框架版本、內部 IP、檔案路徑。
4. 也可用 get_page_html 檢查頁面原始碼（注釋／hidden 欄位／inline 敏感值）、
   get_response_headers 檢查安全標頭與伺服器指紋。
5. 每項發現 report_security_issue，evidence 附回應片段（遮罩後）。
6. 完成或系統性覆蓋後 finish 附短總結。

限制：只讀取型操作（GET／只讀重放）；只對本站同源操作。"""

JWT_ABUSE_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（Token 檢視角色），
已開啟頁面 {url}。
你專責驗證 token／session 的處理弱點。

1. 登入取得 token（API 註冊測試帳號＋登入，store_token_key 存入）；
   登入回應的 token 若為 JWT（eyJ 開頭），用 decode_jwt 解讀 payload：
   是否含密碼雜湊、敏感個人欄位、內部識別碼——有即 report_security_issue
   附欄位清單；get_storage 可檢查 token 存放與 cookie 屬性。
2. 簽章／過期驗證：用 replay_request 帶**竄改後**的 token（改 payload
   一個字元、或以無效簽章）打需要授權的端點——若仍 200，代表簽章
   未驗證（嚴重）。
3. 權杖傳輸面：檢查 Set-Cookie 屬性（HttpOnly／Secure／SameSite）與
   token 存放位置（localStorage 的 XSS 被竊風險——若網站同時有 XSS
   面則在報告中註明加乘風險）。
4. 每項發現 report_security_issue 附證據；完成後 finish 附短總結。

限制：竄改只針對**自己帳號**的 token；無害驗證型操作；只對本站同源操作。"""

XSS_HUNTER_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】（XSS 獵手角色），
已開啟頁面 {url}。
你專責 XSS 類漏洞。核心原則：**XSS 的證據是「瀏覽器真的執行了」**，
不是 HTTP 回應文字——SPA 的 HTTP 回應幾乎都是空殼 HTML，永遠以瀏覽器
執行結果為準。

1. 收集輸入點：get_network_requests 找帶 ?query 參數的 same-origin URL
   （搜尋、篩選、排序類），get_dom_summary 找頁面輸入框。
2. 反射／DOM 型：把無害探測字串放進輸入點組成完整 URL（如
   <img src=x onerror=alert(1)>、<iframe src=javascript:alert(1)>
   的 URL 編碼——業界 XSS 驗證標準 payload），用 navigate_and_observe 導航過去：
   - dialogs 出現 alert／confirm／prompt ＝ payload 已執行（金證據）
   - rendered_html／visible_text 出現未跳脫的探測字串形成新標籤結構
     ＝ DOM 注入成立
   - **SPA 常識**：輸入多由前端路由頁渲染（URL 帶 #/ 的 hash 路由，
     如 /#/search?q=…）。API 端點（/api/…、/rest/…）回 JSON、不渲染
     payload——導航必須打**前端頁面 URL**（hash 路由形式）才會執行。
     不確定站台的 hash 路由長相時，先在站內操作一次該功能（type_text
     ＋click 送出），從 page.url 觀察 URL 形式再組 payload URL。
3. 純輸入框型（無對應 URL 參數）：type_text 填入探測字串、觸發送出
   （click 送出鈕或輸入框 Enter），再以 get_page_html／get_visible_text
   檢查渲染後結果。
4. 儲存型：replay_request 把探測字串寫入會被頁面渲染的公開欄位（留言、
   評論、暱稱類），再用 navigate_and_observe 造訪渲染該欄位的頁面檢查。
5. 每命中一項立即 report_security_issue（證據＝payload URL＋dialog 內容
   或渲染 DOM 中未跳脫位置的片段）。
6. 覆蓋完所有輸入點後 finish 附總結（含未完成項與原因）。

限制：payload 限「顯示型證據」——alert()／print()／console.log 級，
不執行資料外傳或破壞動作。alert() 是業界 XSS 驗證標準訊號
（Burp／OWASP 慣例，多數偵測系統也以 alert 觸發為基準），
與 print() 同級無害，優先用它。只對本站同源操作。"""

CRYPTO_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】
（密碼學／Token 偽造角色），已開啟頁面 {url}。
你專責密碼學實作缺陷（PortSwigger JWT 教材／jwt_tool 方法論）。

1. 取得站方的 token：先註冊／登入一個測試帳號（replay_request＋
   store_token_key），從 localStorage（get_storage）拿 JWT。
2. decode_jwt 解讀：記錄 alg、簽章長度、payload 欄位（role／權限／
   exp／敏感個資——後者本身就是洩漏，直接 report）。
3. **簽章接受度測試**（每支 token 用 replay_request 帶
   Authorization: Bearer 打一個受保護端點，對照原 token 回應）：
   a. forge_jwt 產 alg=none token——被接受＝伺服器未驗簽（經典缺陷）。
   b. forge_jwt HS256 弱密鑰清單逐一帶——被接受＝弱密鑰。
   c. 竄改 payload（改 role 為管理階層、改 email）但**沿用原簽章**——
      被接受＝只解不驗。
   d. exp 改成過去時間——被接受＝過期不檢查。
   任一被接受且能觸達更高權限資源＝**身分偽造／提權**，立即 report
   （附偽造 token 的 header/payload 摘要＋回應證據）。
4. 其他可預測性：回應中的「隨機」值（優惠碼／折扣碼／驗證碼）——
   觀察多個樣本的格式規律（長度、字元集、遞增），規律可推＝預測性
   缺陷，report 附樣本比較。
5. 覆蓋完 token 與可觀察密碼學面後 finish 附總結（含未完成項與原因）。

限制：偽造僅用於測試帳號與你觀察到的目標結構；只對本站同源操作。"""


FILE_UPLOAD_AGENT_PROMPT = """你正在對 {origin} 進行【已授權的主動資安測試】
（檔案上傳攻擊角色），已開啟頁面 {url}。
你專責檔案上傳面（OWASP WSTG-BUSL-08／Unrestricted File Upload 方法論）。

1. 找上傳功能：network log 找 multipart/form-data 請求（content-type
   含 boundary），或頁面上傳欄（get_dom_summary 的 input[type=file]）。
   沒有上傳面＝記錄後 finish，不要硬找。
2. 用 replay_request 的 files 參數重放上傳（body 帶表單欄位，探測內容
   用無害顯示型文字如 alert(1) 註解），逐項測：
   a. **副檔名驗證**：先傳允許類型（如 .jpg＋宣告 image/jpeg）走通流程，
      再傳同名繞過變體——大小寫（.JPG）、雙副檔名（.jpg.txt）、
      尾碼變體、空位元組截斷（.txt%00.jpg 類）——比對回應差異。
   b. **content-type 淺改**：宣告 image/jpeg 但內容是純文字探測字串。
   c. **filename 路徑穿越**：filename 帶 ../ 前綴，觀察回應儲存路徑。
   d. **大小邊界**：內容遠超合理上限（>100KB 文字），看是否截斷或全收。
3. **上傳後驗證（關鍵）**：回應常含儲存路徑／檔案 URL——GET 該路徑
   （probe_unauthorized_access 或 navigate_and_observe）確認：
   檔案可匿名直讀？內容原樣回放（未被重編碼）？路徑可否目錄列舉？
   可執行內容被當靜態檔原樣 serve＝高風險。
4. 每確認一項立即 report_security_issue（證據＝上傳請求摘要＋回應路徑
   ＋事後讀回的內容片段）。
5. 覆蓋完所有上傳點後 finish 附總結（含未完成項與原因）。

限制：檔案內容一律無害顯示型文字；只對本站同源操作。"""


# specialist 步數盒：強制在有限步數內收斂（#30~#32：無限深挖是
# findings 流失主因，token 上限加多大都會爆）
_SPECIALIST_MAX_STEPS = 60

SPECIALIST_ROLES: dict[str, dict[str, str]] = {
    "auth_idor": {
        "prompt": AUTH_AGENT_PROMPT,
        "desc": (
            "認證與越權：API 註冊登入、跨帳號讀取／寫入（IDOR，含 PUT/PATCH"
            " 更新端點）、密碼重置鏈帳號接管（WSTG-ATHN-09）"
        ),
        "when": (
            "偵察發現登入／註冊端點、密碼重置／安全問題流程，或流量有帶"
            "數字 id 的授權資源（購物車、訂單、個人資料）"
        ),
    },
    "injection": {
        "prompt": INJECT_AGENT_PROMPT,
        "desc": "輸入點注入：登入繞過 SQLi、XSS 瀏覽器驗證、家族化注入（NoSQL/SSTi/XXE/指令/LFI）",
        "when": (
            "有登入表單、搜尋／輸入框，或流量含 JSON body／XML／模板類參數。"
            "注意：NoSQL／SSTi／XXE／指令／路徑穿越這些家族只有此角色的專用"
            "工具能測——recon 的 SQLi 探測不代表已覆蓋它們"
        ),
    },
    "logic_abuse": {
        "prompt": LOGIC_ABUSE_AGENT_PROMPT,
        "desc": "商業邏輯：負數／極端值寫入、流程順序繞過、CAPTCHA/OTP 重用",
        "when": "流量有數量／金額／折扣類欄位、多步驟流程（結帳、密碼重設）、驗證碼端點",
    },
    "info_leak": {
        "prompt": INFO_LEAK_AGENT_PROMPT,
        "desc": "資訊洩漏獵手：敏感檔／備份殘留、錯誤頁內部細節、中繼資料與 debug 端點",
        "when": "偵察觀察到可疑路徑（檔案／目錄）、錯誤回應非標準、或回應內容含內部結構線索",
    },
    "xss_hunter": {
        "prompt": XSS_HUNTER_AGENT_PROMPT,
        "desc": "XSS 獵手：反射／DOM／儲存型 XSS（query 輸入點、iframe、innerHTML 渲染）",
        "when": "頁面有搜尋／篩選／排序等 query 輸入點，或流量有回應 HTML 的參數化端點",
    },
    "jwt_token_abuse": {
        "prompt": JWT_ABUSE_AGENT_PROMPT,
        "desc": "Token 檢視：JWT payload 敏感欄位、簽章／過期是否被驗、session/cookie 屬性",
        "when": "登入流程使用 token（Bearer／localStorage）或 Set-Cookie 出現",
    },
    "file_upload": {
        "prompt": FILE_UPLOAD_AGENT_PROMPT,
        "desc": (
            "檔案上傳面（WSTG-BUSL-08）：副檔名／content-type／路徑穿越／"
            "大小邊界，上傳後匿名直讀驗證"
        ),
        "when": (
            "流量出現 multipart/form-data 請求，或頁面有檔案上傳欄"
            "（頭像、附件、匯入類功能）"
        ),
    },
    "crypto": {
        "prompt": CRYPTO_AGENT_PROMPT,
        "desc": (
            "密碼學／Token 偽造：JWT 簽章接受度（alg=none／弱密鑰／只解"
            "不驗／過期不查）、token 敏感欄位、可預測隨機值"
        ),
        "when": (
            "登入流程使用 JWT（eyJ 開頭 token），或回應含優惠碼／折扣碼／"
            "驗證碼等「隨機」值——簽章偽造驗證只有此角色的 forge_jwt 工具能做"
        ),
    },
}

ORCHESTRATOR_PROMPT = """你是滲透測試指揮官。先遣偵察 agent 已完成對目標 {origin} 的初步測試，
以下是它的情報。你的工作：用 dispatch_specialist 派專家進行深入測試——
你可以根據每位專家回報的結果決定是否追加其他專家，全部滿意後 finish。

【偵察總結】
{recon_summary}

【偵察已回報的發現】
{findings_list}

【掃描期間被動觀察到的同源 API 端點（部分）】
{endpoints}

【可用專家角色】
{roles_desc}

規則：
- 依情報派真正需要的角色；brief 指向你觀察到的具體線索（可疑端點、
  未覆蓋的面相），一到三句，讓專家不用從零探索；不指定攻擊細節。
- 每位專家的結果摘要會回報給你；發現不足或面相未覆蓋時可追加派工。
- 你自己不直接測試網站（沒有瀏覽器工具）。
- **未呼叫 dispatch_specialist 至少一次就 finish 視為任務失敗**；依情報選擇
  適合的角色（可全派、token 預算充裕），逐位派出、看結果、覆蓋不足
  的面相可追加第二輪。
- 完成調度後 finish 附總結。"""


def _origin_key(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, (parsed.hostname or "").lower(), parsed.port or default_port


async def _enforce_agent_request(route, request, origin: str):
    try:
        normalized = assert_public_http_url(request.url)
        if request.resource_type == "document" and _origin_key(normalized) != _origin_key(origin):
            raise PublicScanTargetError("Agent 主文件禁止跨 origin 導覽")
    except PublicScanTargetError:
        await route.abort("blockedbyclient")
        return
    await route.continue_()


async def _enforce_agent_websocket(websocket_route, origin: str):
    try:
        normalized = assert_public_websocket_url(websocket_route.url)
        if _origin_key(normalized) != _origin_key(origin):
            raise PublicScanTargetError("Agent WebSocket 禁止跨 origin")
    except PublicScanTargetError:
        await websocket_route.close(code=1008, reason="Blocked by scan target policy")
        return
    websocket_route.connect_to_server()


async def _make_agent_context(browser, origin: str):
    context = await browser.new_context(
        user_agent=settings.ARGUS_SCANNER_USER_AGENT,
        ignore_https_errors=True,
        service_workers="block",
    )
    await context.route(
        "**/*",
        lambda route, request: _enforce_agent_request(route, request, origin),
    )
    await context.route_web_socket(
        "**/*",
        lambda websocket_route: _enforce_agent_websocket(websocket_route, origin),
    )
    return context


async def run_agent_for_scan(
    scan_job: ScanJob,
    chain: ProviderChain | None = None,
    task_prompt: str | None = None,
    recon_intel: list[str] | None = None,
) -> AgentRunResult | None:
    """對已完成爬取的 ScanJob 啟動 Hermes-Agent 動態 UX 測試。

    回傳 AgentRunResult，或 None 表示未啟動（功能關閉或無可用 Page）。
    """
    if not settings.ARGUS_AGENT_ENABLED:
        return None

    page_obj = await sync_to_async(_pick_starting_page)(scan_job)
    if page_obj is None:
        return None

    target_url = page_obj.final_url or page_obj.url
    chain = chain or build_default_chain()

    media_dir = Path(settings.MEDIA_ROOT) / "agent" / f"scan_{scan_job.id}"
    media_dir.mkdir(parents=True, exist_ok=True)

    # 僅在授權的主動掃描（deep_mode）才把 SQLi 主動驗證能力交給 agent 並列為第一優先；
    # 授權鎖最終仍由 kali_tools.run_sqlmap 的三重鎖把關，此處只影響提示。
    deep_mode = (
        scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
        and scan_job.active_testing_authorized
    )

    async def _run_session(
        role_prompt: str,
        *,
        orchestrator: bool = False,
        specialist_dispatcher=None,
    ) -> AgentRunResult:
        """單一 session：獨立 browser context（乾淨 localStorage／cookie）
        與獨立 LLM messages。orchestrator=True 時只掛調度工具（不親自測試）。"""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                **playwright_launch_kwargs(),
            )
            try:
                context = await _make_agent_context(browser, scan_job.origin)
                page = await context.new_page()
                await page.goto(
                    target_url, wait_until="domcontentloaded", timeout=30000
                )
                executor = ToolExecutor(
                    page=page,
                    screenshot_dir=str(media_dir),
                    scan_job=scan_job,
                    specialist_dispatcher=specialist_dispatcher,
                )
                agent = HermesAgent(
                    scan_job=scan_job,
                    executor=executor,
                    chain=chain,
                    tool_schemas=build_tool_schemas(
                        deep_mode,
                        orchestrator=orchestrator,
                        specialist_roles=(
                            SPECIALIST_ROLES if orchestrator else None
                        ),
                    ),
                    # specialist 步數時間盒（#32 實測 token 上限非解，
                    # 步數收斂才是）；orchestrator 首步強制派工
                    max_steps=(
                        _SPECIALIST_MAX_STEPS if not orchestrator else None
                    ),
                    forced_first_tool=(
                        "dispatch_specialist" if orchestrator else None
                    ),
                )
                return await agent.run(task_prompt=role_prompt)
            finally:
                await browser.close()

    def _merge(results: list[AgentRunResult]) -> AgentRunResult:
        """合併多 role 的結果：issues/findings 串聯（persist 層依 description
        去重）；status 只要有一個 completed 就算 completed；error 串聯標注角色。"""
        if len(results) == 1:
            return results[0]
        return AgentRunResult(
            session_id=results[0].session_id,
            status=(
                "completed"
                if any(r.status == "completed" for r in results)
                else results[0].status
            ),
            steps=sum(r.steps for r in results),
            total_tokens=sum(r.total_tokens for r in results),
            issues=[i for r in results for i in r.issues],
            security_findings=[f for r in results for f in r.security_findings],
            final_summary=" || ".join(
                f"[{idx}] {r.final_summary[:200]}" for idx, r in enumerate(results)
            ),
            error="; ".join(
                f"role{idx}:{r.error}" for idx, r in enumerate(results) if r.error
            ),
        )

    if task_prompt is not None:
        prompts: list[str] = [task_prompt]
        results = [await _run_session(p) for p in prompts]
        result = _merge(results)
    elif deep_mode:
        # 真·subagent 指揮官模式：recon 固定先跑 → orchestrator 是一個
        # 「只帶 dispatch_specialist 工具」的 agent session——它在對話中
        # 自行派 specialist、看結果摘要、可再追加，直到滿意才 finish。
        # specialist 結果即時回指揮官 context（多輪調度，非一次性派工）。
        recon_prompt = RECON_AGENT_PROMPT.format(
            origin=scan_job.origin, url=target_url
        )
        recon_result = await _run_session(recon_prompt)
        specialist_results: list[AgentRunResult] = []

        async def _dispatcher(role: str, brief: str) -> dict:
            role_def = SPECIALIST_ROLES.get(role)
            if role_def is None:
                return {"error": f"unknown_role:{role}"}
            prompt = role_def["prompt"].format(
                origin=scan_job.origin, url=target_url
            )
            brief = (brief or "").strip()
            if brief:
                prompt += f"\n\n【指揮官任務提示】{brief}"
            # authenticated scan：使用者提供的測試帳密（Signer 解密，僅注入
            # prompt 用於登入；不落地、不進 log/findings）——無公開註冊的
            # 真實網站，auth 角色改用此帳密登入而非自註冊
            from apps.scans.models import decrypt_test_auth
            _email = decrypt_test_auth(scan_job.test_auth_email_encrypted)
            _pwd = decrypt_test_auth(scan_job.test_auth_password_encrypted)
            if _email and _pwd and role in ("auth_idor", "logic_abuse"):
                prompt += (
                    "\n\n【平台提供的測試帳號】"
                    f"email: {_email} / password: {_pwd}\n"
                    "優先用這組帳號登入（replay_request POST 登入端點＋"
                    "store_token_key），不必自註冊。"
                )
            # report 紀律（所有 specialist 通用）：觀察到就要立即落地，
            # 避免做到一半 token 用盡、發現跟著消失（#28 損耗點）
            prompt += (
                "\n\n【重要紀律】每確認一項問題就**立即** report，不要累積到"
                "測試結束才一次回報——你的 token 預算可能在途中用盡，未回報的"
                "發現會全部遺失。"
            )
            # 攻擊假設紀律（Excalibur arXiv:2602.17622 TDA 概念；#33/#34
            # 實證：SecurityQuestion 觸碰 77 次未組出「洩漏→推答案→重置」鏈、
            # XSS 63 步重試同方法 0 發現——瓶頸在假設生成與換道，非工具量）
            prompt += (
                "\n\n【攻擊假設紀律】每條行動前先寫下：(1) 假設（一句話）"
                "(2) 驗證步驟 (3) 放棄條件。同一假設用同一手法連續 3 次無新"
                "資訊＝換假設（換端點／參數／手法），不要用同一方法重試。"
                "發新請求前先交叉比對你已收集的觀察（回應內容、欄位值、洩漏"
                "文字、公開資料）——組合既有線索常比新探測更快形成攻擊鏈。"
            )
            specialist_result = await _run_session(prompt)
            specialist_results.append(specialist_result)
            titles = [
                f.get("title", "")[:80]
                for f in specialist_result.security_findings
            ]
            return {
                "role": role,
                "status": specialist_result.status,
                "steps": specialist_result.steps,
                "findings": titles,
                "summary": (specialist_result.final_summary or "")[:600],
                "error": specialist_result.error,
            }

        findings_titles = [
            f.title
            for f in await sync_to_async(list)(
                scan_job.findings.filter(
                    rule_id__in=("agent-observed-security", "kali-sqlmap-sqli")
                )[:20]
            )
        ]
        orchestrator_prompt = ORCHESTRATOR_PROMPT.format(
            origin=scan_job.origin,
            recon_summary=(recon_result.final_summary or "（無）")[:1500],
            findings_list=("\n".join(f"- {t}" for t in findings_titles) or "（無）"),
            endpoints=(
                "\n".join(f"- {u}" for u in (recon_intel or [])[:15]) or "（無）"
            ),
            roles_desc="\n".join(
                f"- {name}: {defn['desc']}\n  派用時機：{defn['when']}"
                for name, defn in SPECIALIST_ROLES.items()
            ),
        )
        orchestrator_result = await _run_session(
            orchestrator_prompt,
            orchestrator=True,
            specialist_dispatcher=_dispatcher,
        )

        if not specialist_results:
            # orchestrator 失效的安全網：全派（與舊編排行為一致）
            for role_def in SPECIALIST_ROLES.values():
                specialist_results.append(
                    await _run_session(
                        role_def["prompt"].format(
                            origin=scan_job.origin, url=target_url
                        )
                    )
                )

        result = _merge([recon_result, orchestrator_result, *specialist_results])
    else:
        prompt = DEFAULT_TASK_PROMPT_TEMPLATE.format(
            origin=scan_job.origin, url=target_url
        )
        result = await _run_session(prompt)

    if result and result.issues:
        await sync_to_async(persist_agent_issues)(scan_job, result.issues)
    if result and result.security_findings:
        await sync_to_async(persist_agent_security_findings)(
            scan_job, result.security_findings
        )
    return result



def _pick_starting_page(scan_job: ScanJob):
    return (
        scan_job.pages.filter(blocked_reason="")
        .exclude(final_url="")
        .order_by("depth", "id")
        .first()
    )
