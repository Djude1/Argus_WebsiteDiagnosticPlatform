# 2026-07-22 後端掃描長時間停留 `queued` 事件報告

## 結論摘要

這次「掃描等很久但沒有內容」的主要原因是**後端應用程式 BUG**，不是 K8s 基礎設施故障，也不是掃描器真的執行很慢。

建立掃描時，後端會先建立 `ScanJob` 並預扣 coin，再呼叫 Celery 的 `run_scan_job.delay()`。當時 Django 啟動流程沒有載入專案的 Celery app，`@shared_task` 可能綁到 Celery 預設 app；因此本機即使已設定 eager 模式，task 仍嘗試連線 Redis result backend。排程例外又發生在資料已建立、coin 已預扣之後，舊程式沒有補償處理，最後留下永遠停在 `queued`、`started_at` 為空、進度為 0、沒有 findings 的孤兒工作。

另外，本機曾使用相對 SQLite URL。Django 從不同工作目錄啟動時，會分別建立 repo 根目錄與 `backend/` 下的 `db.sqlite3`，讓使用者、coin 與掃描狀態看起來消失或不一致。這是同次診斷發現的環境路徑問題，但不是 Celery task 沒有正確排程的主因。

修復已由應用程式提交 `3c682f8` 完成，GitOps 提交 `4c79fc8` 已把正式後端映像更新為 `sha-3c682f8`。

## 使用者可見症狀

- 建立掃描後，頁面長時間顯示掃描中，但沒有頁面、finding 或進度內容。
- `ScanJob.status` 持續為 `queued`。
- `started_at` 為空，`progress` 沒有進入 `crawling` 階段。
- 建立 API 可能因 broker／result backend 連線例外回 500。
- 工作建立與 coin 預扣已完成，但 worker 實際上沒有開始處理。
- 從不同目錄啟動本機 Django 時，可能讀到不同 SQLite 檔案，造成帳號、coin 或工作紀錄不一致的假象。

上述狀態和「爬蟲正在慢慢掃」不同：只要 `started_at` 仍為空，就代表 worker 尚未真正開始執行掃描。

## 事件影響

| 範圍 | 影響 |
|---|---|
| 本機 eager 開發模式 | `.env` 的 eager 設定可能沒有套用到 `run_scan_job`，建立掃描時仍誤連 Redis |
| ScanJob 狀態 | 排程失敗後可能遺留永遠 `queued` 的孤兒工作 |
| 計費 | enqueue 前已完成預扣，舊流程沒有在排程失敗時退款 |
| 本機資料一致性 | 相對 SQLite URL 可能產生兩套 DB，導致查到不同使用者、coin 與掃描資料 |
| 正式環境 | 修復部署前使用相同應用程式程式碼，因此可能出現相同排程缺口；當時 K8s、Redis、PostgreSQL 與 worker 本身均健康 |

## 根因分析

### 根因一：專案 Celery app 沒有在 Django 啟動時載入

修復前的 `backend/config/__init__.py` 沒有匯入 `config.celery.app`。`backend/apps/scans/tasks.py` 使用 `@shared_task`，若專案 app 尚未成為 current app，task 可能綁到 Celery 預設 app。

造成的結果是：

1. Django settings 中的 `CELERY_TASK_ALWAYS_EAGER=true` 已成功讀取。
2. 但 `run_scan_job.app` 不是 `config.celery.app`。
3. 呼叫 `run_scan_job.delay()` 時，仍走預設 app 的 broker／result backend 行為。
4. 本機沒有對應 Redis 服務時，建立掃描直接在 enqueue 階段失敗。

因此「`.env` 已放好」仍無法解決問題；設定檔存在不代表 task 已套用到正確 Celery app。

### 根因二：建立工作與排程之間缺少失敗補償

修復前的流程：

```text
POST /api/scans/
  → serializer.save()
  → 建立 ScanJob 並預扣 coin
  → run_scan_job.delay()
  → enqueue 例外
  → API 500，但 ScanJob 仍是 queued，預扣也未退回
```

資料庫交易無法包含外部 broker publish，因此不能只靠把整個 view 包在 transaction 中解決。正確做法是把 enqueue 視為可能失敗的外部副作用，提供明確且冪等的補償流程。

### 根因三：相對 SQLite URL 依啟動目錄解析

`.env` 原先可使用 `DATABASE_URL=sqlite:///db.sqlite3`。這是相對路徑：

- 在 repo 根目錄啟動時，可能使用 `./db.sqlite3`。
- 在 `backend/` 啟動時，可能使用 `backend/db.sqlite3`。

兩個檔案都是合法 SQLite DB，因此不一定會立即報錯，反而容易造成「資料怎麼不見了」或「同一筆掃描狀態不同」的誤判。

## 為什麼不是 CI/CD 或 K8s 故障

在修復 push 前，正式環境已完成以下唯讀檢查：

- 3/3 K8s nodes 為 Ready。
- 11/11 Pods 健康，web、worker、frontend、Redis、DB 與 migration Job 均正常。
- ArgoCD 為 `Synced`／`Healthy`，近期 Warning events 為 0。
- 正式 web／worker image 與當時 GitOps pin 一致。
- Redis 可正常回應，公開首頁、live 與 ready endpoints 均回 HTTP 200。

這些證據表示部署控制面與基礎服務當時可用。正式環境在修復部署前仍有問題，是因為正常運行的 Pod 裡仍是含有 BUG 的應用程式版本；CI/CD 並沒有部署失敗，而是尚未收到修復提交。

修復 push 後，Quality Gate 與 backend image workflow 都成功，GitOps 自動把後端映像 pin 更新為 `sha-3c682f8`。因此本次責任歸類為應用程式 BUG，加上一個本機資料庫路徑陷阱，不歸類為 CI/CD 或 K8s 故障。

## 修復內容

### 1. 強制載入專案 Celery app

`backend/config/__init__.py` 現在匯入並匯出 `celery_app`，確保 Django 啟動時完成 Celery app 初始化。回歸測試會確認：

```text
config.celery_app is config.celery.app
run_scan_job.app is config.celery.app
```

### 2. enqueue 失敗時原子結束工作並退款

`backend/apps/scans/tasks.py` 新增 `fail_scan_job_before_start(scan_job_id)`：

- 使用 `transaction.atomic`。
- 只允許把仍為 `queued` 的工作改為 `failed`。
- 設定完成時間、清空進度並寫入固定錯誤訊息。
- 透過既有 billing service 執行冪等全額退款。
- 若工作已被 worker 取件，不會再改狀態或誤退 coin。

`backend/apps/scans/views.py` 捕捉 `.delay()` 的 enqueue 例外；確定工作仍未開始時，呼叫上述補償函式並回 HTTP 503：

```json
{"detail": "掃描任務暫時無法啟動，預扣 coin 已退回。"}
```

API 不會把 Redis、broker 或內部 runtime 例外直接回傳給前端。

### 3. 保護 broker publish 結果不確定的競態

有一種邊界情況是 broker 已接受工作，但 client 在收到確認前斷線。此時 `.delay()` 可能拋錯，worker 卻已開始執行。

補償函式以 `status=queued` 作為條件更新：

- 若仍為 `queued`：判定尚未取件，安全地標記失敗並退款。
- 若已進入 `crawling` 等狀態：判定 worker 已取得工作，不退款；API 重新讀取當前狀態並回 201。

這避免同一筆掃描同時執行又被退款。

### 4. 統一 worker 執行失敗的對外訊息

掃描器內部失敗時，資料庫與 API 只保留固定訊息「掃描執行失敗。」；底層例外內容不寫入對外欄位或 scan log。原有失敗退款仍透過 billing service 執行。

### 5. 明確要求掃描 API 認證

`ScanJobViewSet.permission_classes` 明確設為 `IsAuthenticated`，避免依賴全域預設而在設定變更後意外放寬掃描資料存取。

### 6. 固定本機 SQLite 位置

`.env.example` 不再提供相對 `DATABASE_URL`。本機未設定 `DATABASE_URL` 時，Django 固定使用 `backend/db.sqlite3`；Docker／K8s 仍由部署環境注入 PostgreSQL URL。

## 舊資料處理

本機共確認三筆從未開始的孤兒掃描：repo 根目錄 SQLite 一筆、`backend/db.sqlite3` 兩筆。它們已透過 `fail_scan_job_before_start()` 標記為 `failed` 並完成冪等退款。

重要限制：修正 `.env`、重啟 server 或部署新版本，都不會讓舊的 `queued` 資料列自動變成 Celery broker 訊息。處理舊工作時必須先確認 `started_at` 為空且狀態仍為 `queued`，再使用既有補償函式；禁止直接更新 DB 狀態或假裝重新送出。

## 驗證結果

### 程式與測試

| 驗證 | 結果 |
|---|---|
| `uv run python backend/manage.py test apps.scans.tests_celery_wiring` | 5 項通過 |
| `uv run python backend/manage.py test apps.scans` | 302 項通過 |
| `uv run python backend/manage.py test apps` | 476 項通過 |
| `uv run ruff check`（本次相關 Python 檔） | 通過 |
| `uv run python backend/manage.py check` | 通過 |
| `uv run python backend/manage.py migrate --check` | 通過 |
| Kustomize manifest build | 通過 |

回歸測試涵蓋：Celery app wiring、明確認證、enqueue 失敗的狀態與退款、重複補償的冪等性、broker publish 不確定競態，以及 worker 例外內容不外洩。

### CI/CD 與部署

- 應用程式修復：[`3c682f8`](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/commit/3c682f870f76c6f29ee3a04daabcf7391377d56f)
- [Quality Gate #35](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/actions/runs/29903182006)：成功。
- [Build & Push Backend Image #18](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/actions/runs/29903182152)：成功。
- GitOps image pin：[`4c79fc8`](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/commit/4c79fc868ec4c20d9398a3993470437302db6825)，後端映像為 `sha-3c682f8`。
- 部署後 ArgoCD 為 `Synced`／`Healthy`，web 與 worker 均完成 rollout。
- 2026-07-23 再次檢查公開首頁、`/api/health/live/`、`/api/health/ready/`，三者均回 HTTP 200。

公開 health endpoints 只能證明 web／DB 基本可用，不能單獨證明 Redis、worker 與完整掃描鏈路。這次另有 K8s worker、Redis 與 rollout 檢查；但文件整理階段沒有再建立正式站的付費／授權掃描，因此「新建一筆正式掃描並完成 findings」仍應作為部署後人工 smoke test。

## 日後遇到相同症狀的固定判斷順序

1. 先確認執行模式：本機 `8000`、Docker `8080` 或正式 K8s。
2. 執行 `uv run python backend/manage.py check`，確認新程序能載入設定。
3. 核對 `run_scan_job.app is config.celery.app`。
4. 本機 eager 模式確認 `CELERY_TASK_ALWAYS_EAGER` 與 `ARGUS_AUTO_QUEUE_SCANS` 的有效布林值。
5. 非 eager 模式確認 Redis 可連線、Celery worker 存活且載入 `run_scan_job`。
6. 查 `ScanJob.status`、`started_at`、`progress`、page 數與 finding 數。
7. 若 `queued`、`started_at` 為空、進度為 0，先查排程鏈路，不要先查 Playwright 或 scanner 效能。
8. 確認本機實際 DB 是 `backend/db.sqlite3`，避免因工作目錄讀到另一套 SQLite。
9. 修正後建立一筆新掃描驗證；舊 `queued` 工作不會自動補送。

完整操作命令與環境分層見 [`environment-preflight.md`](environment-preflight.md)。

## 後續建議

- 部署後用授權測試帳號建立一筆最小頁數掃描，確認狀態可由 `queued → crawling → scanning → completed` 並產生結果。
- 監控長時間 `queued` 且 `started_at` 為空的工作數量，將其作為排程鏈路異常指標。
- 不把 `/api/health/live/` 或 `/api/health/ready/` 當成完整 Celery readiness；排查掃描問題時仍需查看 Redis 與 worker。
- 維持 `tests_celery_wiring.py` 的 wiring 與補償回歸測試，避免未來再次移除 Celery app 初始化。
