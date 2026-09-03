# 修掉兩個 P0：掃描卡住不回收、完全沒有 LOGGING

**日期**：2026-09-03
**操作者**：Claude
**背景**：這兩項在 2026-08-30 的後端功能性稽核就列為 P0，一直沒修。使用者確認先處理。

## 1. worker 被砍時掃描永久卡住、預扣點數不退

### 問題

`run_scan_job` 只防得住三種「Python 層還跑得到 handler」的死法：`ScanCancelled`、`SoftTimeLimitExceeded`、一般例外。worker pod 被 rollout／OOM／節點驅逐砍掉時是 **SIGKILL，什麼 handler 都不會執行**，於是 `ScanJob` 永遠停在 `crawling`／`scanning`，`hold_for_scan` 扣的 coin 永遠不退。

**使用者實際遇過一次**（掃描卡 95 分鐘），而且**每次部署都會重新觸發**——這幾天推了 7 版。

也不能靠 Celery 的 `acks_late` 重投解決：`run_scan_job` 入口的 CAS 是 `filter(status=QUEUED).update(...)`，重投時狀態已是 `crawling`，只會直接 return。冪等保護反而讓重試變成空轉。

### 三道防線

| 防線 | 擋什麼 |
|---|---|
| `terminationGracePeriodSeconds: 3600`（worker） | **正常 rollout 不再砍掉進行中的掃描**。預設只有 30 秒，但一次掃描要好幾分鐘 |
| `tasks.reap_stale_scans()` | OOM、節點故障這類 grace period 擋不住的 |
| `CronJob/reap-stale-scans`（每 15 分鐘） | 定期執行 |

判斷依據是「開始多久了」而不是心跳：**超過 `CELERY_TASK_TIME_LIMIT` 還在非終態，代表連 Celery 的 hard limit 都沒能殺掉它，任務必然已經不在了**。用 `started_at`，從未被取件（`started_at` 為 None）則退回 `created_at`。

單筆收斂走 CAS 更新，萬一與還活著的 worker 撞上只有一邊會贏；批次中一筆失敗不會讓其餘卡住的掃描繼續卡著。

### 為什麼用 CronJob 而不是 Celery beat

專案目前沒有 beat，為一支維護作業多開一個常駐程序不划算；而且 **worker 全掛時 CronJob 仍跑得動**——正好是最需要它的時候。`concurrencyPolicy: Forbid`：重疊執行沒有好處，只會讓兩個程序搶同一批列。

新增 `manage.py reap_stale_scans`，CronJob 呼叫它。

### 測試（`tests_stale_scan_reaper.py`，7 項）
超時的非終態掃描被收斂並退款、還在時限內的不被誤殺、已完成的不被碰、從未取件的 queued 也回收、**重跑不重複退款**（回收會週期執行，退錯錢比不退更糟）、錯誤訊息說得清楚、一筆失敗不影響其他。

## 2. 完全沒有 LOGGING 設定

`settings.py` 原本 0 處 LOGGING。掃描失敗時 DB 只留下 `掃描執行失敗 [analysis:AttributeError]`——**只有例外類別名，沒有 stack**。這幾天追截圖消失、SEO 不見、CI 掛掉，每一次都只能靠猜，就是因為這個。

- `settings.py` 新增 LOGGING：輸出 stdout（K8s 與 compose 都從那裡收，寫檔還要處理輪替與磁碟），等級由 `DJANGO_LOG_LEVEL` 控制、SQL log 另由 `DJANGO_SQL_LOG_LEVEL` 控制（預設 WARNING，否則會把 log 淹掉）。
- `tasks.py` **11 處**吞例外的地方補上 `logger.exception`。**使用者看到的 `append_log` 訊息完全不變**，只是多留一份帶 traceback 的紀錄。

設定裡明確註記：**任何 log 都不得印出 Secret／Token／密碼／`.env` 內容**，呼叫端只記錄鍵名與布林結果。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python -m unittest discover -s tests` → **Ran 38 tests，OK**（含 2 個新的部署契約測試）
- `uv run python backend/manage.py test apps` → **Ran 805 tests，OK（skipped=1）**（前次 798，+7）
- LOGGING 實測：`logging.getLogger("apps.scans.tasks").warning(...)` 確實輸出 `[時間] WARNING apps.scans.tasks: ...`
- **本機安裝 kubectl 實際渲染 kustomize**，確認 CronJob 的 image 會被改寫成 `sha-c16bf73` 而非 `:latest`——那支作業會動到退款，image 版本不該用猜的。

## 新增的部署契約測試（`tests/test_k8s_runtime_commands.py`）
worker 的 `terminationGracePeriodSeconds` 必須明確設定且 ≥ 600；回收 CronJob 必須存在、命令正確、`concurrencyPolicy` 為 `Forbid`。

## 未處理／待決事項

- **既有卡住的掃描**：這次修正對「已經卡在那裡」的舊資料同樣有效（CronJob 一跑就會收斂並退款），但**正式站要等這版部署後才會開始清**。
- `cleanup_reports` / `cleanup_screenshots` 仍未排程——現在有了 CronJob 的樣板，可以照抄。
- 其餘既有項目不變：報告快取無版本概念、finding 列表只顯示 100 筆、「0 個 finding = 100 分」、`argus_report_module/` 未納入版控、`.docx` 視覺與頁數待人工確認。
