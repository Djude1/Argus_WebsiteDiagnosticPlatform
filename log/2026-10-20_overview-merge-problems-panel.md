# 總覽頁：發現問題總數與嚴重度分布整併成單一「問題概況」面板並重排版面

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectOverviewPage`）整頁重排：
  - 移除原本獨立的「發現問題總數」數字卡與獨立的「問題嚴重程度分布」面板，整併成**單一「問題概況」面板**：問題總數本來就寫在嚴重度環圖中心（`SeverityDonut`），不再另立大數字卡（這正是使用者指出的重複來源）；面板內＝環圖＋可點圖例（連到依嚴重度篩選的問題分析）＋底部「較上次掃描（新增／持續／未出現（已修好））」比較列＋頁首「查看問題分析 →」。
  - 版面由原本「KPI 三卡 → grid-3（各維度評分｜嚴重度分布｜優先建議）→ grid-3（各維度問題數｜趨勢｜AEO）」重排為清楚的資訊層級：
    1. KPI 兩卡：網站綜合評分｜最近一次掃描
    2. grid-2：**問題概況**（整併面板）｜優先改善建議（問題＋對策成對）
    3. grid-2：各維度評分與趨勢｜網站評分趨勢（分數視角）
    4. grid-2：各維度問題的數量｜AEO 問答檢測（細項）
    5. 效能與網站架構（`SiteSummaryPanel`，全寬）
- `frontend/src/styles/legacy-member/93-projects.css`：
  - 新增 `.project-problems`（直向排列，環圖撐開）與 `.project-problems-changes`（上緣細線分隔的比較列、連結藍字）。
  - 移除我這次改動造成的孤兒：`.project-kpi-sub-note`（原只服務已刪除的問題總數卡）、`.project-grid-3.is-wide-first` 的 `@media` 規則（JSX 已無人使用）。
- `frontend/src/styles/legacy-member/97-responsive.css`：同步移除 `.project-grid-3.is-wide-first` 的窄螢幕選擇器（孤兒）。`.project-grid-2` 預設即單欄、≥1100px 才兩欄，窄螢幕自動堆疊，無需另加規則。
- `frontend/CLAUDE.md`：`/projects/:id` 路由說明更新為新的面板編排（問題概況整併、四列 grid-2 的資訊層級）。

## 原因
使用者回報（延續前一輪）：總覽頁「發現問題總數」卡與「問題嚴重程度分布」面板資訊仍重疊，直接要求「把兩個面板整合成一個，並重新把整頁合理編排」。最根本的重複是「問題總數」同時出現在數字卡與環圖中心，因此整併時把數字卡整張移除、保留環圖作為唯一總數來源，較上次比較列併入同一面板；其餘面板改為成對的 grid-2，讓「問題＋對策」「分數＋趨勢」「維度細項＋AEO」各成一組，資訊層級更清楚。

## 影響範圍
- 只動總覽頁與其專用樣式；`SeverityDonut`、`CategoryScoreList`、`CountBars`、`AeoTiles`、`SiteSummaryPanel` 等共用元件介面未變。
- 所有資料欄位沿用既有（`data.severity_counts`、`data.changes`、`latest.top_actions` 等），無後端變更。
- 「點嚴重度 → 篩選問題分析」「較上次新增／持續／未出現」等既有導流全部保留，只是集中到問題概況面板。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning：AdminPages useEffect deps）。
- `npm run typecheck`：clean。
- `npx vitest run src/components/projects/ src/features/projects/`：41 pass。
- 未自動驗證：實際版面需 `build-node22.ps1` 後由 CI 建出；部署後看總覽頁確認只剩一個問題面板、四列 grid-2 在寬／窄螢幕都正確堆疊。
