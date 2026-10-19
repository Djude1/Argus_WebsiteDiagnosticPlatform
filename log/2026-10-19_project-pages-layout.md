# 頁面分頁重排：數字磚＋篩選併入清單卡（2026-10-19）

## 問題
`/projects/:id/pages` 的頁數、平均載入、站台層級發現全塞在頁首說明的一句話裡；篩選籤＋搜尋是獨立一張卡夾在頁首與表格之間，
表格本身沒有標題；篩到沒結果沒有清除出口。與同日重排的問題分析頁、掃描與報告頁不一致。

## 變更（`features/projects/ProjectPages.jsx` `ProjectPagesPage`）
- 頁首說明只留一句；數字改成四張 `.project-site-tile`（與總覽同款）：檢查頁數（站台層級發現連到問題分析）、
  平均載入（> 3 秒紅）、有問題的頁面 N / 總頁數、錯誤或被阻擋。
- 篩選籤與搜尋併進表格卡片：標題「頁面清單（N）」（有篩選時「N / 總數」）＋搜尋在同一列，籤在下一列；篩到空附「清除篩選」。
- `93-projects.css`：`.pages-summary`、`.pages-filter-row`、標題列內的 `.project-search`。
- 文件：`frontend/CLAUDE.md` 路由表 `/projects/:id/pages` 列。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`（既有頁面分頁測試涵蓋篩選、搜尋、排序與站台層級發現文字）。請實機看數字磚與深色主題。
