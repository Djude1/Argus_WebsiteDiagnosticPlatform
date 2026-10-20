# 評論頁：補靜態說明、修 hydration 跑板

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
只動 `frontend/src/features/reviews/ReviewsPage.jsx`：
- hero 的 `review-next-hero-copy` 在 H1 下補兩段**無條件渲染**的靜態說明（這頁是什麼、評論來源與遮罩、可做的操作），讓預先渲染的 HTML 帶有實際內容。沿用既有 `.review-next-hero-copy > p` 樣式，不改 CSS。
- 新增 `mounted` 狀態（`useEffect` 掛載後才 true）與 `activeTheme = mounted ? theme : "dark"`；最外層主題 class 改用 `activeTheme`，首次 render 與伺服器預渲染（Node 無 localStorage，主題 fallback 成 dark）一致。

## 原因
Argus 自掃 `/reviews` 回報 GEO 問題：`raw_html_text=270` 遠小於 `rendered_text=606`，不執行 JS 的 AI 爬蟲讀不到主要內容；頁面同時「嚴重跑板」。根因：
- `/reviews` 雖在 `PRERENDERED_ROUTES`，但內容幾乎全綁 API（summary／distribution／評論列表），build 時無 API，預渲染只剩一個 H1，故 raw text 僅約 270。
- 最外層主題 class 直接吃 store 的 `theme`；`store.js` 的 `storedTheme` 在模組載入時同步讀 localStorage，瀏覽器是使用者實際主題、Node 預渲染 fallback 成 dark，使用者為淺色時首次 render 與伺服器 HTML 不一致 → React 整塊重畫（跑板）並被記成 JS 執行期錯誤。

## 影響範圍
- 只影響 `/reviews` 一頁，未動其他頁面與 CSS。
- 預渲染 HTML 會多出兩段說明文字，`raw_html_text` 上升、`geo-render-dependent`（核心內容依賴 JS）應下降。
- 登入相關分支（撰寫入口、我的評論）本就在首次 render 都是登出態（`restoreSession` 由 `App.jsx` 在 `mounted` 後才跑、`accessToken` 初始為 null，server／client 一致），不是 mismatch 來源，故未改動。
- 評論列表仍維持前端載入（動態、分頁、使用者內容，不宜凍進 build 快照）。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning，AdminPages）。
- `npm run typecheck`：clean。
- `/reviews` 無既有測試檔。
- 未自動驗證：預先渲染產物（`dist/reviews.html`）與實機 hydration——需 `build-node22.ps1`（本機 Node 24 + Rollup 會 crash，禁用 `npm run build`），由 CI 前端 image build 跑。部署後應 view-source 確認靜態說明在 HTML 內、DevTools console 無 hydration 警告、重掃 raw_html_text 上升。
