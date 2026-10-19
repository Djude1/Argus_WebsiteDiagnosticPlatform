# 所有專案頁重排：主要動作上移、數字磚統一、工具列併入清單卡（2026-10-19）

## 問題
`/projects`：頁面唯一主要動作「新增網站專案」跟排序籤、搜尋擠在數字列與表格中間的工具列，而不是像其他分頁放頁首右側；
跨網站數字列用的是獨有的 `.project-portfolio`（與各分頁 `.project-site-tile` 不同款），平均分數沒有等級文字；
表格沒有標題；搜尋沒結果的訊息掉在卡片外面、沒有清除出口。

## 變更（`features/projects/ProjectWorkspace.jsx`）
- 「新增網站專案」移到 `project-page-head` 右側。
- `PortfolioSummary` 改用 `.project-site-tile`：網站（未完成掃描數）、平均分數＋等級、低於 60 分（紅／綠）、目前問題、掃描進行中。
- `ProjectTable` 外層改 `section.panel`，接受 `tools`（標題列）與 `children`（空狀態）；水平捲動只包表格。
  清單卡標題「網站清單（N / 總數）」＋搜尋同一列、排序籤下一列；搜不到附「清除搜尋」。
- `93-projects.css`：刪 `.project-portfolio*`、`.project-list-toolbar`、`.project-list-search`（已無使用），新增 `.projects-summary`、`.projects-list-head`；
  `97-responsive.css` 對應改名。
- 文件：`frontend/CLAUDE.md` 路由表 `/projects` 列。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。請實機看數字磚、1100px 以下表格改區塊時標題列的換行、深色主題。
