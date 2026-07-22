# 本機掃描排程與資料庫分流修復

**日期**：2026-07-22
**操作者**：Codex

## 變更內容

- 讓 Django 載入 `config.celery` 的專案 app，確保 scan task 套用 eager／broker 設定。
- 新增 enqueue 前失敗的狀態與計費補償：工作改為 `failed`、預扣 coin 全額退款，API 回 503 且不洩漏底層例外。
- 處理 broker 結果不確定的競態：worker 已開始時保留工作與預扣，不誤報退款；掃描失敗對外只保存固定訊息，並明確要求掃描 API 認證。
- 移除 `.env.example` 的相對 SQLite URL；本機統一使用 `backend/db.sqlite3`，Docker 仍由 Compose 注入 PostgreSQL URL。
- 修復三筆從未開始的孤兒掃描：repo 根目錄 DB 一筆、`backend/db.sqlite3` 兩筆，均已標記失敗並退款。
- 新增 Celery 初始化及 enqueue 退款回歸測試，同步環境 preflight、掃描模組規則與長期記憶。

## 原因

本機 `.env` 雖已補齊，但掃描 task 未綁定專案 Celery app，導致 eager 設定沒有套用，建立掃描時仍嘗試連線 Redis result backend 並回 500。相對 SQLite URL 又建立了第二套資料庫，使掃描與 coin 狀態看似消失或長期停在 `queued`。

## 影響範圍

- 本機 Django／Celery eager 掃描建立、ScanJob 狀態與 coin 補償。
- 本機 SQLite 預設位置與開發者環境範例；Docker PostgreSQL 設定不變。
- 切換回 `backend/db.sqlite3` 後，瀏覽器既有 refresh token 可能需要重新登入。

## 驗證方式

- 先執行新回歸測試，確認修正前可重現 Celery 初始化缺口與 enqueue 500。
- `uv run python backend/manage.py test apps.scans`：302 項通過。
- `uv run python backend/manage.py test apps`：476 項通過。
- `uv run ruff check backend/config/__init__.py backend/apps/scans/tasks.py backend/apps/scans/views.py backend/apps/scans/tests_celery_wiring.py`：通過。
- `uv run python backend/manage.py check` 與 `migrate --check`：通過。
- 驗證 scan task 與專案 Celery app 為同一物件、eager 生效，且有效 DB 為 `backend/db.sqlite3`。
- 重啟本機 server 後，`/api/health/live/`、`/api/health/ready/` 與 `/scans` 均回 200。
- Push 前以唯讀 SSH／kubectl 檢查正式 K8s：3/3 nodes Ready、11/11 Pods 健康，web／worker／frontend、Redis、DB、migrate Job 均正常，ArgoCD 為 Synced／Healthy，近期 Warning events 為 0。
- 核對 live ConfigMap／Secret 與 repo 定義：34 個預期鍵全部存在，鍵集合一致；SMTP 帳密雖為空，但目前採 file-based email backend，不影響掃描。
- 正式 bootstrap 管理員帳號存在、啟用、具 staff／superuser 權限，且 K8s Secret 密碼通過正式 DB 的 `check_password()`；帳密與本機不同，全程未輸出任何值或帳號名稱。
- 發現正式 `DJANGO_SECRET_KEY`、`JWT_SECRET_KEY` 與本機相同，應另案輪替以完成環境隔離；`PASSWORD_RESET_TOKEN_PEPPER` 已不同。本次不在未授權下變更正式 Secret。
- 正式 web／worker image 與 GitOps pin 一致，Redis 回 PONG；外網首頁、live、ready 均回 200，近 24 小時指定 Celery retry 與 worker error 關鍵字計數為 0。
