# 恢復綠界 Stage 部署與公網 API

**日期**：2026-08-06
**操作者**：Codex

## 變更內容

- 在正式 `argus` namespace 的既有 `argus-secret` 補入 `ECPAY_MERCHANT_ID`、`ECPAY_HASH_KEY`、`ECPAY_HASH_IV` 三個鍵；值取自綠界官方 Stage 測試資料，未寫入 repo、終端輸出或本檔。
- 僅以 merge patch 新增上述三鍵，原有 16 個 Secret 鍵保持不變；寫入後總鍵數為 19。
- 對 `web`、`worker` Deployment 執行滾動重啟，讓新 Pod 重新載入 Secret；未修改 frontend、Redis、PostgreSQL 或任何業務資料。

## 原因

GitOps 已將 `ARGUS_PAYMENT_MODE` 套用為 `ecpay_test`，但正式 Secret 尚未補齊三個必要綠界設定，導致 Django settings 啟動檢查拋出例外。web 全部進入 `CrashLoopBackOff` 且 Service 沒有 Ready endpoint，公網停在「正在驗證登入狀態」；worker 新副本也無法啟動。

## 影響範圍

- 恢復登入驗證、健康檢查、付款方案與其他依賴 web API 的公網功能。
- 綠界付款模式維持 `ecpay_test`，僅能導向 Stage 測試環境；本次沒有建立訂單或送出付款。
- 回滾時只需移除本次新增的三個 Secret 鍵；若要維持公網可用，必須同步透過 GitOps 將 `ARGUS_PAYMENT_MODE` 回退為 `disabled`，不可只移除 Secret。

## 驗證方式

- Kubernetes API `/readyz` 回覆 `ok`，3/3 節點為 Ready。
- Argo CD Application 為 `Synced`、`Healthy`，revision 與 `ee58d99` 相符。
- `web`、`worker`、`frontend` Deployment 皆為 desired/updated/ready/available `2/2/2/2`，web 與 worker 的 `CrashLoopBackOff` 數量皆為 0。
- 公網首頁、live health、ready health、付款方案 API 分別回覆 HTTP 200；未登入 refresh 端點在約一秒內回覆預期 HTTP 403，不再逾時。
- 付款方案 API 回傳 `payment_mode=ecpay_test`、`purchase_enabled=true`，方案數為 4。
- 以無登入瀏覽器模擬進站，可正常由 `/` 進入 `/project`；「正在驗證登入狀態」不再顯示，購買入口可正常導向登入頁。
