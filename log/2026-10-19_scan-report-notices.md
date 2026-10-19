# 掃描詳情報告頁審閱：提醒集中成一組（2026-10-19）

## 審閱結論
報告頁（標題與分數 → 進度 → 提醒 → 摘要三卡 → AI 解讀 → 檢視器左清單右預覽）是 2026-10-06 重新設計過的版面，
三種寬度的摘要排法、檢視器 sticky 預覽、篩選兩欄都有刻意處理，沒有結構性問題。
唯一的小毛病：失敗／終止、CDN 提醒、部分掃描、首次免費四種提醒各自是一張獨立條，同時出現時每條之間隔一個頁面間距（1rem），
看起來像四個散落的區塊。

## 變更
- `features/scans/ScanExperience.jsx`：四種提醒包進 `.scan-report-notices`，條與條間距 0.5rem；全部沒有時 `:empty` 不佔位。
- `styles/legacy-member/94-report-style.css`：`.scan-report-notices`。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。
