# AEO 問答頁數字磚統一、資安分析頁類型篩選出口（2026-10-19）

## 審閱結論
- **SEO 分析**：結構（分頁列＋搜尋 → 7 張數字卡 → 優先修復 → 全部問題 → 站台檢查）合理，不動。
- **資安分析**：結構合理；只缺「問題類型」篩選生效時的清除出口（原本只能再點一次卡片）。
- **AEO 問答**：數字列用的是所有專案頁的 `.project-portfolio`（與總覽／頁面／掃描分頁的數字磚不同款），
  AEO 分數只有顏色沒有等級文字（違反「分數一定附數值與等級文字」）；逐題結果面板沒有標題；
  判讀注意事項放在清單之後，看完才知道「無答案」是什麼意思。

## 變更
- `features/projects/ProjectPages.jsx` `ProjectAeoPage`：數字改成 `.project-site-tile`（AEO 分數＋等級、題目＋不計分題數、可回答％＋題數、附原文％、可被引用％）；
  注意事項移到逐題結果之前；逐題結果加標題「逐題結果（N 題）」；移除只剩這裡用的 `scoreToneClass`。
- `features/projects/ProjectSecurityPage.jsx`：資安問題標題列在類型篩選生效時加「顯示全部類型（N）」。
- `93-projects.css`：`.aeo-summary`。文件：`frontend/CLAUDE.md` 路由表 `/projects/:id/aeo` 列。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。請實機看 AEO 數字磚與深色主題。
