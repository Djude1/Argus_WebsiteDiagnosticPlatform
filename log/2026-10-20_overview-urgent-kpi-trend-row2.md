# 總覽頁：頭條「安全標頭等第」改「高風險問題」、評分趨勢移到第二列

**日期**：2026-10-20（同日 fix-urgent-kpi）
**操作者**：Claude

## 變更內容
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectOverviewPage`）：
  - 頭條第三張由「安全標頭參考等第」（`ObservatoryKpi`，移除）改為「高風險問題」（新 `UrgentIssuesKpi`）：嚴重＋高的數量、紅字（0 時藍字），小字列「嚴重 N、高 N，建議先修這些」，連結到 `issues?severity=critical`（沒有嚴重時 `high`）。安全標頭等第仍在資安分析頁，總覽不再顯示。
  - 「網站評分趨勢」上移到第二列（各維度評分（寬）｜問題概況｜網站評分趨勢），「優先改善建議」下移到第三列（優先改善建議｜各維度問題的數量｜AEO）。
- `frontend/src/features/projects/ProjectPages.test.tsx`：移除 ObservatoryKpi 斷言，新增 `UrgentIssuesKpi` 測試（加總、連結、0 的文案）。
- `frontend/CLAUDE.md`：路由說明同步。

## 原因
使用者看過上一版截圖後指定：安全標頭等第在總覽不夠有用、換成更有用的；評分趨勢要放第二列。頭條列的角色是「現在要先處理什麼」，嚴重＋高的數量比參考等第直接得多，且有可點的下一步。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning）；`npm run typecheck`：clean；`npx vitest run src/features/projects/ src/components/projects/`：43 pass。
- 本機 sqlite ＋ Vite dev server ＋ Playwright 實跑示範專案截圖確認版面（截圖已給使用者，不入 repo）。
