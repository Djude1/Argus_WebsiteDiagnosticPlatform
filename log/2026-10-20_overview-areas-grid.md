# 總覽頁：改成單一 grid-template-areas 版面（拿掉高風險卡、優先建議在右上角）

**日期**：2026-10-20（同日 fix-areas-grid）
**操作者**：Claude

## 變更內容
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectOverviewPage`）：依使用者指定的位置改為一張 `.project-overview-grid`：
  - 第一欄（寬）：`.ov-head`（綜合評分｜行動版效能）→ 各維度評分與趨勢。
  - 第二欄：最近一次掃描（往左移、對齊下方問題概況）→ 問題概況。
  - 第三欄：優先改善建議（放到空出來的右上角，跨前兩列）→ 網站評分趨勢（壓到下方）。
  - 最後一列：各維度問題的數量｜AEO 問答檢測｜網站架構（`SiteSummaryPanel` 新增 `className` prop 以掛上區域）。
  - 移除 `UrgentIssuesKpi`（高風險問題頭條卡）與其匯出、測試。
- `frontend/src/styles/legacy-member/93-projects.css`：移除 `.project-kpis.is-four`，新增 `.project-overview-grid`／`.ov-*`（≥1100px 三欄 `1.25fr 1fr 1fr` 與 areas；窄螢幕單欄依閱讀順序）。
- `frontend/CLAUDE.md`：路由說明改寫為定稿版面，並列出不要再走回頭路的幾個版本。

## 原因
使用者看過上一版截圖後逐項指定：高風險問題卡拿掉；最近一次掃描往左、對齊問題概況；網站評分趨勢往下壓；優先改善建議放到右上角。這些位置用一列一列的 grid 做不到（右上角面板要跨兩列），改成 `grid-template-areas` 一次固定所有面板位置。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning）；`npm run typecheck`：clean；`npx vitest run src/features/projects/ src/components/projects/`：42 pass。
- 本機 sqlite ＋ Vite dev server ＋ Playwright 實跑示範專案截圖確認版面（截圖已給使用者，不入 repo）。
