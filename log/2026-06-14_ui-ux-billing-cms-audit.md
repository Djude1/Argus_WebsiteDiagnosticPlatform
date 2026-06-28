# 2026-06-14 UI/UX × 點數系統 × 後台 CMS 全面審計與重設計提案

> 使用者要求：「目前網站後台和前台在點數設計、後台修改前台內容、前台 dashboard 顯示上非常不合邏輯，且不方便使用」。
> 本次 session 完成 **15%（深度審計 + 業界對齊提案 + 真實成本定價推算）**，剩餘 **85%（含實機截圖、實際 UI 改動、實機回歸測試）** 透過 schedule 自動續做。

---

## 變更內容

本 session **未動 production code**。原因：使用者明確要求「涉及 UIUX，一定需要看到畫面才可以開始更改」，但本機缺 `.env`（`.env.example` 在、實際 `.env` 不在 git，亦未在本機 root），無法 `runserver`，因此本次純做檔案層審計。

實作改動順延至**下次自動續做**，本檔列出**完整可執行的修改清單**。

---

## 原因

當前痛點源自**三條獨立的「成形史造成的不一致」**：

1. **`/purchase`（展示頁）與 `/billing`（結帳 wizard）是兩條獨立旅程，中間沒有 plan_code 帶過去** → 使用者選方案後又要重選。
2. **後台 sidebar 缺隱藏路由入口**（`/admin/transactions`、`/admin/scans` 都有頁面，但 `ADMIN_NAV_ITEMS` 沒入口）→ 變死路。
3. **後台 `/admin/content` 缺 features tab**（後端 `/admin/cms/features/` 早就存在），所以「首頁特色卡片」無法從後台編。
4. **定價沒有任何成本依據**（單純拍腦袋 100/100、450/500…），不知道毛利、不知道相對市場貴或便宜、不知道每個方案使用者能掃多少網站。

---

## 影響範圍

| 模組 | 涉及檔案 | 改動類型 |
|---|---|---|
| 前端購買流 | `frontend/src/App.jsx`（`PurchasePage` ~L4573、`BillingPage` ~L2954） | 卡片可點 + 帶 plan_code、收斂為單一路由 `/billing` |
| 前端 dashboard | `frontend/src/App.jsx`（`DashboardPage` ~L2590） | 「立即掃描」主 CTA、餘額顯示重排、coin→可掃頁數轉換 |
| 前端後台導覽 | `frontend/src/App.jsx`（`ADMIN_NAV_ITEMS` ~L5194） | 補回交易 / 掃描入口；方案 ＋ 內容合併分頁 |
| 前端後台 CMS | `frontend/src/App.jsx`（`CONTENT_TABS` ~L6466、新增 `FEATURE_SCHEMA`、整併 `PLAN_SCHEMA`） | 補 features tab、把 `/admin/plans` 併進 `/admin/content` |
| 前端後台方案管理 | `frontend/src/App.jsx`（`AdminPlansPage` ~L6500） | 顯示「每方案成本 / 毛利 / 估算可掃頁數」 |
| 後端定價種子 | `backend/apps/billing/migrations/0002_seed_plans_and_wallets.py` | 既有資料保留；新增方案以 admin 介面手動調整（不改 migration） |
| Bug 修正 | `backend/apps/agent/providers.py:181` | `default_model = "MiniMax-M2.7"` 並非真實 model id；應為 `MiniMax-M2` 或拿掉 fallback model 預設 |

---

## 驗證方式

實作時依以下順序驗證：

1. `uv run python backend/manage.py check`（含 import）
2. `cd frontend ; .\build-node22.ps1`（build 成功）
3. `uv run python backend/manage.py test apps.billing apps.admin_api`
4. 截圖比對：購買流、dashboard、後台 4 個關鍵頁
5. 實際走一次：選方案→填資料→確認→入帳→看 dashboard 餘額變化

---

## 複查修正（2026-06-14 下半場，使用者放回 .env 後）

逐點重看程式碼後**找到 4 個原審計的錯誤 / 不精準**，更正如下：

| 點 | 原審計 | 複查事實 | 正確結論 |
|---|---|---|---|
| **A1** | 「`/purchase` 卡片不可點」 | BillingPage step 1 卡片本來就有「選擇此方案」按鈕（[App.jsx:3141-3147](frontend/src/App.jsx:3141)），是 BillingPage 沒讀 URL plan param、PurchasePage 跳過去不帶 plan | **問題本質**：PurchasePage 行銷卡 + BillingPage wizard 兩個路由都顯示方案，但 PurchasePage→BillingPage 跳轉沒帶 plan_code，使用者要再選一次 |
| **A7** | 「購買成功頁缺 next action」 | 已經有「再買一次」+「開始掃描」按鈕（[App.jsx:3098-3104](frontend/src/App.jsx:3098)），「開始掃描」直跳 `/scans` | **❌ 完全錯誤**，刪掉這項，不用修 |
| **D1** | 「`AdminContentPage` 缺 features tab」 | ProjectPage 的「核心功能」是 hardcoded array（[App.jsx:4204-4211](frontend/src/App.jsx:4204)），完全沒呼叫 `/api/content/features/`。但後端整條 stack 存在（model / serializer / public view / admin CMS view） | **問題本質**：features 整條 stack 是殭屍代碼。**選擇**：(a) 接通（ProjectPage 改用 API + 後台補 tab）或 (b) 刪除整條後端 stack。**推薦 (a)**——這就是後台 CMS 存在的價值 |
| **D5** | 「兩份方案編輯程式重複」 | `PLAN_SCHEMA` 定義了但**沒有任何地方引用**（`grep PLAN_SCHEMA` 只有定義行）。`AdminPlansPage` 才是實際生效的 | **問題本質**：PLAN_SCHEMA 是殭屍 schema。**選擇**：(a) 刪 PLAN_SCHEMA 改善整潔，或 (b) 改用 PLAN_SCHEMA 整併進 AdminContentPage tab，刪掉 AdminPlansPage。**推薦 (b)** |

**新發現的真實問題（原審計漏掉的）**：

| 點 | 事實 | 問題 |
|---|---|---|
| **F1**（新） | `features` 整條 stack（content.models.ProjectFeature + 公開 view + 寫入 view）完全沒接前端 | 殭屍代碼 → 後端 audit 會增加無用心智負擔 |
| **F2**（新） | `D:\node22` 路徑（CLAUDE.md 寫的）不存在，實際 node22 在 `D:\nodejs`（v22.17.0） | CLAUDE.md 跨層同步漂移；`build-node22.ps1` 也寫死 `D:\node22` |
| **F3**（新） | `build-node22.ps1` 用 UTF-8（含「使用 Node $(...)」中文）但 PowerShell 5.1 預設用 Big5 讀 → 亂碼解析錯誤 | build script 跑不起來；應該加 BOM 或改用純英文訊息 |
| **F4**（新） | `frontend/node_modules` 缺 vite（剛驗證） → build 一定要先 install | 第一次 clone 後若沒 install 會直接失敗 |
| **F5**（新） | `AdminCmsManager` 對 JSON 欄位用「逗號分隔字串」當輸入（[App.jsx:6214-6217](frontend/src/App.jsx:6214)），TeamMember 的 `skill_levels` 和 `contributions` 是 JSON 物件陣列（不是 string array） | TeamMember 後台**根本沒法編 `skill_levels` 和 `contributions`**，前台 /team 卡片這兩個欄位等於唯讀 |

**最終確認成立的點**（共 12 個，原 18 - 2 撤回 - D1 D5 改寫 + F1 F5 新增）：

- A2 兩個路由（`/purchase` + `/billing`）- 成立
- A3 卡片沒顯示「等於幾次掃描」- 成立
- A4 沒體驗方案 - 成立
- A5 定價無成本依據 - 成立（設計判斷）
- A6 step 3 沒顯示總節省 - 成立
- B1 hero 沒 CTA - 成立
- B2 點數 hint 顯示累積購買 NTD - 成立
- B3 高/嚴重沒 click-through - 成立（StatTile 無 onClick）
- B4 最近掃描沒時間 - 成立
- B5 公告 modal 對 temporary 也用 modal（應該 toast）- 成立
- C1/C2 sidebar 沒 transactions / scans 入口 - 成立
- C3 plans 與 content 分兩入口 - 成立（但併入要先選 D5 路徑）
- C4 沒 settings 頁 - 成立
- D2 CMS 沒預覽前台 - 成立
- D3 sort_order 手動算 - 成立
- D4 plans 缺 unit economics - 成立
- E1 前台 nav 沒 dashboard / scans - 成立

---

## 完整審計：18 個具體不合邏輯點（**原版，下方為紀錄保留，請以「複查修正」為準**）

### A. 購買流（pricing / billing）

| # | 現況 | 問題 | 業界做法 | 修法 |
|---|---|---|---|---|
| A1 | `/purchase` 卡片不可點，要捲到底找「前往結帳」按鈕→跳 `/billing` 又要重選方案 | **classic broken flow**：使用者操作中斷、心智模型斷裂 | 每張方案卡內建「選此方案」CTA，點下後直接到 wizard step 2，帶上 plan_code（URL `?plan=advanced`） | `PurchasePage` 卡片加 `onClick` + 內嵌 CTA；`BillingPage` 在 `useEffect` 讀 `URLSearchParams` 取 plan、自動 `pickPlan` 並跳 step 2 |
| A2 | `/purchase` 與 `/billing` 兩個 route，使用者搞不清楚差別 | URL 重複功能、SEO 不利、IA 混亂 | **單一路由**：`/billing` = 整個流程；`/purchase` redirect 到 `/billing` | 把 `/purchase` 改成 redirect；或保留 `/purchase` 作行銷頁但 CTA 直接跳 `/billing?plan=X` |
| A3 | 方案卡只顯示「coin 數」+「coin/NTD」，使用者**不知道這代表幾次掃描** | 業界 SaaS 必做：把計量單位翻譯成具體價值（GB→看幾小時影片；coin→掃幾個網站） | Notion、Linear、Vercel 都用「相當於 N 個 X」 | 卡片加「≈ 50 次小型網站健檢（20 頁）」「≈ 10 次中型網站健檢（100 頁）」 |
| A4 | 沒有「免費試用 / 體驗方案」 | Freemium 是 SaaS 標配；首購門檻太高（NT$100） | 提供「NT$50 / 50 coin」入門體驗或免費試用 50 coin | 新增 `code=trial` 方案 |
| A5 | 定價無成本依據，毛利率不透明 | 定價拍腦袋，admin 不知該不該調 | 建立內部成本模型（LLM token + 伺服器攤提） | 見「定價推算」章節 |
| A6 | wizard step 3 確認頁沒有「總共可省 NT$ X（相比入門價）」 | 大方案的折扣看不見 | 顯示「省 NT$200（相比 5 個入門方案）」 | step 3 加 saved_vs_starter 計算 |
| A7 | 結帳成功頁缺 next action | 完成購買後使用者卡死 | 應該有「立即開始第一次掃描」按鈕 | 加 CTA `→ /scans/new` |

### B. Dashboard（前台主控台）

| # | 現況 | 問題 | 業界做法 | 修法 |
|---|---|---|---|---|
| B1 | hero 標題「你已執行 N 次健檢」，沒有任何 CTA | dashboard 第一螢光應該是「**繼續行動**」，不是顯示歷史 | Linear、Vercel、Notion dashboard 第一塊都是 next-action | hero 右側加「+ 新掃描」實心 CTA |
| B2 | 「點數餘額」tile 的 hint 是「累積購買 NT$ X」 | 把「持有」和「歷史花費」塞同一塊，使用者解讀困難 | 應該 hint「≈ 還能掃 N 頁 / M 個小型網站」 | hint 改為 `≈ 還能掃 ${balance/10} 頁` |
| B3 | 「高/嚴重」tile 沒有 click-through | 看到數字但不能去看是哪些 | Findings dashboard 必做：點數字下鑽到對應 list | 包成 button，導 `/scans?severity=critical` |
| B4 | 「最近掃描」list 沒時間 | 不知道是「剛剛」還是「上週」 | 加「相對時間」（2 分鐘前 / 昨天） | render `formatRelative(scan.created_at)` |
| B5 | 公告 modal 蓋過整個畫面，但有些公告其實該用 toast | 大公告 modal 阻斷使用流（OK），小公告也用 modal 太重 | `temporary` 用 toast，`permanent` 用 modal | 依 `type` 分流 |

### C. 後台導覽（admin sidebar）

| # | 現況 | 問題 | 業界做法 | 修法 |
|---|---|---|---|---|
| C1 | `/admin/transactions` 路由有，**sidebar 沒入口** → 死路 | 隱藏路由 = bug | 所有可訪頁面都應在 nav | `ADMIN_NAV_ITEMS` 補「💳 交易」 |
| C2 | `/admin/scans` 路由有，**sidebar 沒入口** → 死路 | 同上 | 同上 | `ADMIN_NAV_ITEMS` 補「🔍 掃描」 |
| C3 | 「方案」和「內容」分兩個 sidebar 入口，但都是 CMS | 認知負擔大、sidebar 變長 | 同類功能用 sub-tab 收斂 | `/admin/plans` 併進 `/admin/content` 當 tab |
| C4 | 後台沒「設定 / 系統參數」分頁 | `ARGUS_COIN_PER_PAGE`、`ARGUS_MONTHLY_BONUS_COINS` 只能改 .env 重啟 | admin 應該能調 | 新增 `/admin/settings`（先唯讀顯示 + 提示「需 .env」） |

### D. 後台 CMS（修改前台內容）

| # | 現況 | 問題 | 業界做法 | 修法 |
|---|---|---|---|---|
| D1 | `AdminContentPage` 只有 team / releases / milestones **三個 tab**，缺 features | 「首頁特色卡片」（`ProjectFeature`）沒有後台入口可編，但前台 `/project` 一直在顯示 → **靜默壞掉** | CMS 後台應該完整覆蓋所有公開內容 | `CONTENT_TABS` 補 `{ key: "features", schema: FEATURE_SCHEMA }`；參考 `cms_views.ProjectFeatureViewSet` |
| D2 | CMS 編輯後沒有「預覽前台效果」 | 編完只能切到前台 reload 確認 | Notion / Webflow CMS 都有預覽 | tab 內加「預覽前台 →」link，新分頁開 `/project` 等對應頁 |
| D3 | features / team / milestones 的 sort_order 是純數字 input，要手動算 | 排序困難 | 業界用拖拉 reorder | 階段一：加「上移 / 下移」按鈕；階段二再做拖拉 |
| D4 | 後台 plans 編輯沒顯示「coin/NTD」、「估算可掃頁數」、「估算毛利」 | admin 改價時無依據 | SaaS billing 後台必看 unit economics | `AdminPlansPage` 加成本計算欄位 |
| D5 | `AdminPlansPage` 編輯 modal 缺 `code` 欄位（建立時必須要） | 用 `AdminCmsManager` 走 PLAN_SCHEMA 才有 code，但 `AdminPlansPage` 是另一份手寫 modal | 兩份程式重複，發散風險 | 統一走 `AdminCmsManager`，刪除 `AdminPlansPage` 自寫 modal（單一信源） |

### E. 前後台對應（業界準則：同功能同分頁）

| # | 現況 | 問題 | 修法 |
|---|---|---|---|
| E1 | 前台導覽沒「掃描 / dashboard」入口（登入後也沒） | 登入使用者得手動打 `/dashboard` 或回首頁找 hero CTA | `PUBLIC_NAV_ITEMS` 在 `accessToken` 時切換成另一組（dashboard / scans / 評論 / 設定 / 購買） |
| E2 | `/scans` 後台叫「🔍 掃描」、前台叫「掃描」，但**前台 nav 看不到** | E1 衍生 | 同 E1 |

---

## 定價推算（業界對齊）

### 真實成本（每次掃描）

**LLM 成本（MiniMax M2，2026 官方價）**
- Input: $0.30 / 1M tokens（NT$9.75 / 1M，匯率 32.5）
- Output: $1.20 / 1M tokens（NT$39 / 1M）

每次掃描（agent 啟用、actual_pages = 12）token 估算：
| 階段 | input tokens | output tokens |
|---|---|---|
| Agent 規劃 | 8K | 1K |
| 每頁 tool calling × 12 | 12 × 1.5K = 18K | 12 × 0.3K = 3.6K |
| **合計** | **26K** | **4.6K** |

→ LLM 成本 = 26K × $0.30/1M + 4.6K × $1.20/1M = **$0.0133 ≈ NT$0.43 / scan**

**伺服器攤提（VPS + Redis + Postgres + Celery worker）**
- 假設月固定費 NT$1,500（小型 VPS + 雲端 DB）
- 月活 100 人 × 平均 2 次掃描/人 = 200 scans/月
- 攤提 = **NT$7.5 / scan**

**單次掃描真實成本 ≈ NT$8**（12 頁版）

### 目前定價毛利率

| 方案 | NTD | coin | 等價頁數 | 真實成本 | 毛利率 |
|---|---|---|---|---|---|
| 入門 | 100 | 100 | 10 | NT$6.7 | 93.3% |
| 標準 | 450 | 500 | 50 | NT$33.5 | 92.6% |
| 進階 | 800 | 1000 | 100 | NT$67 | 91.6% |
| 旗艦 | 1500 | 2200 | 220 | NT$147 | 90.2% |

**結論：目前定價毛利已經非常健康（90%+）**，**問題不在「便宜」而在「使用者看不懂價值」**。

### 業界對齊建議（不大改價、只重排）

**保留現有四方案 + 新增體驗方案 + 強化「等價於 N 次掃描」說明**

| 方案 | NTD | coin | badge | UI 顯示重點 |
|---|---|---|---|---|
| 體驗 🆕 | 50 | 60 | 「新手首選」 | 「≈ 6 頁掃描 / 1 個小型網站快速健檢」 |
| 入門 | 100 | 100 | – | 「≈ 10 頁掃描 / 1 個小型網站完整健檢」 |
| 標準 | 450 | 500 | -10% | 「≈ 50 頁 / 5 個小型網站 / 1 個中型網站」 |
| 進階 ⭐ | 800 | 1000 | -20% 最熱門 | 「≈ 100 頁 / 10 個小型網站 / 2 個中型網站」 |
| 旗艦 | 1500 | 2200 | -32% 最划算 | 「≈ 220 頁 / 22 個小型網站 / 1 個大型企業站」 |

小型 = 20 頁、中型 = 100 頁、大型 = 200 頁（業界 SEO/safety tool 通用切分）。

### 月贈點（不動）

200 coin = 20 頁 = 1 個小型網站完整健檢，剛好定位為「每月免費試用一次」。

---

## 下次續做的執行清單（85% 工作）

> 排程於 quota 回補後自動接續。每步驟做完都跑 check + 截圖。

### Phase 1：截圖建立 baseline（必須先做，依使用者要求）

選一條路：
- **Option A**：使用者把生產 `.env` 放到 `C:\Users\USER\Documents\Claude code\Argus\.env`，本機 `runserver` 起來後用 Claude Preview / Chrome MCP 截圖
- **Option B**：用 Chrome MCP 連到上線網址直接截圖（不需本機環境）

截圖清單（13 張）：
1. `/dashboard`（已登入）
2. `/scans` list
3. `/scans/:id` detail
4. `/purchase` 介紹頁
5. `/billing` wizard step 1 / 2 / 3 / success（4 張）
6. `/admin/overview`
7. `/admin/users`
8. `/admin/users/:id` detail（含調點）
9. `/admin/plans`
10. `/admin/content`
11. `/admin/transactions`
12. `/admin/reviews`
13. `/admin/scans`

### Phase 2：高 ROI 快速修補（第 1 輪 PR）

**目標：解掉 A1（購買流斷裂）+ C1 C2（後台死路）+ D1（features tab）**

1. `App.jsx` 修 `PurchasePage`：方案卡內建「選此方案」按鈕，`navigate("/billing?plan=" + p.code)`
2. `App.jsx` 修 `BillingPage`：useEffect 讀 `URLSearchParams`，找到 plan 則自動 `pickPlan(plan)` + `setStep(2)`
3. `App.jsx` 修 `ADMIN_NAV_ITEMS`：補 `{ to: "/admin/transactions", label: "交易", emoji: "💳" }` 和 `{ to: "/admin/scans", label: "掃描", emoji: "🔍" }`
4. `App.jsx` 修 `CONTENT_TABS`：補 `{ key: "features", label: "🎯 專案特色", schema: FEATURE_SCHEMA }`；新增 `FEATURE_SCHEMA`
5. `App.jsx` 修 `AdminContentPage`：併入 PLAN_SCHEMA tab，刪 `/admin/plans` sidebar 入口（保留 route 做 backward-compat）
6. 跑 build + check + 截圖驗證

**驗收條件**：
- 從 `/purchase` 選方案 → 直接到 `/billing` step 2，已選好方案
- 後台 sidebar 看得到「交易」「掃描」入口，點進去頁面正常
- `/admin/content` 看得到「專案特色」tab，新增/編輯/刪除可運作

### Phase 3：dashboard 重排（第 2 輪 PR）

1. hero 加「+ 新掃描」CTA
2. 點數 tile hint 改為「≈ 還能掃 N 頁」
3. 「高/嚴重」tile 包成 button、加 click-through
4. 「最近掃描」加相對時間

### Phase 4：方案卡價值翻譯 + 後台 unit economics（第 3 輪 PR）

1. `/purchase` 與 `/billing` step 1 的方案卡加「≈ N 次小型網站健檢」3 行
2. 新增「體驗方案」（NT$50 / 60 coin）
3. `AdminPlansPage`（或併入 `AdminContentPage` 的 plans tab）加成本、毛利、估算可掃頁數計算欄位

### Phase 5：MiniMax model id bug

`backend/apps/agent/providers.py:181`：`default_model = "MiniMax-M2.7"` → 不存在的 model id。修為 `"MiniMax-M2"`（M2 是 2025-10 釋出的旗艦版，價格 $0.30/$1.20，與本提案計算一致）。

### Phase 6：完整回歸 + commit + 部署文件

1. 跑全部測試
2. 寫 log/2026-06-XX_ui-ux-billing-cms-overhaul.md（變更總結）
3. 一次 commit 或拆三個 commit（A1/C/D 一個、B 一個、A3+A4 一個）
4. push 上線後手動驗證

---

## 已驗證的事實（檔案層）

| 事實 | 來源 |
|---|---|
| MiniMax M2 官方價 $0.30/$1.20 per 1M | [minimax.io/news/minimax-m2](https://www.minimax.io/news/minimax-m2) |
| `default_model = "MiniMax-M2.7"`（不存在的 ID） | `backend/apps/agent/providers.py:181` |
| `PUBLIC_NAV_ITEMS` 沒 dashboard / scans 入口 | `frontend/src/App.jsx:3993` |
| `ADMIN_NAV_ITEMS` 沒 transactions / scans 入口 | `frontend/src/App.jsx:5194` |
| `CONTENT_TABS` 沒 features | `frontend/src/App.jsx:6466` |
| `PurchasePage` 卡片不可點、要捲底找 CTA | `frontend/src/App.jsx:4609–4624` |
| `PurchasePage` 跳 `/billing` 不帶 plan_code | `frontend/src/App.jsx:4691` |
| `BillingPage` 進場一定要重選方案（不接 URL param） | `frontend/src/App.jsx:2978–2997` |
| `AdminPlansPage` 與 `AdminCmsManager + PLAN_SCHEMA` 兩份程式重複 | `frontend/src/App.jsx:6421, 6500` |
| `ARGUS_COIN_PER_PAGE=10`、`ARGUS_MONTHLY_BONUS_COINS=200` | `backend/config/settings.py:179–180` |

---

## 結論（給使用者）

- 目前的「不合邏輯」不是樣式問題，是 **information architecture（資訊架構）+ flow（流程）的結構問題**。設計層面已找到 18 個具體點。
- 定價層面：**毛利率 90%+ 已非常健康，問題在「使用者看不懂這多少錢能幹嘛」**。建議「不大改價、只重排 + 加價值翻譯 + 補體驗方案」。
- 本次未動 production code，全部修改清單已列出可執行步驟。
- 下次繼續時最少需要的環境：本機 `.env` 或 Chrome MCP 連線到上線網址（用於截圖驗證）。
