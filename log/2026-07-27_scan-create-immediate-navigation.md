# 建立掃描立即導頁

**日期**：2026-07-27<br>
**操作者**：Codex

## 變更內容

- 修正本機 `CELERY_TASK_ALWAYS_EAGER=true` 時，`POST /api/scans/` 在 HTTP request 內同步跑完整掃描，導致表單等待數十秒至數分鐘才取得任務 ID。
- 正式／非 eager 模式維持 broker publish 與投遞失敗 503、退款契約。
- 本機 eager 模式改由單 worker、單 outstanding 背景 executor 執行 task；API 先回 `201`、`queued` 與任務 ID，前端可立即導向掃描詳情頁。
- 背景 task 使用 `apply(throw=True)`，執行前後清理 DB connection 並保證釋放 slot；啟動失敗或 executor 忙碌沿用 `fail_scan_job_before_start()` 的狀態與退款處理。
- 新增 `scans.E001` deployment check，拒絕非 DEBUG 環境誤開 eager。
- 新增 eager API 回應順序、Event barrier 非同步執行、容量上限、背景失敗、DB connection 與 slot 清理測試。

## 原因

前端原本已在建立 API 回傳後立即導頁，但本機 eager 模式讓
`run_scan_job.delay()` 變成同步呼叫，因此真正的等待發生在後端 HTTP request。
掃描時間不應決定建立任務 API 的回應時間。

## 影響範圍

- 影響本機 eager 模式的掃描投遞方式。
- 不修改單頁／全網站範圍、前端路由、API schema、Model、migration、計費金額或正式 Celery worker。
- eager 背景 executor 只供本機 smoke；runserver 重啟可能中斷，正式整合仍使用 Redis/Celery。

## 驗證方式

- `uv run python backend/manage.py test apps.scans.tests_celery_wiring`：16 項全數通過。
- 直打本機建立 API（測試交易回滾）：`201`、`queued`、含任務 ID，約 125ms 回應，背景提交 1 次。
- Event barrier 測試：task 尚未解除阻塞時，HTTP 已先回 `201 queued`。
- `uv run python backend/manage.py test apps`：645 項通過、2 項平台條件略過。
- `uv run ruff check backend`、Django check、migration check、diff check：通過。
- 獨立安全複查：Critical 0、High 0、Medium 0。
