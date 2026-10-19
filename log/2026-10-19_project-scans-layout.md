# 掃描與報告分頁重排：分數概況與趨勢移到表格上方（2026-10-19）

## 問題
使用者截圖指出 `/projects/:id/scans` 的「分數趨勢」排在掃描紀錄表之後，掃描次數越多就被推得越下面；
折線圖的 viewBox 只有 320×110、`width=100%` 置中，所以在寬卡片裡只佔中間一小塊。

## 變更
- `features/projects/ProjectPages.jsx` `ScanHistoryPanel`：右欄改為
  1. 「分數概況」面板：4 張數字磚（沿用總覽的 `.project-site-tile`，分數色調 ≥80 藍／60–79 琥珀／<60 紅並附等級文字）
     ——最新分數＋等級與完成時間、與上一次相比（評分規則不同時寫「規則已更新」）、完成／總次數、進行中；
     下方分數趨勢圖（`LineChart` 改 640×150、容器 `max-width: 680px`，完成 2 次以上才顯示）。
  2. 「掃描紀錄」表：預設只列最近 `HISTORY_PREVIEW`＝8 筆，超過時底部「顯示更早的 N 次掃描」一鍵展開。
- `styles/legacy-member/93-projects.css`：`.scan-overview-tiles`／`.scan-overview-trend*`／`.scan-history-more`（淺色書寫，深色由建置外掛自動產生）。
- 測試 `ProjectPages.test.tsx`：概況顯示最新分數與等級；11 筆只先列 8 筆、展開後 11 筆且按鈕消失。
- 文件：`frontend/CLAUDE.md` 路由表 `/projects/:id/scans` 列。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`（見 commit 當下輸出）。雲端無法渲染，請使用者實機看：
數字磚在 ≥1280px 四張一列、窄螢幕自動換行；趨勢圖靠左不再浮在中間；超過 8 筆的展開按鈕。
