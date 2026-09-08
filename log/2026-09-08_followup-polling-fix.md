# 追問送出後畫面不更新

**日期**：2026-09-08
**操作者**：Claude

## 變更內容

- `RebuildWorkspace.jsx`：追問送出後強制重啟 polling，並加入 30 次的啟動寬限期
- `services.py`：`ask_followup` 開始時清空 `trace`

## 原因

**真實事故**：使用者在正式站 `/scans/50/rebuild/25` 追問「還有什麼繼續需要優化的
地方嗎？幫我優化」，opencode 收到也正常回答了（我從 `.126` 的 session 確認：
第 3 則 assistant 訊息 `finish='stop'`、409 output tokens、有 text part），
但 Argus 頁面完全沒有輸出，思考過程也沒清空。

根因在前端的 polling：

```jsx
if (IN_PROGRESS.has(data.status)) {
  timer = setTimeout(poll, POLL_INTERVAL_MS);   // 只在進行中才排下一次
}
```

追問是**非同步任務**。送出後 worker 還沒撿起來，狀態仍是 `succeeded`，於是
polling 沒有重新啟動——**畫面從此不再更新**。資料其實都寫進 DB 了
（`conversation`、`reply`、`trace` 都有），只是頁面不去讀。

連使用者自己的問題都沒顯示，就是這個原因：`ask_followup` 第一步就把問題寫進
`conversation` 了，但前端沒重新抓。

## 排除過程（記錄下來避免下次重走）

1. 先確認 opencode 端正常 → 是正常的，回答完整
2. 用**同一個 production session** 重現串流 → client 運作正常，8.7 秒收到
   完整事件並正確判定結束。所以不是串流或 `done` 判定的問題
3. 「連自己的問題都沒顯示」→ 指向前端沒重新讀取，而非後端沒寫入

## 影響範圍

- 追問時 `trace` 會被清空。上一輪的推理是「產生優化版」的過程，跟新問題無關，
  留著會讓人以為新回應沒進來。對話本身保存在 `conversation`，不會遺失
- 寬限期 30 次 × 1 秒：worker 在 30 秒內撿起任務就會接上；超過則停止 polling，
  使用者重新整理即可看到結果（資料早就在 DB）

## 驗證方式

- `apps.rebuild` 63 tests OK（新增「追問清空上一輪 trace」1 項）
- 前端 `vite build` 通過
- ruff / check 通過

## 未驗證（需使用者）

- 正式站的追問端到端。前端 polling 的行為沒辦法在這台自動驗證
