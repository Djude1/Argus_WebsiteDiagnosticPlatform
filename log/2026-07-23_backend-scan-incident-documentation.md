# 後端掃描排程事件文件化

**日期**：2026-07-23
**操作者**：Codex

## 變更內容

- 新增 `docs/backend-scan-queue-incident-2026-07-22.md`，整理掃描長時間停在 `queued` 的症狀、根因、修復、資料處理、測試、CI/CD 與部署驗收。
- 從環境 preflight 與長期記憶加入事件報告連結，讓組員可由既有診斷入口找到完整說明。
- 整理既有掃描恢復紀錄，只保留與後端故障、K8s 健康度和部署判定直接相關的內容。

## 原因

組員需要一份可共同查閱的事件報告，明確區分應用程式 BUG、本機環境路徑問題、CI/CD 與 K8s 基礎設施狀態，避免再次把未取件的 `queued` 工作誤判成掃描器執行緩慢。

## 影響範圍

- 僅修改 Markdown 文件，不變更後端程式、資料庫、K8s manifest 或 runtime 設定。
- 新文件成為本次掃描排程事故的詳細交接來源；日常操作仍以 `docs/environment-preflight.md` 為固定診斷入口。

## 驗證方式

- 對照應用程式修復提交 `3c682f8`、GitOps 提交 `4c79fc8`、目前程式碼與回歸測試逐項核對文件事實。
- 重新執行 Celery wiring 回歸測試、Django system check、migration check 與 Markdown 連結／一致性檢查。
- 檢查 staged allowlist 與敏感字串，確認提交只包含本次後端事件文件與必要索引調整。
