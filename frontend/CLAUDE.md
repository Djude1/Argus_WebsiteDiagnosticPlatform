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

- 全域樣式入口是 `src/styles.css`，它只依序 `@import` `src/styles/*.css`（35 個連續區塊，無 CSS modules）
- **匯入順序＝覆寫優先序，不可重排**：日間主題（`40`／`41`）、響應式（`31`）、後台深色主題（`63`）等覆寫層靠「出現在後面」蓋過前面的同權重規則，調動順序會靜默改變畫面
- `10`–`23` 號檔包在 `@layer components` 內（Tailwind 會提到 `@tailwind components` 的位置輸出）；其餘在 layer 之外
- 新樣式放進對應區塊檔；新增整個頁面或元件可建新檔，並在入口插在正確順位
- 拆分時（2026-09-26）build 輸出與拆分前**逐位元組相同**；之後若要把規則搬到別的檔案（例如把日間主題覆寫移到元件旁），必須逐區目視比對，不再能保證相同
- 命名採 BEM-like：`.頁面名-元素名`（例如 `.admin-panel`、`.scan-card`）
- Admin 後台深色 sidebar 顏色使用 CSS 變數（定義在 `src/styles/03-tokens.css` 的 `:root`）
- **禁止使用 inline style**（除非動態計算值，如進度條寬度）
- 後台樣式一律使用 `--admin-*` 語意 token（定義在 `:root`，由品牌色衍生）；不得再寫死 `#0f172a`／`#1e293b` 這類泛用 slate 色值
- **後台支援深色主題**：深色值以 `:root[data-theme="dark"]` 覆寫 `--admin-*` token，**不逐條改規則**。新增後台樣式時請用 token；若非用固定色不可，須同時在檔案末端的深色區塊補上對應覆寫
- 側欄（`.admin-sidebar` / `.admin-nav*` / `.admin-brand*`）**恆為深色**，不隨主題切換，其色值刻意不使用 `--admin-*` token

---

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
| 客戶 | 使用者、訂單、點數交易 |
| 內容與社群 | 評論治理、網站內容、公告（superuser）|
| 系統 | 方案與定價、系統資訊、操作日誌（superuser）|

`superuserOnly` 的項目對 staff **完全不顯示**（不是 disabled）；整組被濾空時連分組標題一起隱藏。

## 前端路由地圖

> 所有根路由定義在 `App.jsx`；實際頁面元件位於下方對應 feature 檔。

| 路由 | 元件 / 頁面 | 說明 |
|---|---|---|
| `/login` | `LoginPage` | Email 登入/註冊；有 Google Client ID 時才顯示 Google OAuth |
| `/project` | `ProjectPage` | 公開行銷頁：產品特色 |
| `/free-tools` | `FreeToolsPage` | 公開免費分析（測速 / URL 風險 / 郵件風險），呼叫 `/api/insights/*` |
| `/team` | `TeamPage` | 公開行銷頁：團隊介紹 |
| `/purchase` | `PurchasePage` | 購買點數（3 步驟結帳 wizard） |
| `/download` | `DownloadPage` | 下載報告 |
| `/scans` | `ScansPlaceholder` → `ScanListPage` | 掃描列表（需登入） |
| `/domains` | `DomainVerifyPage` | 網域所有權驗證（需登入）：新增網域 → 三方法設定說明（DNS TXT / meta / 驗證檔，一鍵複製）→ 執行驗證；主動式資安測試的閘門 |
| `/scans/:scanId` | `ScanDetailPage` | 掃描結果詳情 + findings |
| `/scans/:scanId/topology` | `TopologyPage` | 網站拓樸圖（ReactFlow） |
| `/scans/:scanId/rebuild/:rebuildId` | `RebuildWorkspace` | 單次網頁複刻的工作區：左側 AI 思考過程（1 秒 polling）、右側產出預覽與原稿／優化版比對 |
| `/reviews` | `ReviewsPage`（`PublicLayout`） | 日／夜主題同步的科技評論頁；沿用公開 top bar／footer，提供星等篩選、匿名／遮罩 Email 選項、本人評論管理與評論／官方回覆的逐則按讚、檢舉流程 |
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
| `src/features/scans/ScanExperience.jsx` | 掃描建立、列表、詳情與拓樸頁 |
| `src/features/domains/DomainVerifyPage.jsx` | 網域所有權驗證頁（清單／新增／三方法驗證操作） |
| `src/features/scans/RebuildWorkspace.jsx` | 網頁複刻工作區（思考流＋產出比對）|
| `src/components/scans/PageRebuildPanel.jsx` | 掃描詳情側欄的複刻觸發與狀態 |
| `src/components/scans/FixOutputSection.jsx` | 掃描詳情的「修正產出」專區：四分頁（JSON-LD／OG＋meta／llms.txt／FAQ Schema）、一鍵複製、llms.txt 下載、輪詢產生狀態、逐欄位來源標註（placeholder＝請人工確認） |
| `src/features/account/AuthenticatedPages.jsx` | Dashboard、歷史、購點、設定與登入後導覽 |
| `src/features/reviews/ReviewsPage.jsx` | 公開評論、評分分布、本人評論、逐則按讚／檢舉與日／夜科技介面 |
| `src/features/public/PublicPages.jsx` | 專案、免費工具、團隊、購買介紹與下載等公開頁 |
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
| `src/components/navigation/NavActions.jsx` | 登入後導覽列的通知與帳號操作 |
| `src/components/scans/ScanBadges.jsx` | 掃描狀態與風險等級徽章 |
| `src/api.ts` | Axios instance，統一處理 base URL 與 CSRF token；後台列表函式的參數與回傳綁定產生的型別 |
| `src/shared/apiTypes.ts` | **自動產生，禁止手改**：OpenAPI → TS 型別 |
| `src/shared/apiContracts.ts` | 從 `apiTypes.ts` 取好名字的後台型別出入口 |
| `src/store.js` | Zustand 全域狀態（user、wallet 等） |
| `src/main.jsx` | React entry point，Provider 掛載 |
| `src/styles.css` | 樣式入口：依序 `@import` `src/styles/*.css`（順序即覆寫優先序）|
| `src/styles/03-tokens.css` | 全域設計 token（`:root`，含 admin 深色 sidebar 變數）|
