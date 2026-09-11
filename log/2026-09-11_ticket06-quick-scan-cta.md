# 票06：quick-scan 導流 CTA 文案

**日期**：2026-09-11  
**操作者**：Claude（ZCode）

## 變更內容
- `frontend/src/features/public/PublicPages.jsx`：quick-scan **結果輸出後**在結果卡底部加導流區塊——「完整掃描可獲得可直接貼上的修正內容」（列四類產物＋付費掃描附贈 1 次產生額度），按鈕導向 `/login` 建立完整掃描。
- `frontend/src/styles.css`：`.insight-upsell` 樣式（深色預設＋`data-theme="light"` 白底覆寫）。

## 原因
spec 票 06（`.scratch/fix-output/issues/06`）：讓免費 quick-scan 使用者知道升級付費能換到什麼；**僅文案與入口導流，不做免費產生**——修正產出對應的是一份付費掃描結果。

## 影響範圍
- 僅 quick-scan 有結果時顯示；測速／釣魚檢測等其他免費工具與未查詢前的空狀態不受影響。

## 驗證方式
- 前端 build（`build-node22.ps1`）成功。
- 手動驗證：`/free-tools` 的單頁快速檢查跑出結果後，結果卡底部出現導流區塊與「登入建立完整掃描」按鈕；按鈕導向登入頁；日／夜主題文字均可讀；CTA 不觸發任何修正產出 API。
