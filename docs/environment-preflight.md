# 環境啟動與掃描 Preflight

這份文件是所有 Agent 與開發者在啟動 Argus、驗證 API／掃描功能，或診斷「掃描卡住」前的共同檢查入口。目的不是假設所有人使用相同單機環境，而是先確認目前採用哪一種執行模式及其必要依賴。2026-07-22 的實際事故、根因、修復與部署證據見 [`backend-scan-queue-incident-2026-07-22.md`](backend-scan-queue-incident-2026-07-22.md)。

## 1. `.env` 完整性

專案根目錄必須有不納入版控的 `.env`。可由 `.env.example` 建立，但「檔案存在」不等於「內容完整」。

```powershell
Test-Path .env
git check-ignore .env
uv run python backend/manage.py check
```

- Django 在任何模式都強制要求 `DJANGO_SECRET_KEY` 與 `PASSWORD_RESET_TOKEN_PEPPER` 非空。
- Docker Compose 另外強制要求 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 非空。
- S3 media、綠界測試金流等功能有各自的條件式必要鍵；啟用前以 `.env.example` 與 `backend/config/settings.py` 為準。
- Agent 只能回報鍵名及「已設定／缺少」狀態，不得顯示、複製或記錄實際值。
- 修改 `.env` 後，必須重啟 Django、Celery worker 或相關容器才會載入新值。

只要 `manage.py check` 尚未通過，就先歸類為本機環境／設定問題，不得宣稱應用程式已完成啟動。

### 本機與 K8s 設定比對

- 不得要求兩個環境的 `.env`／Secret 整份相同。Redis、資料庫 URL、debug、eager、允許網域與瀏覽器路徑本來就應依環境不同；`DJANGO_SECRET_KEY`、`JWT_SECRET_KEY`、`PASSWORD_RESET_TOKEN_PEPPER` 與管理員密碼等安全值也應隔離。
- 比對正式環境時，先核對 live ConfigMap／Secret 的**鍵集合**是否符合 `k8s/01-namespace-config.yaml` 與 `k8s/02-secret.example.yaml`，再對共用鍵只輸出「存在／非空／相同與否」；禁止把值、雜湊、帳號名稱或 token 寫入終端輸出、log、memory 或 commit。
- 第三方 API key 是否共用必須是明確決策；相同只代表使用同一供應商憑證，不代表環境設定正確。
- `ARGUS_BOOTSTRAP_SUPERUSER_*` 只在 bootstrap migration 建立帳號時使用；事後改 Secret 不會更新既有資料庫密碼。正式查核必須同時確認帳號存在、`is_superuser`／`is_staff`／`is_active`，並以 Django `check_password()` 驗證 Secret 內密碼，仍不得輸出帳號或密碼。

## 2. 明確選擇執行模式

| 模式 | 入口 | 必要條件 | 可驗證範圍 |
|---|---|---|---|
| 本機 UI／API | `http://127.0.0.1:8000` | `.env`、migration、`frontend/dist` | 頁面與同步 API；不能證明背景掃描鏈路正常 |
| 本機 eager smoke test | `http://127.0.0.1:8000` | 上述條件，加上 `ARGUS_AUTO_QUEUE_SCANS=true`、`CELERY_TASK_ALWAYS_EAGER=true`、Playwright Chromium | 建立 API 立即回 queued，背景 executor 管理獨立 Python 掃描程序；不等同 Redis／worker 完整整合 |
| Docker 完整整合 | `http://localhost:8080` | Docker Desktop、完整 `.env`、PostgreSQL、Redis、web、worker、frontend | 掃描功能的標準整合驗證環境 |

掃描功能的正式整合驗證一律使用 Docker 模式；本機 eager 只用於快速縮小問題範圍。
為了維持 UI/API 的非同步契約，本機 eager 不會在 `POST /api/scans/` request 內跑完整
掃描；端點建立並預扣成功後先回 `201` 與任務 ID，再由 runserver process 內的單一
背景 executor 啟動獨立 Python 程序。這是為了避免 Windows Playwright 在 web thread
建立事件迴圈時偶發 `WinError 10013`；程序有硬逾時、process-tree 清理與非終態任務
退款收斂。關閉或重啟 runserver 仍可能中斷這類本機任務，所以不能拿它取代
Redis/Celery 的持久佇列。

本機 eager executor 同時只接受一筆 outstanding 掃描；已有工作時再送一筆會回
503、將新建任務標記失敗並冪等全額退款。非 DEBUG 環境若誤開 eager，
`uv run python backend/manage.py check --deploy` 會回報 `scans.E001`。

```powershell
# 本機 UI／API 或 eager smoke test
uv run python backend/manage.py migrate
uv run python backend/manage.py runserver 127.0.0.1:8000

# Docker 完整整合；config 會先檢查 Compose 必要變數
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
```

## 3. 其他常被漏掉的前置條件

| 項目 | 檢查／處理 | 漏掉時常見現象 |
|---|---|---|
| Python 依賴 | `uv sync` | import error、server 無法啟動 |
| Migration | `uv run python backend/manage.py migrate` | API 500、欄位或資料表不存在 |
| 前端 build | `cd frontend ; .\build-node22.ps1 ; cd ..` | 頁面仍是舊版或 `frontend/dist` 不存在；禁止直接 `npm run build` |
| Playwright Chromium | `Test-Path .ms-playwright`；缺少時先設定 `PLAYWRIGHT_BROWSERS_PATH=.ms-playwright` 再安裝 | worker 已取件，但 crawler 啟動瀏覽器失敗 |
| Redis／Celery worker | Docker `ps` 與 worker log，或本機明確使用 eager | 工作長時間停在 `queued` |
| Celery app 初始化 | `config.celery_app`、`config.celery.app` 與 `run_scan_job.app` 必須是同一物件 | `.env` 顯示 eager，但 task 仍連線 Redis backend |
| 建立 API 非同步契約 | eager 模式確認回應先帶 `queued + id`，再由背景 executor 更新狀態 | 表單停在「送出中」直到掃描結束 |
| 資料庫模式 | 本機不設 `DATABASE_URL`，固定使用 `backend/db.sqlite3`；Docker 注入 PostgreSQL URL | 相對 SQLite URL 會產生另一套資料，誤判工作消失或狀態沒更新 |
| 程序重啟 | `.env` 或 worker 設定異動後重啟 | 檔案內容正確，但執行中的程序仍使用舊設定 |

Playwright 必須安裝在專案內，不能污染全域路徑：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH=".ms-playwright"
uv run playwright install chromium
```

## 4. 「掃描卡住」固定診斷順序

1. 確認目前操作的是本機 `8000`（`backend/db.sqlite3`）還是 Docker `8080`（PostgreSQL）。
2. 讓 `uv run python backend/manage.py check` 通過；若剛修改 `.env`，先重啟相關程序。
3. 確認有效的 `ARGUS_AUTO_QUEUE_SCANS` 與 `CELERY_TASK_ALWAYS_EAGER`，並核對 `run_scan_job.app` 是 `config.celery.app`；只輸出布林結果，不輸出 broker URL 或機密。
4. 非 eager 模式確認 Redis 可連線且 Celery worker 存活；Docker 模式執行 `docker compose ... ps` 並查看 `worker` log。
5. 查 `ScanJob.status`、`started_at`、`progress` 與頁面／finding 數量：
   - `queued`、`started_at` 為空、進度為 0：工作尚未被執行，優先查自動排程、broker 與 worker，不是 crawler 掃得慢。
   - 已進入 `crawling`／`analyzing` 才繼續查 Playwright、目標站網路、timeout 與 scanner 例外。
6. 修正設定後，用正常 API／UI 建立一筆新掃描驗證。舊的 `queued` DB 資料列不會自動變成 Celery broker 訊息；不得直接改資料庫狀態假裝重送。確定是 enqueue 前失敗的孤兒工作，只能透過 `tasks.fail_scan_job_before_start()` 結束並觸發冪等退款。

`/api/health/live/` 只證明 web process 可回應，`/api/health/ready/` 主要驗證 web／DB；兩者都不能替代 Redis 與 Celery worker 檢查。

## 5. 問題歸類

| 證據 | 優先歸類 |
|---|---|
| 新程序無法通過 `manage.py check` | `.env`／本機設定 |
| eager 設定為 true，但 `run_scan_job.app` 不是專案 Celery app | 應用程式 Celery 初始化 BUG |
| 工作一直 `queued` 且從未有 `started_at` | 排程設定、Redis 或 worker runtime |
| worker 已取件，卡在 `crawling`／`analyzing` 並有例外 | 應用程式 BUG、外部工具或目標站問題 |
| 同 commit 的 Docker 完整整合通過，部署環境失敗 | CI/CD、映像、K8s secret/config 或部署 runtime |
| 本機與部署的完整整合都能穩定重現 | 應用程式 BUG 或共用設定契約問題 |

沒有上述證據前，不可僅因「等待很久」就判定為 CI/CD 或掃描器 BUG。
