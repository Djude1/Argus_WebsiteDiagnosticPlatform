# Celery Task Timeout 保護

## 變更內容

新增 Celery task 雙層 timeout 保護機制，防止掃描任務因爬蟲進入無窮迴圈而永久佔用 worker。

**修改檔案：**
- `backend/config/settings.py`：新增 `CELERY_TASK_TIME_LIMIT`（3600s）和 `CELERY_TASK_SOFT_TIME_LIMIT`（3300s），支援 `.env` 覆寫
- `backend/apps/scans/tasks.py`：import `SoftTimeLimitExceeded`，在 `except` 鏈新增 timeout handler（位於 `ScanCancelled` 與 `Exception` 之間）

## 原因

`run_scan_job` Celery task 原本無任何全局 timeout 保護。若目標網站持續觸發 redirect 或 AJAX 無止境載入，Playwright 單頁 30 秒超時失效後，worker 可能永久卡住。

## 行為說明

| 層級 | 時間 | 行為 |
|---|---|---|
| 軟限（Soft）| 55 分鐘 | 在 task 內 raise `SoftTimeLimitExceeded`，handler 執行清理：寫入 FAILED 狀態、退還 Coin、記錄 log |
| 硬限（Hard）| 60 分鐘 | OS 強制殺掉 worker process（若軟限清理未在 5 分鐘內完成） |

## 影響範圍

- 所有掃描任務：55 分鐘後若仍未完成，強制標記 FAILED 並全額退幣
- 使用者前端：顯示「掃描超時（超過 55 分鐘上限）」錯誤訊息
- 無 backward-incompatible 改動

## 驗證方式

語法驗證：`python -c "import ast; ast.parse(open('backend/apps/scans/tasks.py').read())"` — 通過
整合測試須在 Docker 環境觀察超長掃描的行為（本機缺 Celery worker）
