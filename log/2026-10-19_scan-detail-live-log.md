# 掃描進行中：執行紀錄移到進度條下方（2026-10-19）

## 問題
`/scans/:id` 進行中時，執行紀錄還是收合放在整頁最底（摘要、檢視器之後），使用者要看即時進度得捲到最下面。

## 變更
- `features/scans/ScanExperience.jsx`：抽出 `ScanLogPanel({ entries, live })`。
  進行中（`live`）：放進 `.scan-report-progress` 進度區塊內、緊接進度條下方，預設展開、標題「即時執行紀錄」、
  每次新紀錄自動捲到最底；完成／失敗／終止：維持原本收合放最後（診斷資料）。
- `styles/legacy-member/94-report-style.css`：`.scan-log-panel.is-live` 上距與較矮的高度（220px）。
- 文件：`frontend/CLAUDE.md` 路由表 `/scans/:scanId` 列。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。雲端無法渲染，請實機看進行中的掃描：紀錄在進度條下方展開且會跟著捲。
