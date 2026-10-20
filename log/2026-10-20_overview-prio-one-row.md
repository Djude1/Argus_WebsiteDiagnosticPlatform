# 總覽頁：優先改善建議縮成一列高、評分趨勢與問題概況同列

**日期**：2026-10-20（同日 fix-prio-one-row）
**操作者**：Claude

## 變更內容
- `frontend/src/styles/legacy-member/93-projects.css`：`.project-overview-grid` 的 areas 由四列改三列——`"head scan prio" / "cats probs trend" / "counts aeo arch"`。優先改善建議只佔第一列（與綜合評分、最近一次掃描等高），網站評分趨勢改與各維度評分、問題概況同列。
- `frontend/src/features/projects/ProjectPages.jsx`：總覽的 `LineChart` 加 `height={200}`（預設 110），讓趨勢圖填滿與問題概況等高的面板，不留大片空白；版面註解同步。
- `frontend/CLAUDE.md`：路由說明同步。

## 原因
使用者：上一版優先改善建議跨兩列，五個項目之下空太多，要縮短、讓第三欄的分界對齊問題概況。改成三列 areas 後，第一列三個面板等高、第二列三個面板等高，欄線與列線都對齊。

## 驗證方式
- `npm run lint`：0 error；`npm run typecheck`：clean；`npx vitest run src/features/projects/ src/components/projects/`：42 pass。
- 本機 Vite dev server ＋ Playwright 實跑示範專案截圖確認（截圖已給使用者，不入 repo）。
