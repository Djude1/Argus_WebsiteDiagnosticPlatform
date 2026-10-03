# frontend 模組規則

Claude Code 進 `frontend/` 工作時，本檔會在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。規則有衝突時以本檔為準。

---

## React 分層架構

`src/App.jsx` 只負責根路由、權限 wrapper 與 `React.lazy` 載入；頁面依 domain 放在 `src/features/`，共用 UI / hook 放在 `src/components/` 或 `src/shared/`。

- 新頁面放進對應 `features/<domain>/`；檔名須表達頁面集合或職責，不得再把所有頁面塞回 `App.jsx`。
- 單一頁面若有可獨立理解的複雜區塊，抽成 `components/<domain>/<清楚元件名>.jsx`。
- 跨 domain 共用的純 UI、格式化或 hook 放 `shared/`；避免 feature 互相循環 import。
- 新路由在 `App.jsx` 用 `lazyNamed()` 掛載，維持 route-level code splitting。

---

## Build 規則

**必須使用 `build-node22.ps1`，禁止直接執行 `npm run build`。**

原因：系統 Node v24.x + Rollup 4.x 在 Windows 有已知 bug（`STATUS_STACK_BUFFER_OVERRUN`，exit code `-1073740791`），build 會無聲 crash。`build-node22.ps1` 會自動偵測 portable Node 22 位置（候選路徑與安裝方式見 [`docs/node22-guide.md`](../docs/node22-guide.md)）。

```powershell
# 正確 build 方式（在專案根目錄執行）
cd frontend ; .\build-node22.ps1 ; cd ..

# 重灌 node_modules 也要用 portable Node 22 的 npm（路徑見 docs/node22-guide.md，例如）
D:\nodejs\npm.cmd install
```

Dev server（`npm.cmd run dev`）兩種 Node 都能跑，因為 dev 不走 Rollup 打包。

`vite.config.js` 的 `manualChunks` 固定拆出 React、ReactFlow 與 service vendor；新增大型依賴後應先確認 production build 無單一 chunk 超過 500 kB，再決定是否調整既有分組。

---

## 狀態管理

- 全域狀態（`user`、`wallet` 等）放 `store.js`（Zustand）
- API 呼叫統一使用 `api.js` 的 Axios instance
- **禁止在元件中直接使用 `fetch()` 或 `axios`**，理由：`api.js` 統一處理 base URL、CSRF token 和 401 攔截
- Access token 只存在 Zustand 記憶體；refresh token 由後端 HttpOnly cookie 管理，禁止存入 localStorage

---

## 樣式規範

- **品牌規範**：見 [`docs/brand-guidelines.md`](../docs/brand-guidelines.md)（Night Watch：虹膜青主色、守望琥珀點綴、Sora／Noto Sans TC／JetBrains Mono）。
- **公開頁（`.public-shell`）例外**：視覺維持改版前版本（系統字、深藍＋科技青），樣式在 `21-public.css`、`35-public-legacy.css`（取回的改版前日間／響應式規則）、`70-home.css`、`71-scan-pipeline.css`，最後由 `73-public-refine.css` 做克制整理（區塊節奏、減少外框與光暈）。公開頁新增樣式寫在 `73`，並限縮在 `.public-shell` 內；不要把 Night Watch 的 `--ag-*` 風格套回公開頁。
- **會員區舊版樣式範圍（2026-09-28 起）**：網站專案工作區（`/projects/*`，含掃描建立表單與列表）、掃描詳情（`/scans/:id` 全部子路由：互動報告、拓樸、複刻工作區）、網域驗證、購點使用 `462848b`（Night Watch 改版前）的 JSX 與外觀；設定頁、MCP 接入中心維持改版後版本。原本的 Dashboard 與歷史頁已由網站專案工作區取代（2026-10-02，見下「網站專案工作區」）。
  - 舊版樣式在 `src/styles/legacy-member/`（由 `main.jsx` 在 `styles.css` 之後匯入）：`NN-*.css` 是當時同名檔過濾出這些頁面用得到的規則，照舊版原樣書寫；`90-compat.css` 補共用元件（`shared/AppShared.jsx`）改版後的差異；`00-tailwind.css` 以 `@config` 指定 `tailwind.member-legacy.config.js`（當時的設定，系統字型）。
  - 範圍限制由 `postcss-member-legacy.js`（掛在 `postcss.config.js` 的 tailwind 之後）在 build 時處理：規則一律加上 `:is(.member-legacy, #…)` 前綴（ID 等級特異度），範圍內元素先 `all: revert` 擋掉新版同名 class；`:root`／`html`／`body` 規則改掛在包裝上，`.argus-app`／`.argus-main` 規則改為 `:has(.member-legacy)`，keyframes 加 `ml-` 前綴。包裝是 `App.jsx` 的 `MemberLegacy`（`display: contents`）。
  - **深色主題**：舊版只有淺色。外掛對每條含顏色的舊規則自動產生 `:root[data-theme="dark"]` 版本（淺底→深藍、深字→淺字、淺框→暗框，保留色相）；對映不理想處與頁面底色（對齊公開頁深藍漸層）在 `91-dark.css` 手動覆寫。新增舊版樣式時照淺色寫即可，深色會自動產生。
  - 修改這些頁面的樣式：改 `legacy-member/` 對應檔，**不要**改 `11`／`14`／`16`／`61` 等新版檔（範圍內會被覆寫）；與工作區無關的新頁面不要放進 `MemberLegacy`。
- **網站專案工作區（2026-10-02，`docs/adr/0003-site-project-workspace.md`）**：會員區以網站為單位。頂部導覽列品牌右側是專案切換器（`components/navigation/ProjectSwitcher.jsx`，經 `SiteNav` 的 `leading` 插入，樣式 `64-project-switcher.css` 用 `--ag-*` token）；導覽列連結只放帳號層級入口（所有專案、網域驗證、購點、MCP；2026-10-02 移除指向公開產品介紹的「首頁」，入口移到帳號選單；登入後點品牌回所有專案，`SiteNav` 的 `brandTo`）。中等寬度（≤1180px，含分屏）切換器不顯示小標、日夜鈕只留圖示；≤920px 品牌｜切換器｜帳號同一列、連結第二列（`64-project-switcher.css`）。目前網站的功能在工作區側邊欄（`features/projects/ProjectWorkspace.jsx`），各分頁在 `ProjectPages.jsx`，樣式 `legacy-member/93-projects.css`。**會員工作區是報告式外觀**（`legacy-member/94-report-style.css`，2026-10-02）：白底細線分區、圓角 6px 無陰影、選中用字重＋底線或中性底色（不用彩色左邊條）、嚴重度／分數／狀態用色點或上色數字（不用彩色底膠囊）、側邊欄不用圖示、主要動作不放右上角、不用 emoji；舊版元件的深色自動規則會帶回彩色底，94 檔末尾有明確的深色覆寫。網站圖示一律用 `components/projects/SiteFavicon.jsx`（`project.favicon` data URL，沒有就顯示首字）。「目前專案」存在 store（`currentProjectId`，localStorage `argus_current_project`，只是個人便利設定）；切換時停留在同一個分頁（`projectSwitchPath`）。切換器每列顯示最新分數與設定齒輪，專案多於 6 個時出現搜尋框，↑／↓ 移動焦點。掃描表單在專案內以專案預設（起始網址、`default_scope`、`default_categories`）起始，草稿 key 為 `argus_scan_draft_v1:project-<id>`；掃描整體進度一律用 `ScanExperience.jsx` 的 `scanProgress()`（總覽進度條與掃描詳情共用）。掃描詳情網址維持 `/scans/:id`，由 `ProjectScanShell` 依掃描所屬專案顯示同一個側邊欄。`/dashboard`、`/scans`、`/history` 由 `ProjectHomeRedirect` 轉到目前專案的對應分頁，沒有專案時到 `/projects/new`。判斷公開頁一律用路徑段比對（`/project` 不能吃到 `/projects`）。
- **頂部導覽列**：公開頁與登入後頁面共用 `components/navigation/SiteNav.jsx`（`.public-nav` 樣式，21-public／35-public-legacy），兩者只差連結清單與右側動作區（登入後是 `NavActions`：點數與帳號選單）。不要再為登入後另做一套導覽列樣式。**導覽列的尺寸與排版（高度、內距、logo、字級、連結高度、按鈕高度）日／夜共用**，寫在 `35-public-legacy.css` 的無主題規則；`:root[data-theme="light"]` 規則只能改顏色、陰影與背景——2026-09-28 前尺寸只寫在日間規則裡，切換主題時整條導覽列高度 93↔75px 跳動，且日間規則壓過響應式媒體查詢。會員導覽列項目見 `features/account/TopNav.jsx`（帳號設定與評論在右側頭像選單；網站專案切換器在品牌右側）。
- 全域樣式入口是 `src/styles.css`，依序 `@import` `src/styles/*.css`；**匯入順序＝覆寫優先序，不可隨意重排**。
- **顏色一律用 `--ag-*` 語意 token**（`03-tokens.css`）：深色值在 `:root`（預設主題），日間值在 `:root[data-theme="light"]`。規則只寫一次、兩個主題自動正確；**不要再寫 `:root[data-theme="light"] .xxx` 的逐條覆寫**，也不要寫死 Tailwind `slate-*`／`blue-*`／`indigo-*` 或青→紫漸層。
- 品牌元件樣式在 `05-brand.css`（`ArgusMark`／`ArgusLogo`、`.ag-eyebrow`、`.ag-viewfinder`、`.ag-surface-grid`）；核心元件（`.panel`、`.primary-button`、`.secondary-button`、`.input`、`.severity`、`.status-badge`、`.category-pill`…）在 `10-components-core.css`，已全面 token 化。
- 標誌一律用原品牌圖：`ArgusLogo`（`brand-logo.webp`）與 `ArgusMark`（`argus-eye-still.webp`），元件在 `components/brand/ArgusMark.tsx`；動態之眼 `argus-eye.webp` 只用於首頁 hero。圖示用 `shared/LineIcons.jsx`／`shared/ActionIcons.jsx`，不用 emoji。
- 後台 `--admin-*` token 定義在 `18-admin.css` 開頭，由 `--ag-*` 衍生，深／淺主題自動切換；側欄恆為深色（`--admin-sidebar-*`）。後台樣式一律用 `--admin-*` 或 `--ag-*`。
- 多數 `10`–`22` 號檔包在 `@layer components` 內（Tailwind 會提到 `@tailwind components` 的位置輸出）。
- 命名採 BEM-like：`.頁面名-元素名`（例如 `.admin-panel`、`.scan-card`）。
- **禁止使用 inline style**（除非動態計算值，如進度條寬度、分數環尺寸）。
- 動畫須尊重 `prefers-reduced-motion`（`03-tokens.css` 已全域處理）；390px 寬不得出現水平捲動。

## 元件新增規範

- 鼓勵依 domain 新增獨立 `.jsx` 元件檔；檔名使用 PascalCase 並與主要 export 同名。
- 一次性、短小且只服務單頁的元件可留在該 feature 檔案，避免過度分拆。
- 不建立 `utils.jsx`、`helpers.jsx`、`components.jsx` 這類職責不明的垃圾桶檔名。

---

## 套件安裝

安裝新套件前**必須告知使用者**，因為需要用 portable Node 22 的 npm（路徑見 [`docs/node22-guide.md`](../docs/node22-guide.md)，例如）：

```powershell
D:\nodejs\npm.cmd install 套件名
```

---

## 禁止事項

| 禁止 | 原因 |
|---|---|
| `npm run build` | Node v24 Rollup crash |
| `npm install` 不指定路徑 | 可能用到系統 Node v24 |
| `fetch()` / `axios` 直接呼叫 | 繞過 api.js 的 token 處理 |
| inline style（除動態值）| 難以維護，破壞主題一致性 |
| 把新頁面直接塞回 `App.jsx` | 破壞 route-level 分層與 lazy loading |
| 職責不明的 `utils.jsx` / `components.jsx` | 難以定位與形成循環依賴 |

---

## 後台側欄導覽分組

側欄依「使用者來後台做什麼」分為四組，每組 3 項（定義見 `AdminPages.jsx` 的 `ADMIN_NAV_GROUPS`）：

| 分組 | 項目 |
|---|---|
| 營運 | 概覽、掃描任務、網域驗證、系統健康 |
| 客戶 | 使用者、訂單、點數交易、合作洽談 |
| 內容與社群 | 評論治理、網站內容、公告（superuser）|
| 系統 | 方案與定價、系統資訊、操作日誌（superuser）|

`superuserOnly` 的項目對 staff **完全不顯示**（不是 disabled）；整組被濾空時連分組標題一起隱藏。

## 前端路由地圖

> 所有根路由定義在 `App.jsx`；實際頁面元件位於下方對應 feature 檔。

| 路由 | 元件 / 頁面 | 說明 |
|---|---|---|
| `/login` | `LoginPage` | Email 登入/註冊；有 Google Client ID 時才顯示 Google OAuth |
| `/project` | `ProjectPage` | 公開行銷頁：hero、產品預覽、檢測面向與方法、掃描流程、交付物與證據、核心功能、安全邊界、技術棧、FAQ（團隊頁、平台規模與開發歷程已於 2026-09-28 移除） |
| `/free-tools` | `FreeToolsPage` | 公開免費分析（測速 / URL 風險 / 郵件風險），呼叫 `/api/insights/*` |
| `/purchase` | `PurchasePage` | 購買點數（3 步驟結帳 wizard） |
| `/download` | `DownloadPage` | 下載報告 |
| `/verify` | `VerifyReportPage` | 報告查驗（公開導覽列有入口） |
| `/partners` | `PartnersPage`（`features/public/PartnersPage.jsx`） | 商業合作：合作方式、客戶會拿到什麼、流程、FAQ 與洽談表單（`POST /api/content/partner-inquiries/`；後台 `/admin/partner-inquiries` 檢視） |
| `/settings` | `SettingsPage` | 帳號設定：個人資料、大頭貼上傳／移除（`/api/auth/me/avatar/`）、密碼、外觀 |
| `/mcp` | `McpAccessPage`（`features/account/McpAccessPage.jsx`） | MCP 接入中心（入口在會員頂部導覽列，取代原本的「設定」；帳號設定改由右側帳號選單進入）：訂閱狀態、本月用量、端點；三步驟「選擇工具 → 複製設定 → 驗證連線」（Claude Code／Codex／Cursor／VS Code／Claude Desktop／curl）；憑證建立（明文只顯示一次）與撤銷、最近呼叫、可用工具。API 為 `/api/mcp-access/*`，樣式 `63-mcp-access.css` |
| `/projects` | `ProjectsListPage`（`features/projects/ProjectWorkspace.jsx`） | 所有網站專案：一列跨網站數字（網站數、平均分數、低於 60 分、目前問題、進行中）＋網站登記表（圖示與名稱、分數與變化、走勢、各維度分數、目前問題依嚴重度、上次掃描；可依需要注意／最近掃描／名稱排序，超過 4 個網站可搜尋；窄螢幕每列改為區塊）；可展開已封存的專案並恢復（`?archived=true`） |
| `/projects/new` | `ProjectCreatePage` | 新增網站專案（網址＋選填名稱；同網站已有專案回 409 並引導過去，已封存的自動恢復） |
| `/projects/:id` | `ProjectWorkspace` ＞ `ProjectOverviewPage`（`ProjectPages.jsx`） | 專案總覽儀表板：分數與上次相比、問題數、新增／持續／本次未出現、各維度分數與小走勢線、趨勢、嚴重度分布、各維度問題數、AEO 摘要、優先改善建議、本次掃描覆蓋、最近掃描、進行中掃描（有掃描在跑時每 5 秒更新）、公告 toast（區塊在 `components/projects/DashboardWidgets.jsx`） |
| `/projects/:id/scans` | `ProjectScansPage` | 建立掃描（`ScanJobForm project=…`：預設專案起始網址、送出帶 `project`）＋此網站全部掃描（`ScanList`） |
| `/projects/:id/issues` | `ProjectIssuesPage` | 問題分析：選擇掃描、維度／嚴重度／變化篩選（寫在網址、`replace` 不污染上一頁）、「連續 N 次」與受影響頁面、「查看證據」連到 `/scans/:id?finding=`、本次未出現；可展開看說明／修法／全部受影響頁面、`?group=category` 依維度分組、匯出 CSV（`issuesToCsv`，含 BOM） |
| `/projects/:id/aeo` | `ProjectAeoPage` | AEO 問答檢測：選擇掃描、AEO 分數／題數／可回答比例／附原文比例，逐題結果可依判定篩選（`AeoAnswerPanel withFilter`）；原本在掃描詳情最下方 |
| `/projects/:id/pages` | `ProjectPagesPage` | 頁面：選擇掃描，每頁狀態碼、載入時間、問題數與最高嚴重度、各維度問題數；篩選（有問題／錯誤或被阻擋／載入 > 3 秒）、搜尋、表頭排序、截圖預覽、連到該頁問題 |
| `/projects/:id/history` | `ProjectHistoryPage` | 歷史報告：分數趨勢、歷次掃描表格、問題分析與 Word 報告下載 |
| `/projects/:id/settings` | `ProjectSettingsPage` | 名稱、起始網址（須同網站）、預設掃描設定（範圍、維度）、網域驗證狀態、封存 |
| `/dashboard`、`/scans`、`/history` | `ProjectHomeRedirect` | 舊入口：轉到目前專案的總覽／掃描／歷史報告 |
| `/domains` | `DomainVerifyPage` | 網域所有權驗證（需登入）：新增網域 → 三方法設定說明（DNS TXT / meta / 驗證檔，一鍵複製）→ 執行驗證；主動式資安測試的閘門 |
| `/scans/:scanId` | `ProjectScanShell` ＞ `ScanLayout` ＞ `ScanDetailPage` | 掃描報告（外框是所屬專案的側邊欄；`ScanLayout` 是「← 所有掃描」＋報告／網站結構圖／修正產出三個分頁）：標題與分數 → 摘要（嚴重度、各維度、優先處理）→ 檢視器（左：頁面下拉＋維度／嚴重度篩選＋問題清單；右：選中問題的說明與證據、固定高度可捲動並自動捲到元素的截圖、選定單頁時的複刻工具）→ 收合的執行紀錄；進行中顯示細分階段進度（`progress.steps`／`step`，對照表 `SCAN_STEP_META`，含 `aeo_answers`「AEO 問答檢測」）；整體百分比＝(已完成階段數＋本階段 `step_done/step_total`)／階段數，每個階段各有自己的小進度條，進度條與階段同步推進 |
| `/scans/:scanId/topology` | `TopologyPage` | 網站結構圖（ReactFlow） |
| `/scans/:scanId/fixes` | `ScanFixOutputPage` | 修正產出（`FixOutputSection`；掃描完成才可產生，原本在報告最下方） |
| `/scans/:scanId/rebuild/:rebuildId` | `RebuildWorkspace` | 單次網頁複刻的工作區：左側 AI 思考過程（1 秒 polling）、右側產出預覽與原稿／優化版比對 |
| `/reviews` | `ReviewsPage`（未登入：`PublicLayout`；登入後：會員區，會員導覽列、無公開頁尾，網址相同；會員入口在頭像選單） | 日／夜主題同步的科技評論頁（樣式為改版前版本：`50`／`51`／`52-reviews*`）；沿用公開 top bar／footer，提供星等篩選、匿名／遮罩 Email 選項、本人評論管理與評論／官方回覆的逐則按讚、檢舉流程 |
| `/reviews-next` | → redirect `/reviews` | 比較階段舊網址的相容轉址，不再維護第二套頁面 |
| `/admin` | → redirect `/admin/overview` | staff 進入點 |
| `/admin/overview` | `AdminOverviewPage` | 概覽：今日脈搏、14 天趨勢、總量統計與成本明細 |
| `/admin/users` | `AdminUsersPage` | 使用者管理（`AdminUsersPages.tsx`）|
| `/admin/users/:userId` | `AdminUserDetailPage` | 使用者詳情 + 點數調整、訂閱、登入記錄（`AdminUsersPages.tsx`）|
| `/admin/orders` | `AdminOrdersPage` | 訂單管理（狀態分段切換、搜尋 email／姓名／公司／統編、發票類型篩選、明細 modal）|
| `/admin/transactions` | `AdminTransactionsPage` | 點數交易紀錄（`AdminTransactionsPage.tsx`；類型篩選涵蓋 `CoinTransaction.Kind` 全部 11 種）|
| `/admin/reviews` | `AdminReviewsPage` | 評論治理（官方回覆、評論／回覆檢舉分開統計、隱藏／重新公開；`AdminReviewsPage.tsx`） |
| `/admin/scans` | `AdminScansPage` | 掃描任務管理（`AdminScansPages.tsx`）|
| `/admin/scans/:scanId` | `AdminScanDetailPage` | 掃描詳情（管理員視角）；含終止與重排處置、`top_actions`、`warning_summary` |
| `/admin/health` | `AdminHealthPage` | 系統健康：動態掃描鏈路圖（資料庫→Redis→Worker→佇列→掃描執行，斷點之後停止流動）＋ 系統資源（CPU／記憶體／磁碟／網路／運行時間）＋ 逐項判定依據；預設每 15 秒自動更新 |
| `/admin/domains` | `AdminDomainsPage` | 網域驗證管理（搜尋／狀態篩選、人工核准與否決）（`AdminDomainsPage.tsx`；篩選在網址上）|
| `/admin/content` | `AdminContentPage` | CMS 內容管理 |
| `/admin/partner-inquiries` | `AdminPartnerInquiriesPage` | 商業合作洽談（`/partners` 表單送來的資料；只能改處理狀態與內部備註，含「疑似垃圾訊息」狀態）|
| `/admin/plans` | `AdminPlansPage` | 定價方案管理（`AdminPlansPage.tsx`；成本／毛利試算見 `features/admin/planEconomics.ts`，每頁 coin 數取自後端）|
| `/admin/settings` | `AdminSettingsPage` | 系統資訊（唯讀；敏感值只顯示「已設定／未設定」布林，不輸出實際值）|
| `/admin/announcements` | `AdminAnnouncementsPage` | 公告管理（superuser 限定）（`AdminAnnouncementsPage.tsx`）|
| `/admin/audit-log` | `AdminAuditLogPage` | 管理員操作稽核軌跡（superuser 限定）；交易與掃描已各自獨立成頁，不再內嵌分頁（`AdminAuditLogPage.tsx`；動作篩選涵蓋 `AdminAuditLog.Action` 全部 9 種）|

## API 型別與測試

前端型別由後端 schema 產生，**不要手寫**。後端改了 serializer 或查詢參數後要重新產：

```bash
uv run python backend/manage.py spectacular --file frontend/openapi.json --format openapi-json
cd frontend && npx openapi-typescript openapi.json -o src/shared/apiTypes.ts
npm run typecheck
```

- `apiTypes.ts` 是產生物，**禁止手改**；要改型別就去改後端的 serializer／`@list_schema` 標註。
- 呼叫端一律從 `src/shared/apiContracts.ts` 取型別，不要直接寫 `components["schemas"][...]`。
- **`openapi-typescript` 需要 TypeScript 5.x**：TS 7（Go 改寫版）沒有暴露 `ts.factory`，產生時會 crash。
- TypeScript 是**漸進導入**：`allowJs: true` + `checkJs: false`，既有 `.jsx` 不受影響；新檔案與改動較大的舊檔案才轉 `.ts`／`.tsx`。
- 檢查指令：`npm run lint`（ESLint）、`npm run typecheck`、`npm test`（Vitest + jsdom + Testing Library）。**三者都在 CI 的 Quality Gate 與前端 image build 中執行**，任一失敗前端 image 就不會建出。測試檔與元件放同目錄（`X.test.tsx`）。
- 測試寫「元件註解承諾的行為」（例如 Esc 可關、錯誤一定有重試鍵、0 不能被當成空值），不測內部實作；用 role／可及名稱查元素，不用 class。
- **`.tsx` 引用 `.jsx` 元件時**，TS 會把沒有預設值的解構 props 推成必填；遇到這種情況就把該元件轉成 `.tsx` 並寫明 props 型別，不要在呼叫端硬塞 `undefined`。
- **日期格式化的分隔字元來自 ICU 語系資料**（Node 22 + ICU 78 是 U+2009 thin space），各版本／瀏覽器不同，測試不要寫死空白字元。
- **頁面要吃到型別保護必須是 `.tsx`**：`.jsx` 因 `checkJs: false` 不檢查，呼叫型別化 API 也擋不住欄位錯誤。轉換方式參考 `AdminScansPages.tsx`——網址參數（字串）送進 API 前要窄化成後端宣告的型別（整數、`ordering` 白名單），壞值送 `undefined` 交給後端預設。
- **前端列舉後端 choices 時用 `Record<後端Enum, 標籤>`**（例：`AdminTransactionsPage.tsx` 的 `KIND_LABELS`）：後端新增選項而前端沒補，會是編譯錯誤。原本手寫的選項清單曾漏掉 11 種交易類型中的 6 種。
- **enum 型別從欄位索引取，不要引用 `StatusA7fEnum` 這類名稱**：多個 model 都有同名欄位（如 `status`）時，drf-spectacular 產生的 enum 名稱帶雜湊後綴，其他 enum 變動時可能改名。寫成 `AdminVerifiedDomain["status"]`（見 `apiContracts.ts` 的 `VerifiedDomainStatus`）。
- 後端 `JSONField`（如 `top_actions`、`warning_summary`）在 schema 只能是 `unknown`；在頁面內以本地 type 描述結構並註明產生端檔案，不要用 `any`。
- **ESLint 的定位是抓執行期錯誤，不是風格**（設定見 `eslint.config.js`）：`.jsx` 不經型別檢查，引用不存在的名稱時 build 照樣成功、到瀏覽器才炸，由 `no-undef`／`react/jsx-no-undef` 攔下；另含未使用變數與 hooks 規則。刻意不開 prop-types、排版規則與 react-hooks v7 的 React Compiler 規則。
- **確認 lint 結果看結束碼，不要 grep 輸出**：終端機若輸出色碼，`grep " error "` 會匹配失敗而誤判為乾淨（2026-09-26 因此漏掉 2 個孤兒 import，後由完整 `npm run lint` 抓到）。
- **ESLint 固定在 9**：`eslint-plugin-react` 7.37 的 peer 只到 ESLint 9.7。
- 後端回應 schema 的欄位一律標為必填（`backend/config/spectacular_hooks.py`），型別上不會出現 `status?:` 這種「不會發生的缺欄位」；可能為空的欄位才是 `| null`。
- import 一律不寫副檔名（`../../shared/useListQuery`）：寫 `.js` 但實體是 `.ts` 時 Vite 會默默改找，看起來像 JS 檔、容易誤導。

## 為什麼要這套型別管線

後台出過兩次**靜默失效**——畫面照常顯示、沒有任何錯誤，但結果是錯的：

1. `?user=` 沒列進 `useListQuery` 的 `defaults`：網址帶著參數，列表完全不篩選。
2. `user_id` 沒進 `AdminScanJobSerializer`：掃描列表連到使用者的連結永遠不會出現。

兩者都只能靠人眼發現。現在前者是 `useListQuery` 的泛型擋下、後者是產生的型別擋下，
兩種都會變成編譯錯誤。後端側的契約由 `apps/admin_api/tests.py` 的
`AdminOpenAPISchemaTests` 鎖定。

## 核心檔案

| 檔案 | 職責 |
|---|---|
| `src/App.jsx` | 根路由、權限 wrapper、lazy feature 載入 |
| `src/features/auth/AuthPages.jsx` | 登入、註冊與密碼重設頁 |
| `src/features/projects/ProjectWorkspace.jsx` | 網站專案工作區外框（側邊欄、`useProject`）、`ProjectScanShell`、`ProjectHomeRedirect`、所有專案與新增專案頁 |
| `src/features/projects/ProjectPages.jsx` | 專案的總覽、掃描、問題分析、頁面、AEO 問答、歷史報告、專案設定七個分頁 |
| `src/components/projects/DashboardWidgets.jsx` | 總覽儀表板區塊：各維度分數＋小走勢線（small multiples，不靠顏色辨識維度）、單色數量長條、本次掃描覆蓋、AEO 摘要、最近掃描 |
| `src/components/navigation/ProjectSwitcher.jsx` | 頂部工具列的網站專案切換器（目前專案、切換、設定入口、所有專案、新增專案；Esc／點外面關閉） |
| `src/components/projects/OverviewWidgets.jsx` | 分數環 `ScoreRing` 與公告 toast（原 Dashboard 元件） |
| `src/features/scans/ScanExperience.jsx` | 掃描建立表單（`ScanJobForm`，可帶 `project`）、此網站的掃描列表（`ScanList`）、詳情與拓樸頁（462848b 舊版）；估價＝`有效頁數 × 已選維度數 × coin_per_category` ＋（全網站且勾 UX 時）`wallet.agent_ux_fee`（AI Agent 擬真使用者 UX 測試附加費），維度說明列會顯示這筆 |
| `src/features/domains/DomainVerifyPage.jsx` | 網域所有權驗證頁（清單／新增／三方法驗證操作） |
| `src/features/scans/RebuildWorkspace.jsx` | 網頁複刻工作區（思考流＋產出比對）|
| `src/components/scans/PageRebuildPanel.jsx` | 掃描詳情側欄的複刻觸發與狀態 |
| `src/components/projects/SiteFavicon.jsx` | 網站圖示（`project.favicon` 或名稱首字）；切換器、側邊欄、總覽、所有專案共用 |
| `src/components/scans/AeoAnswerPanel.jsx` | 專案「AEO 問答」分頁的逐題結果（`withFilter` 時可依判定篩選、不重複顯示標題與計數）：逐題判定（可回答／資訊不足／內容衝突／無可用答案）、展開看理由與原文證據；`scan.aeo_report.status` 非 `evaluated` 時只顯示「未充分評估」與原因、不顯示比例（樣式在 `legacy-member/92-layout.css` 的 `.aeo-*`） |
| `src/components/scans/FixOutputSection.jsx` | 掃描的「修正產出」分頁（`/scans/:id/fixes`）：四分頁（JSON-LD／OG＋meta／llms.txt／FAQ Schema）、一鍵複製、llms.txt 下載、輪詢產生狀態、逐欄位來源標註（placeholder＝請人工確認） |
| `src/features/account/AuthenticatedPages.jsx` | 會員區入口：re-export `TopNav`／`BillingPage`（＋`SubscriptionPanel`）／`SettingsPage`，各頁實作在同目錄同名檔；購點為 462848b 舊版 |
| `src/features/reviews/ReviewsPage.jsx` | 公開評論、評分分布、本人評論、逐則按讚／檢舉（樣式 `50-reviews.css`＋`51-reviews-dark.css`＋`52-reviews-layout-v2.css`） |
| `src/features/public/PublicPages.jsx` | 公開頁 layout（導覽＋分組頁尾）與專案、免費工具、購買介紹、下載、報告查驗頁 |
| `src/features/public/PartnersPage.jsx` | 商業合作頁與洽談表單（樣式在 `73-public-refine.css` 的 `partners-*`）|
| `src/components/navigation/SiteNav.jsx` | 公開頁與登入後共用的頂部導覽列外殼＋日夜切換鈕 |
| `src/features/public/NotFoundPage.jsx` | 未匹配路由的 404 頁面 |
| `src/features/admin/AdminPages.jsx` | React 管理後台 layout 與各管理頁（掃描頁已拆出）|
| `src/features/admin/AdminScansPages.tsx` | 掃描列表與掃描詳情（TypeScript，走型別化 API；頁面層測試鎖定 `?user=` 篩選與使用者連結）|
| `src/features/admin/AdminUsersPages.tsx` | 使用者列表與使用者詳情（串詳情／調整點數／訂閱／登入記錄／方案五個端點）|
| `src/features/admin/adminHelpers.ts` | 後台 `.tsx` 頁共用：`toAllowed`（白名單窄化）、`toPositiveInt`、`statusLabel`、`errorDetail`、`fieldErrors`（DRF 400 欄位錯誤 → 表單欄位）|
| `src/components/admin/activateAdminRow.ts` | `role="link"` 表格列的鍵盤開啟（Enter／空白鍵）|
| `src/features/admin/AdminOrdersPage.jsx` | 訂單管理頁（接上後端既有的 `/admin/orders/`）|
| `src/features/admin/AdminOverviewPage.jsx` | 概覽（後台首頁）|
| `src/features/admin/AdminHealthPage.jsx` | 系統健康頁 |
| `src/components/admin/AdminScanChain.jsx` | 掃描鏈路圖（節點狀態＋流動動畫，斷點後停止）|
| `src/components/admin/AdminSystemStats.jsx` | 系統資源卡片（含容器／主機量測範圍標示）|
| `src/components/admin/AdminStatCard.tsx` | 統計卡與內嵌 sparkline |
| `src/components/admin/AdminMiniChart.jsx` | 後台多序列折線圖 |
| `src/components/admin/AdminModal.tsx` | 後台統一 modal 與 `AdminField` 表單欄位（label／hint／error 三段式）|
| `src/components/admin/AdminStates.tsx` | 後台載入骨架、空狀態與區塊級錯誤狀態 |
| `src/components/admin/AdminPagination.tsx` | 後台共用分頁 |
| `src/components/admin/AdminSortableTh.tsx` | 可排序表頭（排序由後端 `ordering` 參數完成）|
| `src/shared/formatters.js` | 日期／時間／數字／金額格式化，禁止在 JSX 直接寫 `toLocaleString` |
| `src/shared/useListQuery.ts` | 列表頁的搜尋／篩選／排序／分頁狀態與網址同步（泛型綁定 `defaults`，未宣告的鍵無法存取）|
| `src/shared/AppShared.jsx` | 跨 feature 共用圖表、dialog hook、狀態標籤與錯誤格式化 |
| `src/components/brand/IntroSequence.jsx` | 首次進站品牌動畫 |
| `src/components/navigation/NavActions.jsx` | 登入後導覽列右側：點數、頭像選單（帳號設定／購點與訂閱／評論／產品介紹／管理後台）、`AccountAvatar`（有大頭貼顯示圖片，否則顯示縮寫）|
| `src/shared/clipboard.js` | `copyToClipboard`（clipboard API，失敗退回 execCommand）；網域驗證頁與 MCP 頁共用 |
| `src/components/scans/ScanBadges.jsx` | 掃描狀態與風險等級徽章 |
| `src/api.ts` | Axios instance，統一處理 base URL 與 CSRF token；後台列表函式的參數與回傳綁定產生的型別 |
| `src/shared/apiTypes.ts` | **自動產生，禁止手改**：OpenAPI → TS 型別 |
| `src/shared/apiContracts.ts` | 從 `apiTypes.ts` 取好名字的後台型別出入口 |
| `src/store.js` | Zustand 全域狀態（user、wallet、網站專案清單 `projects` 與目前專案 `currentProjectId` 等） |
| `src/main.jsx` | React entry point，Provider 掛載 |
| `src/styles.css` | 樣式入口：依序 `@import` `src/styles/*.css`（順序即覆寫優先序）|
| `src/styles/legacy-member/index.css` | 會員區舊版樣式入口（只作用在 `.member-legacy` 內；網站專案工作區在 `93-projects.css`）|
| `postcss-member-legacy.js` | 把 `legacy-member/` 的規則限縮到 `.member-legacy` 範圍的 PostCSS 外掛 |
| `src/styles/03-tokens.css` | 品牌設計 token（`--ag-*`，深色 `:root`／日間 `[data-theme="light"]`）與全站基礎排版 |
| `src/components/brand/ArgusMark.tsx` | 品牌標誌 `ArgusLogo`（brand-logo.webp）／`ArgusMark`（argus-eye-still.webp） |
