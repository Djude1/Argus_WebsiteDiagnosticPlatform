# frontend 模組規則

Claude 操作 `frontend/` 目錄時，本檔會在專案層 `CLAUDE.md` 之後自動載入。規則有衝突時以本檔為準。

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

- 全域樣式在 `styles.css`（單一 CSS 檔，無 CSS modules）
- 命名採 BEM-like：`.頁面名-元素名`（例如 `.admin-panel`、`.scan-card`）
- Admin 後台深色 sidebar 顏色使用 CSS 變數（定義在 `styles.css` 頂部 `:root`）
- **禁止使用 inline style**（除非動態計算值，如進度條寬度）

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
| `/scans/:scanId` | `ScanDetailPage` | 掃描結果詳情 + findings |
| `/scans/:scanId/topology` | `TopologyPage` | 網站拓樸圖（ReactFlow） |
| `/reviews` | `ReviewsPage`（`PublicLayout`） | 夜間科技評論頁；沿用公開 top bar／footer，提供星等篩選、本人評論管理與評論／官方回覆的逐則按讚、檢舉流程 |
| `/reviews-next` | → redirect `/reviews` | 比較階段舊網址的相容轉址，不再維護第二套頁面 |
| `/admin` | → redirect `/admin/overview` | staff 進入點 |
| `/admin/overview` | `AdminOverviewPage` | 後台總覽 |
| `/admin/users` | `AdminUsersPage` | 使用者管理 |
| `/admin/users/:userId` | `AdminUserDetailPage` | 使用者詳情 + 點數調整 |
| `/admin/transactions` | `AdminTransactionsPage` | 交易紀錄 |
| `/admin/reviews` | `AdminReviewsPage` | 評論治理（官方回覆、評論／回覆檢舉分開統計、隱藏／重新公開） |
| `/admin/scans` | `AdminScansPage` | 掃描任務管理 |
| `/admin/scans/:scanId` | `AdminScanDetailPage` | 掃描詳情（管理員視角） |
| `/admin/content` | `AdminContentPage` | CMS 內容管理 |
| `/admin/plans` | `AdminPlansPage` | 定價方案管理 |
| `/admin/audit-log` | `AdminAuditLogPage` | 操作紀錄（superuser 限定） |

## 核心檔案

| 檔案 | 職責 |
|---|---|
| `src/App.jsx` | 根路由、權限 wrapper、lazy feature 載入 |
| `src/features/auth/AuthPages.jsx` | 登入、註冊與密碼重設頁 |
| `src/features/scans/ScanExperience.jsx` | 掃描建立、列表、詳情與拓樸頁 |
| `src/features/account/AuthenticatedPages.jsx` | Dashboard、歷史、購點、設定與登入後導覽 |
| `src/features/reviews/ReviewsPage.jsx` | 公開評論、評分分布、本人評論、逐則按讚／檢舉與夜間科技介面 |
| `src/features/public/PublicPages.jsx` | 專案、免費工具、團隊、購買介紹與下載等公開頁 |
| `src/features/public/NotFoundPage.jsx` | 未匹配路由的 404 頁面 |
| `src/features/admin/AdminPages.jsx` | React 管理後台 layout 與各管理頁 |
| `src/shared/AppShared.jsx` | 跨 feature 共用圖表、dialog hook、狀態標籤與錯誤格式化 |
| `src/components/brand/IntroSequence.jsx` | 首次進站品牌動畫 |
| `src/components/navigation/NavActions.jsx` | 登入後導覽列的通知與帳號操作 |
| `src/components/scans/ScanBadges.jsx` | 掃描狀態與風險等級徽章 |
| `src/api.js` | Axios instance，統一處理 base URL 與 CSRF token |
| `src/store.js` | Zustand 全域狀態（user、wallet 等） |
| `src/main.jsx` | React entry point，Provider 掛載 |
| `src/styles.css` | 全域樣式（含 admin 深色 sidebar 變數） |
