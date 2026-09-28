# 頂部導覽列日／夜一致、會員區評論不跳公開頁、導覽列「設定」換成 MCP 接入中心

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- `frontend/src/styles/35-public-legacy.css`：導覽列的尺寸與排版（`.public-nav-inner` 最大寬度與內距、`.public-brand` 間距、`.public-brand-logo` 52px、`.public-brand-sub` 字級、`.public-nav-links` 間距、`.public-nav-link` 高度、`.theme-toggle` 與 `.public-cta-primary` 最小高度）從 `:root[data-theme="light"]` 規則移到無主題規則；日間規則只留顏色、陰影與背景。
- `frontend/src/App.jsx`：登入後的 `/reviews` 不再包在 `PublicLayout`，改在會員區顯示（會員導覽列、無公開頁尾，網址不變）；未登入仍是公開頁版型。
- `frontend/src/features/account/TopNav.jsx`：會員導覽列「設定」換成「MCP 接入中心」（`/mcp`）；帳號設定仍由右側帳號選單進入。
- `frontend/src/components/navigation/NavActions.jsx`：移除帳號選單中重複的「MCP 接入中心」項目（入口已在導覽列）。
- `frontend/CLAUDE.md`：導覽列尺寸日／夜共用的規則、`/reviews` 與 `/mcp` 路由說明、帳號選單項目。

## 原因
使用者回報：
1. 切換日／夜主題時頂部欄會變動。實測所有頁面（含公開頁）深色 93px、logo 64px，日間 75px、logo 52px，連內距、副標字級、連結高度都不同——這些尺寸只寫在日間規則裡；日間規則的特異度也壓過響應式媒體查詢。統一採日間的緊湊尺寸，會員導覽列 8 個項目也較不易換行。
2. 會員頁面點「評論」會進入公開頁版型（公開導覽列與頁尾），像是離開了會員區。
3. 希望導覽列拿掉「設定」、改放 MCP 接入中心。

## 影響範圍
- 深色主題（預設）的頂部導覽列變矮（93→75px）、logo 64→52px，與日間一致；公開頁與會員頁同時生效。
- 登入後的 `/reviews` 版型改為會員區；未登入訪客看到的評論頁不變。

## 驗證方式
- Playwright 實機量測（本機 runserver＋前端 build）：會員 `/dashboard`、`/scans`、`/settings`、`/mcp`、`/project`、`/reviews` 與未登入 `/project`、`/reviews`，在 1440／900／390px 切換日／夜，導覽列、logo、副標、連結、按鈕的位置、尺寸與字型全部一致（先把滑鼠移開，排除按鈕 hover 上移 1px 的干擾）
- 會員從 Dashboard 點「評論」→ 網址 `/reviews`、無 `.public-shell` 與公開頁尾、導覽列「評論」為作用中；未登入 `/reviews` 仍為公開頁
- 導覽列項目為首頁／Dashboard／掃描／網域驗證／歷史／購點／評論／MCP 接入中心，1600～1180px 皆不換行（75px）；帳號選單為帳號設定／購點與訂閱／登出，可進入 `/settings`
- `npm run lint`、`npm run typecheck`、`npm test`（152 項）、`vite build` 通過
