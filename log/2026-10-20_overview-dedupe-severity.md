# 總覽頁去重：發現問題總數卡不再重複嚴重度分布

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- `frontend/src/features/projects/ProjectPages.jsx`（`ProjectOverviewPage`）：
  - 「發現問題總數」卡移除嚴重度數量籤（高／中／低／資訊，原本還漏了「嚴重」、加總對不上總數），改為「查看問題分析 →」連結＋一句「依嚴重度分布見下方圖表」。保留總數與「較上次（新增／持續／未出現（已修好））」。
  - 「問題嚴重程度分布」甜甜圈圖傳入 `issuesPath`。
- `frontend/src/components/projects/DashboardWidgets.jsx`：`SeverityDonut` 新增 `issuesPath` prop，圖例每列在有 issuesPath 時改為 `<Link>`（連到 `?severity=<級>` 的問題分析），把原本總數卡上「點嚴重度籤篩選」的功能移到圖例，單一來源。
- `frontend/src/styles/legacy-member/93-projects.css`：甜甜圈圖例 grid 由 `li` 移到 `.dash-donut-row`（可點、hover 淺底、focus 外框）；新增 `.project-kpi-sub`／`.project-kpi-sub-note`；移除已無人用的 `.project-sev-row`（`.project-sev-count` 問題分析頁仍用，保留）。

## 原因
使用者回報總覽頁「發現問題總數」與「問題嚴重程度分布」兩個面板資訊嚴重重疊——兩者都在列各嚴重度的數量。總數卡的籤還漏了「嚴重」級、加總與總數對不上。改為單一來源：總數卡只講總量與和上次的差異，嚴重度分布（含「嚴重」與百分比、可點篩選）統一由甜甜圈圖負責。

## 影響範圍
- 只動總覽頁與共用的 `SeverityDonut`；`SeverityDonut` 未傳 `issuesPath` 時維持純圖例（非連結），向後相容。
- 「點嚴重度 → 篩選問題分析」的功能保留，移到甜甜圈圖例。

## 驗證方式
- `npm run lint`：0 error（1 個既有無關 warning）。
- `npm run typecheck`：clean。
- `npx vitest run src/components/projects/ src/features/projects/`：41 pass。
- 未自動驗證：實際版面需 `build-node22.ps1` 後由 CI 建出；部署後看總覽頁確認總數卡不再列嚴重度籤、甜甜圈圖例可點跳到對應嚴重度的問題分析。
