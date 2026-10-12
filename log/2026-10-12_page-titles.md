# 每個頁面各自的標題

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
- 新增 `frontend/src/shared/documentTitle.ts`：網址對照標題表，格式「頁面主題｜Argus AI網站健檢平台」；`App.jsx` 換頁時設定 `document.title`
- 測試 `documentTitle.test.ts`（公開頁標題不重複、動態網址、沒對到的網址）
- `frontend/CLAUDE.md` 核心檔案表補一列

## 原因
Argus 自掃報告 4.12「多個頁面使用相同的標題」（中風險）：SPA 只有一份 index.html，15 頁 title 全是「Argus AI網站健檢平台」。

## 影響範圍
- 只改瀏覽器分頁與搜尋結果顯示的標題；爬蟲讀執行 JavaScript 後的頁面，所以會判定為各頁不同
- 不執行 JavaScript 的爬蟲仍只看到 index.html 的預設標題（屬 JavaScript 渲染問題，另案處理）
- 新增路由時要在 `TITLES` 補一列

## 驗證方式
- 前端 lint（0 error）、typecheck、`npm test` 286 項通過
- 部署後重新掃描確認 4.12 不再出現
