# frontend 模組規則

Claude 操作 `frontend/` 目錄時，本檔會在專案層 `CLAUDE.md` 之後自動載入。規則有衝突時以本檔為準。

---

## App.jsx 操作規範

`frontend/src/App.jsx` 是 **6500+ 行的單檔**，包含所有頁面元件與路由。

**修改前必須先 grep 定位，禁止從頭瀏覽。**
原因：盲目瀏覽 6500 行會消耗大量 token 且容易看錯位置。

```powershell
# 定位元件或函式（例如找 AdminUsersPage）
Select-String -Path "src\App.jsx" -Pattern "function AdminUsersPage"
```

- 路由定義在 App.jsx **底部約第 6460 行**的 `<Routes>` 區塊
- 新元件加在對應頁面元件附近，不要集中放在檔案頂部

---

## Build 規則

**必須使用 `build-node22.ps1`，禁止直接執行 `npm run build`。**

原因：系統 Node v24.x + Rollup 4.x 在 Windows 有已知 bug（`STATUS_STACK_BUFFER_OVERRUN`，exit code `-1073740791`），build 會無聲 crash。`build-node22.ps1` 自動切換到 `D:\node22` portable Node 22 執行。

```powershell
# 正確 build 方式（在專案根目錄執行）
cd frontend ; .\build-node22.ps1 ; cd ..

# 重灌 node_modules 也要用 Node 22
D:\node22\npm.cmd install
```

Dev server（`npm.cmd run dev`）兩種 Node 都能跑，因為 dev 不走 Rollup 打包。

---

## 狀態管理

- 全域狀態（`user`、`wallet` 等）放 `store.js`（Zustand）
- API 呼叫統一使用 `api.js` 的 Axios instance
- **禁止在元件中直接使用 `fetch()` 或 `axios`**，理由：`api.js` 統一處理 base URL、CSRF token 和 401 攔截

---

## 樣式規範

- 全域樣式在 `styles.css`（單一 CSS 檔，無 CSS modules）
- 命名採 BEM-like：`.頁面名-元素名`（例如 `.admin-panel`、`.scan-card`）
- Admin 後台深色 sidebar 顏色使用 CSS 變數（定義在 `styles.css` 頂部 `:root`）
- **禁止使用 inline style**（除非動態計算值，如進度條寬度）

---

## 元件新增規範

- **禁止新增獨立的 `.jsx` / `.tsx` 元件檔案**
  原因：本專案刻意採用單檔架構，分拆會破壞現有 import 結構
- 只有跨多個頁面使用的小型 util 元件才考慮抽為獨立函式，但仍放在 App.jsx 頂部「元件」區

---

## 套件安裝

安裝新套件前**必須告知使用者**，因為需要用特定 Node 版本：

```powershell
D:\node22\npm.cmd install 套件名
```

---

## 禁止事項

| 禁止 | 原因 |
|---|---|
| `npm run build` | Node v24 Rollup crash |
| `npm install` 不指定路徑 | 可能用到系統 Node v24 |
| `fetch()` / `axios` 直接呼叫 | 繞過 api.js 的 token 處理 |
| inline style（除動態值）| 難以維護，破壞主題一致性 |
| 新增獨立元件檔案 | 破壞單檔架構 |

---

## 前端路由地圖

> 所有路由定義在 `App.jsx` 底部 `<Routes>` 區塊（約第 6460 行起）。

| 路由 | 元件 / 頁面 | 說明 |
|---|---|---|
| `/login` | `LoginPage` | Google OAuth 登入 |
| `/project` | `ProjectPage` | 公開行銷頁：產品特色 |
| `/free-tools` | `FreeToolsPage` | 公開免費分析（測速 / URL 風險 / 郵件風險），呼叫 `/api/insights/*` |
| `/team` | `TeamPage` | 公開行銷頁：團隊介紹 |
| `/purchase` | `PurchasePage` | 購買點數（3 步驟結帳 wizard） |
| `/download` | `DownloadPage` | 下載報告 |
| `/scans` | `ScansPlaceholder` → `ScanListPage` | 掃描列表（需登入） |
| `/scans/:scanId` | `ScanDetailPage` | 掃描結果詳情 + findings |
| `/scans/:scanId/topology` | `TopologyPage` | 網站拓樸圖（ReactFlow） |
| `/reviews` | `ReviewsPage` | 平台評論 |
| `/admin` | → redirect `/admin/overview` | staff 進入點 |
| `/admin/overview` | `AdminOverviewPage` | 後台總覽 |
| `/admin/users` | `AdminUsersPage` | 使用者管理 |
| `/admin/users/:userId` | `AdminUserDetailPage` | 使用者詳情 + 點數調整 |
| `/admin/transactions` | `AdminTransactionsPage` | 交易紀錄 |
| `/admin/reviews` | `AdminReviewsPage` | 評論管理（可回覆） |
| `/admin/scans` | `AdminScansPage` | 掃描任務管理 |
| `/admin/scans/:scanId` | `AdminScanDetailPage` | 掃描詳情（管理員視角） |
| `/admin/content` | `AdminContentPage` | CMS 內容管理 |
| `/admin/plans` | `AdminPlansPage` | 定價方案管理 |
| `/admin/audit-log` | `AdminAuditLogPage` | 操作紀錄（superuser 限定） |

## 核心檔案

| 檔案 | 職責 |
|---|---|
| `src/App.jsx` | 6500+ 行，所有頁面元件與路由定義全在此 |
| `src/api.js` | Axios instance，統一處理 base URL 與 CSRF token |
| `src/store.js` | Zustand 全域狀態（user、wallet 等） |
| `src/main.jsx` | React entry point，Provider 掛載 |
| `src/styles.css` | 全域樣式（含 admin 深色 sidebar 變數） |
