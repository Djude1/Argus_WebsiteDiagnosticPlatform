# 總覽頁：優先改善建議五項撐開、評分趨勢往上加高 30px

**日期**：2026-10-20（同日 fix-prio-spread）
**操作者**：Claude

## 變更內容
- `frontend/src/styles/legacy-member/93-projects.css`（≥1100px）：
  - `.ov-right .ov-prio` 的 flex-basis 改 `calc(var(--ov-prio-h) - 30px)`（比問題概況矮 30px），並改 flex 直向；`.project-priority-list` `flex: 1` ＋ `space-evenly`，五個建議項目平均撐開填滿面板、下方不留白。
  - 評分趨勢因此往上多 30px（右欄總高固定）。
- `frontend/CLAUDE.md`：路由說明同步。

## 原因
使用者：優先改善建議的五項要展開填滿、面板下方不留白；網站評分趨勢面板往上變高一點。兩個面板共用右欄總高，趨勢往上長就得吃優先建議的高度；已向使用者確認「往上加高 30px、優先改善建議相應縮短、不再與問題概況等高」。

## 驗證方式
- `npm run lint`：0 error；`npx vitest run src/features/projects/`：38 pass。
- 本機 Vite dev server ＋ Playwright 量測：優先改善建議 279px（＝308.5 − 30）、評分趨勢 234.5px（＝204.5 ＋ 30）；截圖已給使用者，不入 repo。
