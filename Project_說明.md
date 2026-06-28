# 🎯 角色定位
你是一位資深全端架構師,精通 React + Django + Playwright + LLM Agent (Tool Calling) 與 Web 資安。
請以「資深技術主管帶領新人」的方式回應:先給整體架構與決策理由,再進入細節程式碼。
所有回應使用繁體中文,程式碼註解亦使用繁體中文。
回應開始前,請先用 100 字以內摘要你對本專案的理解,確認方向無誤後再進入正式輸出。

---

# 📌 專案名稱(暫定)
**Argus** — 次世代 AI 動態行為分析與全站健檢平台

---

# 🧭 專案核心理念
SaaS 級網站健檢工具。使用者輸入單一網址 → 系統執行:
(a) 全站爬蟲與拓撲映射
(b) 四維靜態掃描(SEO / AEO / GEO / 資安)
(c) Hermes-Agent 驅動的擬真使用者動態 UX 測試

最終產出:
- 可互動視覺化工作區(中央截圖 + 高光標示)
- 管理層 Word 報告
- 供開發者使用的「結構化問題描述 Prompt」(讓使用者自行帶去 ChatGPT/Claude 取得修復方向,本系統**不負責產生修復程式碼**)

---

# ⚙️ 技術棧(Fixed Stack,不需建議替代方案)

| 層級 | 技術 |
|---|---|
| 前端 | React 18 (Vite)、Tailwind CSS、Zustand(狀態)、HTML5 Canvas(高光繪製)、Axios |
| 後端 | Django 5.x + Django REST Framework、SimpleJWT(認證) |
| 任務佇列 | Celery + Redis |
| 爬蟲/瀏覽器 | Playwright(Python, async, Chromium headless) |
| 資料庫 | PostgreSQL(production)、SQLite(dev) |
| AI Agent | Hermes-style Agent 架構；Provider 以 MiniMax-M2.7 優先、GLM `glm-4.7-flash` / `glm-4.5-flash` 第二順位、Gemini 分析備援 |
| 文件生成 | python-docx |
| 部署 | Docker Compose(web / worker / redis / db / nginx) |

---

# 🛡️ 法律與倫理硬性限制(CRITICAL,不可違反)
程式碼必須內建以下機制:

1. **授權確認機制**:使用者送出網址前,必須勾選「我擁有此網站或已獲得書面授權測試」之同意書,後端記錄 IP、timestamp、user_id。
2. **爬蟲範圍**:預設**僅同網域(same-origin)**、最大深度 3 層、最大頁數 50(可在後台調整)、遵守 `robots.txt`(預設開啟,可由 admin 關閉)。
3. **資安測試模式**:預設為「被動偵測(Passive)」— 只分析 response header、HTML、cookie flags、CSP、表單缺少 CSRF token 等**不發送惡意 payload**的檢測。
4. **主動測試(Active)** 如 SQLi 偵測、admin path enumeration **必須**:
   - 使用者額外勾選「我同意進行侵入式測試」
   - 限制 RPS(每秒請求數)≤ 2
   - 僅使用無破壞性 payload(如 `' OR '1'='1` 觀察 response 差異,不執行 `DROP TABLE`)
   - 所有請求加上自訂 User-Agent: `SiteSense-AI-Scanner/1.0 (authorized-audit)`
5. **AI 拒絕**:若使用者輸入明顯第三方網站(google.com、銀行網域等),UI 顯示警告並要求重新確認。

---

# 🗂️ 功能規格(依優先級分為 MVP 與 Phase 2)

## ✅ MVP(請先完成這部分)

### M1. 同網域全站爬蟲
- 輸入 URL → Celery 任務啟動 Playwright
- 廣度優先(BFS),每頁記錄:最終 URL、HTTP status、title、HTML 原始碼、render 後 DOM、長截圖(full-page PNG)、載入時間
- 拓撲關聯:記錄 page-to-page 的連結關係(供後續視覺化網站地圖)

### M2. 四維靜態掃描
針對每個爬到的頁面執行:

| 維度 | 檢測項目範例 |
|---|---|
| **SEO** | Meta title/description 長度、H1 唯一性、H1-H6 階層、alt 屬性、canonical、hreflang |
| **AEO** | FAQ Schema、HowTo Schema、問答結構、`<dl>` 使用率 |
| **GEO** | Schema.org JSON-LD 完整度、段落語意密度、可被 RAG 擷取的結構化區塊比例 |
| **資安(Passive)** | HTTPS、HSTS、CSP、X-Frame-Options、X-Content-Type-Options、Cookie HttpOnly/Secure/SameSite、表單缺 CSRF token、混合內容、外洩 `.git`/`.env`(僅 HEAD request) |

每個發現(Finding)必須包含:
- `severity`:critical / high / medium / low / info
- `category`:seo / aeo / geo / security / ux
- `title`:短描述
- `description`:**漏洞說明**(給人類看,以繁中清楚敘述問題是什麼、為什麼是問題、可能造成什麼影響)
- `remediation`:**修補建議**(給人類看,描述「該怎麼改方向」即可,**不需給出實際程式碼**)
- `evidence`:觸發證據(HTML 片段或 header dump,供使用者佐證)
- `bounding_box`:`{x, y, width, height}`(若可對應到頁面元素)
- `selector`:對應 CSS selector(備援用)
- `ai_handoff_prompt`:**結構化問題敘述 Prompt**,讓使用者複製後自行貼到 ChatGPT/Claude 詢問修復方式。本系統**僅產生問題描述的 Prompt,不產生修復碼**。

`ai_handoff_prompt` 模板範例:
````
我網站有以下問題,請協助我分析並提供修復方向:
- 問題類型:{category}
- 嚴重度:{severity}
- 問題描述:{description}
- 相關 HTML 片段:
```html
{evidence}
```
- 修補建議方向:{remediation}

請依此資訊提供具體修改方向、檢查步驟與注意事項；不要輸出完整修復程式碼。
````

### M3. 中央互動工作區(核心 UX)
- **不使用 iframe**(避免 X-Frame-Options / CORS)
- 中央顯示 Playwright 擷取的「完整長截圖」(響應式縮放)
- 截圖上方疊一層 `<canvas>`,依 Finding 的 `bounding_box` 繪製高光框
- 左/右側邊欄:Findings 列表(可依 category / severity 篩選),每筆為 Button
- 點擊 Button:
  1. Canvas 高光框 fade-in 對應位置
  2. 中央區域 `scrollIntoView({ behavior: 'smooth', block: 'center' })`
  3. 右側 Panel 滑出顯示完整描述 +「複製問題 Prompt」按鈕(複製 `ai_handoff_prompt`)

### M4. 報告匯出
- **Word(.docx)**:封面 → 摘要(Severity 統計圖表) → 各頁面 Findings 條列(含描述與建議,**不含修復程式碼**) → 附錄
- **AI Prompt 複製**:單一 Finding 一鍵複製其 `ai_handoff_prompt`

### M5. 前台 / 後台分離
- **前台(User Portal)**:Google OAuth 登入、新建掃描任務、查看互動報告、匯出、購買點數、撰寫評論
- **後台(Admin)**:React `/admin/*` 為**唯一**管理介面(django-admin 已整併移除),管理員以前台 email 登入後進入,可管理使用者點數錢包、交易紀錄、評論回覆、掃描任務、CMS 內容、操作紀錄(superuser)

### M6. 點數制度（取代月配額）
- **錢包**：每使用者一個 `CoinWallet`（balance、累積購買、累積掃描）；建立帳號自動發 200 coin，之後每月登入時自動補發
- **掃描扣點**：建立時預扣 `max_pages × 10`，完成依實際頁數退回未使用部分；失敗或被取消全額退回
- **購點**：4 個方案（入門 NT$100/100c、標準 NT$450/500c、進階 NT$800/1000c、旗艦 NT$1500/2200c），目前為模擬付款（直接加 coin），未來可接金流
- **退費**：僅 admin 在後台手動加減 coin（CoinWalletAdmin 自訂 adjust 頁面，可輸入任意金額 + 備註）

### M7. 平台評論
- **一人一則**：`PlatformReview`（rating 1-5、comment、admin_reply）
- **公開列表**：未登入也能讀；登入後可寫/更新自己的評論
- **管理員回覆**：後台編輯 admin_reply 自動填入回覆時間與回覆者，前台公開顯示

---

## 🚀 Phase 2(MVP 完成後再做)

### P1. Hermes-Agent 動態 UX 測試
整合方式:
- **Hermes-Agent** 是本專案的 Agent 行為架構名稱,不代表固定使用 Hermes 模型。
- **不**自架模型,改用已通過測試的 API Provider:MiniMax-M2.7 優先,GLM `glm-4.7-flash` / `glm-4.5-flash` 第二順位,Gemini 作分析備援。
- 採用 **OpenAI-compatible tool/function calling** 格式,避免綁定單一模型供應商。
- 將 Playwright 動作封裝為 Tools 給 Agent 呼叫:
````
  click(selector), type_text(selector, text), scroll(direction, amount),
  get_visible_text(), get_dom_summary(), take_screenshot(),
  report_ux_issue(severity, title, description, selector)
````
- Agent 任務 Prompt 範例:
  > 你正在測試一個電商網站。請嘗試:1) 找到一個商品 2) 加入購物車 3) 進入結帳。過程中若發現任何按鈕點不到、流程斷裂、UI 誤導,呼叫 `report_ux_issue`。
- Agent 行為循環:observe(DOM summary) → think → act(tool call) → observe → ... 最多 20 步或自行 finish
- `report_ux_issue` 的回報結果落地到 `Finding` 表(category=ux),**僅描述問題與建議方向,不產生修復碼**

### P2. 主動式資安測試(需額外授權勾選)
- SQLi 偵測(boolean-based,無破壞性)
- Admin path enumeration(字典 ≤ 100 條常見路徑)
- 開放目錄列表偵測

### P3. 拓撲圖視覺化(D3.js / React Flow)

---

# 🧱 初始架構交付規格(歷史參考)

> 本節保留為早期架構設計參考。正式開發順序以 `開發計畫.md` 為準。

## 1️⃣ 資料庫 Schema(Django Models)
請給出完整可執行的 `models.py`,至少包含:
- `User`(擴充 Django auth)
- `ScanJob`(一次掃描任務,含 status 狀態機:queued / crawling / scanning / agent_testing / completed / failed)
- `Page`(掃描到的每一頁)
- `Finding`(每一個發現,含 bounding_box、selector、severity、category、description、remediation、ai_handoff_prompt)
- `AgentSession`(Hermes Agent 的一次測試 session)
- `AgentStep`(Agent 的每一步 tool call 記錄)
- `AuthorizationConsent`(使用者授權記錄,法律證據)

每個 Model 註明欄位用途,並指出索引(`db_index`)與外鍵 `on_delete` 策略。

## 2️⃣ Playwright + 座標映射的後端邏輯
請提供:
- 一個 async function `capture_page_with_findings(url) -> dict`
- 流程:進入頁面 → 等待 networkidle → 滾動到底(觸發 lazy-load) → 截全頁圖 → 對每個檢測規則執行 `page.locator(...).bounding_box()` 取得座標 → 序列化回傳
- 處理重點:
  - DPR(device pixel ratio)座標換算
  - viewport vs full-page 座標差異
  - 固定定位元素(position: fixed)的座標漂移問題
- 前端對應的 React 元件草圖 `<ScreenshotCanvas />`,說明:
  - 截圖縮放比例計算(`displayWidth / actualWidth`)
  - Canvas 與 img 的 z-index 疊合
  - 高光框繪製動畫(fade-in + pulse)

## 3️⃣ Hermes-Agent + Playwright Tools 整合(虛擬碼)
請提供:
- Tool schema(JSON Schema 格式)定義
- Agent 主迴圈虛擬碼(observe-think-act)
- Prompt 模板(system prompt + 任務 prompt)
- 如何把 Agent 的 `report_ux_issue` tool call 落地存進 `Finding` 表
- Token 消耗與步數上限的安全閘

---

# ✅ 驗收標準
- [x] Models 可直接 `python manage.py makemigrations` 通過
- [x] Playwright 函式為 async,且有 try/except 與 timeout
- [x] 所有給使用者看的字串為繁體中文
- [x] 程式碼遵循 PEP 8(ruff 通過);前端 ESLint(Airbnb) 尚未設定
- [x] **本系統僅產生「問題描述 + 修補方向建議 + 給 AI 用的問題 Prompt」,絕不產生修復後的程式碼**
- [ ] 若有不確定的決策,以 `# DECISION:` 註解標出並說明取捨

---

# 🚫 請勿做的事
- 不要建議替換技術棧
- 除非使用者明確要求,避免一次給超過 3 個檔案的完整實作,以降低審查與整合風險。
- 不要省略法律授權檢查邏輯
- 不要在 Finding、Word 報告、或任何輸出中產生「修復用的程式碼」
- 不要在程式碼中使用 emoji
