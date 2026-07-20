# 前端程式碼品質 / UI-UX 審查後修正

**日期**：2026-07-20
**操作者**：Claude

## 變更內容
- `frontend/src/features/public/NotFoundPage.jsx`：移除兩處靜態 inline style，改套用既有的 `.public-hero-content` / `.public-hero-actions` class。
- `frontend/src/features/admin/AdminPages.jsx`：清掉全部 24 處固定值 inline style，改用新增的 CSS class（`.admin-chart-legend i.tone-*`、`.admin-stat-grid.cols-3`、`.admin-balance-big.tight`、`.admin-table th.col-actions`、`.admin-cell-mono`、`.admin-btn.small` / `.admin-btn.danger`、`.admin-icon-lg`、`.ann-modal.sm` / `.ann-modal.lg`、`.ann-form-row`、`.ann-form-radio-group`、`.ann-input-days`、`.admin-log-payload`）；同時把 7 處寫成 `/* eslint-disable-next-line */` 但與程式碼同一行、實際上不生效的註解改成正確作用的 `/* eslint-disable-line */`。
- `frontend/src/styles.css`：新增上述對應的 CSS class 定義。
- `frontend/src/features/public/PublicPages.jsx`：`FreeToolsPage` 四組工具（單頁檢查／測速／URL 風險／郵件風險）重複的 loading/result/error state 與 fetch 邏輯，抽成共用 `useInsightTool(endpoint)` hook。
- `frontend/src/features/account/AuthenticatedPages.jsx`：`BillingPage` 的 `useEffect` 拆成兩個——`/billing/plans/` 只在掛載時打一次，`wallet`/`me` 的 fetch 保留原本依賴陣列；並移除一行過時的重構殘留註解（指向舊版 6500+ 行 `App.jsx` 已不存在的行號）。
- `frontend/src/features/scans/ScanExperience.jsx`：`FindingsWorkspace` 的 `loadDetails()` 補上 `cancelled` flag 與 `try/catch`，比照同檔 `ScanDetailPage`/`TopologyPage` 既有寫法，避免切換 scan 過快或 API 失敗時覆蓋新資料 / unhandled rejection；並把誤植在 `AuthPages.jsx` 開頭、描述 `ScanLayout` 版面設計的長註解移回本檔 `ScanLayout` 定義正上方。
- `frontend/src/features/auth/AuthPages.jsx`：移除上述誤植的 `ScanLayout` 註解。
- `frontend/src/shared/AppShared.jsx`：新增 `useConfirmDialogs()` hook，提供 `confirmDialog(message, { danger })`（回傳 `Promise<boolean>`，取代 `window.confirm`）與 `notifyDialog(message)`（取代 `window.alert`），沿用既有 `.ann-modal` / `.ann-backdrop` 玻璃擬態視覺與 `useDialogFocus` 的 focus trap，並匯出 `useConfirmDialogs`。
- `frontend/src/styles.css`：新增 `.ann-btn-confirm.danger`（紅色，用於刪除類確認按鈕）。
- `frontend/src/features/account/AuthenticatedPages.jsx`、`frontend/src/features/scans/ScanExperience.jsx`、`frontend/src/features/admin/AdminPages.jsx`：全部 8 處 `window.confirm` / `window.alert`（刪除帳號、終止掃描、CMS 項目刪除、方案刪除、公告刪除、評論回覆失敗提示）改用 `useConfirmDialogs()`，破壞性操作一律帶 `{ danger: true }` 顯示紅色確認鍵。

## 原因
使用者請 Frontend Developer agent 對前端做程式碼品質/架構與 UI/UX 審查（見同次對話），審查報告列出上述問題後，使用者確認要一併修正；原生 `confirm`/`alert` 改用自訂 modal 是報告中列為「較大幅度」而分兩輪確認後才動手的項目。

## 影響範圍
- 純樣式/結構重構，未變更任何 API 呼叫參數或業務邏輯行為。
- `FindingsWorkspace` 的資料載入行為新增了失敗容錯（原本未捕捉的 rejection 現在會被吞掉，等下一輪 polling 重試）。
- `BillingPage` 減少了 `/billing/plans/` 的重複請求次數。
- 原本同步阻塞的 `window.confirm`/`alert` 改為非同步（`await confirmDialog(...)`），呼叫端流程從同步 `if (window.confirm(...))` 改成 `if (await confirmDialog(...))`；使用者體感差異：confirm/alert 彈窗改成套用專案深色科技風樣式，其餘互動（Enter/Esc/Tab focus trap、點遮罩取消）行為不變。

## 驗證方式
- 對修改過的 `.jsx`/`.css` 檔以 `esbuild --jsx=automatic` 個別轉譯，語法皆通過（exit 0）。
- 啟動 `vite` dev server（僅 dev，未執行 `npm run build`，符合 `frontend/CLAUDE.md` 的 build 限制），對每個修改過的模組與 `styles.css` 直接發 HTTP 請求觸發 Vite 轉譯，皆回應 200（無 import / 語法錯誤）。
- 未在瀏覽器手動走過完整互動流程（免費工具送出、admin CRUD、帳單頁、掃描詳情頁、刪除帳號/終止掃描/CMS 刪除等確認彈窗），建議之後人工過一次以下路徑確認視覺與互動無誤：`/free-tools`（三個分頁）、`/admin/plans`、`/admin/announcements`、`/admin/audit-log`、`/admin/content`（CMS 刪除）、`/billing`、`/scans/:id`、`/settings`（刪除帳號按鈕）。
- 未執行 production build（`build-node22.ps1`），因本機環境為 Linux 非 Windows，且該腳本是 pwsh 專用；建議下次在 Windows 開發機上依規範跑一次 build 做最終確認。
