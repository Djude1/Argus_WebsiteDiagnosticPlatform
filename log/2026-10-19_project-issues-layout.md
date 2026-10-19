# 問題分析頁重排：去掉重複的篩選工具列（2026-10-19）

## 問題
`/projects/:id/issues` 的摘要卡（嚴重度按鈕、維度籤）與下方獨立工具列（維度、嚴重度下拉）是**同一組篩選做了兩次**，
工具列夾在摘要卡與問題表中間，顯示模式與匯出也跟表格分離；篩選到沒結果時沒有「清除篩選」出口。

## 變更
- `features/projects/ProjectPages.jsx` `ProjectIssuesPage`
  - 移除獨立 `issue-toolbar` 面板（維度／嚴重度／變化下拉）；篩選只留摘要卡的嚴重度按鈕與維度籤。
  - 摘要卡的比較文字改成可點籤：「新增 N」「持續 N」＝`?change=` 切換，「本次未出現 N」連到 `#missing`；
    有任一篩選（維度／嚴重度／變化／搜尋）時顯示「清除篩選」。
  - 問題表卡片新增標題列 `issue-table-head`：左「需要處理的問題（N）」（分組模式為「問題清單（N）」）＋搜尋提示，
    右顯示模式分段鈕（列表／依嚴重度分組／依根本原因）＋匯出 CSV。
  - 篩選後沒結果：`issue-table-empty` 附「清除篩選」按鈕。
- `styles/legacy-member/93-projects.css`：`.issue-toolbar*` 換成 `.issue-table-head`／`.issue-table-tools`／`.issue-table-empty`／
  `.issue-compare`／`.project-change-chip.is-button`。
- 文件：`frontend/CLAUDE.md` 路由表 `/projects/:id/issues` 列。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。雲端無法渲染，請實機看：摘要卡籤與表格標題列、窄螢幕換行、深色主題。
