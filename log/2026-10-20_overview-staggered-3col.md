# 總覽頁：改回三欄錯開版面（保留問題概況整併面板）

**日期**：2026-10-20（同日 fix-staggered）
**操作者**：Claude

## 變更內容
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectOverviewPage`）：
  - 上一輪把面板改成等寬 grid-2 齊平排列，使用者回饋「越改越醜、太方塊」，要求回到「以前那樣上下有些錯開」的版面。
  - 改回兩列 grid-3（沿用使用者指認的舊版編排）：
    - 第二列 `grid-3 is-wide-first`：各維度評分與趨勢（寬欄）｜問題概況（整併面板）｜網站評分趨勢
    - 第三列 `grid-3`：AEO 問答檢測｜各維度問題的數量｜優先改善建議
  - **保留**上一輪的問題概況整併（問題總數＝環圖中心，不再另立「發現問題總數」數字卡；含可點圖例與「較上次新增／持續／未出現」比較列）。
- `frontend/src/styles/legacy-member/93-projects.css`：
  - `.project-grid-3` 加 `align-items: start`：面板各自依內容高度，不被同列最高者撐平，總覽上下自然錯開（這正是「錯開」的來源）。
  - 重新加回 `.project-grid-3.is-wide-first`（1.25fr／1fr／1fr）——上一輪誤刪。
- `frontend/CLAUDE.md`：路由說明同步新編排與 `align-items: start` 的錯開意圖。

## 原因
使用者比較兩張截圖後明確表示：等寬兩欄的新版太方塊、很醜，想要之前三欄、面板上下錯開的版面。根因是把版面從三欄改成兩欄 grid-2，且 grid 預設 `align-items: stretch` 會把同列面板拉成等高，短面板（環圖）下方留大片空白。改回三欄並讓面板依內容高度排列（`align-items: start`），恢復較密、較有節奏的錯開感，同時不丟失使用者稍早要的「兩面板整併成一個」。

## 影響範圍
- 只動總覽頁與其專用樣式；`.project-grid-3` 僅總覽頁使用（已 grep 確認），加 `align-items: start` 不影響其他頁。
- 問題概況整併、可點圖例、較上次比較、各面板資料欄位全部保留，無後端變更。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning）。
- `npm run typecheck`：clean。
- `npx vitest run src/features/projects/ src/components/projects/`：41 pass。
- 未自動驗證：實際版面需 `build-node22.ps1` 後由 CI 建出；部署後看總覽頁確認三欄錯開、問題概況仍是單一面板。
