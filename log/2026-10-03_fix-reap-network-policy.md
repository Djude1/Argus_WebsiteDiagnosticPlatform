# 修復卡住掃描回收 Job 的資料庫連線

**日期**：2026-10-03
**操作者**：Codex

## 變更內容
- 為 `reap-stale-scans` CronJob Pod 加上 `app: reap` label。
- 將 `app: reap` 納入 PostgreSQL 的 Ingress NetworkPolicy 白名單。
- 新增 manifest 契約測試，確保回收 Job 的 label 與資料庫連線授權同步存在。

## 原因
正式叢集的回收 Job 因未被 PostgreSQL Ingress policy 放行而無法連線，重試用盡後顯示 `BackoffLimitExceeded`。

## 影響範圍
- 只影響 `reap-stale-scans` 對 PostgreSQL 的存取。
- 修復後，卡住的掃描可依既有規則被標示失敗並冪等退款。

## 驗證方式
- 執行 K8s manifest 契約測試。
- 部署後以手動建立的 CronJob Job 驗證其完成狀態與日誌。
