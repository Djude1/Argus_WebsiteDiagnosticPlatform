# 總覽頁：優先改善建議與問題概況等高

**日期**：2026-10-20（同日 fix-prio-equal）
**操作者**：Claude

## 變更內容
- `frontend/src/styles/legacy-member/93-projects.css`：`.project-overview-grid` ≥1100px 加 `grid-template-rows: minmax(0,1fr) minmax(0,1fr) auto`——容器高度不定時，兩個 fr 列會一起取內容最高者，第一列（優先改善建議）因此與第二列（問題概況）等高；`.ov-prio` 改 flex 直向，`.project-priority-list` 以 `space-evenly` 把五個項目撐開填滿，不堆在上面留空。
- `frontend/CLAUDE.md`：路由說明同步。

## 原因
使用者要求優先改善建議面板高度與問題概況一致。兩者在不同列，只能讓兩列等高；第一列的其他卡（綜合評分、效能、最近一次掃描）會跟著變高、下方留白，是這個要求的必然代價，已在回覆中說明。

## 驗證方式
- `npm run lint`：0 error；`npx vitest run src/features/projects/`：38 pass。
- 本機 Vite dev server ＋ Playwright 實跑示範專案截圖確認（截圖已給使用者，不入 repo）。
