# 總覽頁：優先改善建議量測定高＝問題概況，其餘面板還原

**日期**：2026-10-20（同日 fix-prio-measured）
**操作者**：Claude

## 變更內容
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectOverviewPage`）：
  - 撤回上一版「前兩列 1fr 1fr」（第一列三張卡跟著變高，使用者不要）。
  - 右欄改成 `.ov-right`（跨前兩列的 flex 直向）包住優先改善建議與網站評分趨勢。用 `ResizeObserver` 量問題概況面板的 border-box 高度寫進 grid 的 CSS 變數 `--ov-prio-h`（動態值，inline style 例外），優先改善建議以它定 `flex-basis`，評分趨勢 `flex: 1` 吃剩餘高度（＝第一列高度）、壓在下方。
  - `LineChart` 高度還原預設 110。
- `frontend/src/styles/legacy-member/93-projects.css`：areas 改回 `"head scan right" / "cats probs right" / "counts aeo arch"`，移除 `grid-template-rows: 1fr 1fr auto` 與 `space-evenly` 撐開；新增 `.ov-right`、`.ov-right .ov-prio`／`.ov-trend` 的 flex 規則（≥1100px 才定高，窄螢幕單欄自然高度）。
- `frontend/CLAUDE.md`：路由說明同步。

## 原因
使用者明確要求：只讓優先改善建議與問題概況等高、評分趨勢往下壓，其他面板都不要動。兩個面板在不同 grid 列，純 CSS（subgrid／fr）都做不到「只拉這一張」而不動第一列的卡，所以改用量測寫 CSS 變數。

## 驗證方式
- `npm run lint`：0 error；`npm run typecheck`：clean；`npx vitest run src/features/projects/`：38 pass。
- 本機 Vite dev server ＋ Playwright 實跑並用 `getBoundingClientRect` 量測：優先改善建議 309px、問題概況 308.5px、評分趨勢 204.5px＝第一列卡 205px（截圖已給使用者，不入 repo）。
