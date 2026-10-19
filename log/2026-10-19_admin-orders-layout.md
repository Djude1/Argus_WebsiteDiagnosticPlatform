# 後台訂單頁審閱：兩份資料各自成面板（2026-10-19）

## 問題
`/admin/orders` 是購點訂單與訂閱每期扣款兩份獨立資料疊在一頁，但購點訂單那張表沒有標題：
狀態分段鈕 → 搜尋 → 大表 → 分頁 → 「訂閱每期扣款」面板，讀起來像整頁都是訂單。
訂閱扣款的「結果」欄是純文字「成功／失敗（代碼 訊息）」，與訂單表的狀態徽章不一致。

## 變更
- `AdminOrdersPage.jsx`：購點訂單包成 `admin-panel`，標題列「購點訂單（N）」＋狀態分段鈕同一列，搜尋列、表格、分頁在面板內；
  與下方「訂閱每期扣款」面板對稱。
- `AdminSubscriptionCharges.jsx`：扣款結果改 `admin-order-status` 徽章（成功綠／失敗紅），失敗代碼與訊息改第二行。

## 驗證
`npm run lint`、`npm run typecheck`、`npx vitest run`。
