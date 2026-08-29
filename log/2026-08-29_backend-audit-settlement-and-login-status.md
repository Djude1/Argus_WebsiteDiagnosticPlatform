# 後端稽核：結算失敗誤判與登入狀態碼修正

**日期**：2026-08-29  
**操作者**：Claude

## 變更內容

### 1. `backend/apps/scans/tasks.py` — 結算失敗不再翻掉已完成的掃描
- `run_scan_job()` 收尾處的 `settle_scan_actual()` 例外不再 `raise`。
- 改為捕捉後記錄：`warning_summary["settlement_error"]` 寫入例外類別名、`scan_log` 補一筆 error，掃描維持 `completed`。
- 回傳 dict 新增 `settlement_error` 欄位（成功時為 `None`）。
- 新增 `backend/apps/scans/tests_settlement.py`（2 項測試）鎖定此契約。

### 2. `backend/apps/accounts/views.py` — 登入認證失敗改回 401
- `EmailLoginView` 帳密錯誤由 `400` 改為 `401`；欄位缺漏維持 `400`。
- `backend/apps/accounts/tests.py`：既有斷言 400 → 401，並新增 `test_email_login_missing_field_is_bad_request_not_unauthorized` 鎖定 400/401 分界。

### 3. `backend/apps/scans/tests_process_runner.py` — 修 flaky 測試
- `test_linux_cancel_kills_descendant_that_ignores_sigterm` 的 `/proc/<pid>/stat` 讀取有 TOCTOU 競態，改用 `read_proc_state()` helper 捕捉 `FileNotFoundError` / `ProcessLookupError`。

### 4. `backend/apps/accounts/tests.py` — 修 throttle 計數殘留造成的測試互相干擾
- 四個測試類別（`GoogleLoginTests`、`GoogleLoginConfigTests`、`PasswordResetTokenTests`、`EmailAuthTests`）的 `setUp` 加上 `cache.clear()`。

### 5. 文件同步
- `backend/apps/scans/CLAUDE.md`：Coin 扣點流程補上「結算失敗不得往上拋」規則。
- `backend/apps/accounts/CLAUDE.md`：補上 email-login 的 400/401 分界與前端 401 攔截器不受影響的理由。

## 原因

使用者要求檢查後端運行與邏輯架構，稽核後回報三項問題，使用者指定修其中兩項（1 與 3）。第 4 項是修 3 的過程中被自己的新測試觸發而必須一併處理。

1. **結算失敗誤判**：`settle_scan_actual()` 在 `ScanJob` 已寫成 `completed` 之後才執行。原本的 `raise` 會落到 `run_scan_job` 的通用 `except`，把掃描改成 `failed` 並執行**全額**退款——頁面與 findings 都已寫入 DB，狀態卻變成失敗，退的也不是差額。觸發條件（`CoinWallet.DoesNotExist`、DB 短暫失聯）機率低，但一旦發生資料狀態與計費雙錯。
2. **登入狀態碼**：帳密錯誤與 `DisallowedHost`、CSRF 等設定層錯誤都回 400，線上排查無法從狀態碼分流。2026-08-25 診斷 `ars.clouda.dpdns.org` 登入失敗時就因此繞路。
3. **flaky 測試**：子程序是孤兒，由 init／subreaper 回收，回收可能發生在 `exists()` 與 `read_text()` 之間。已被回收其實比 zombie 更徹底，代表 `_terminate_process_tree` 成功，不該算失敗。
4. **throttle 計數殘留**：`GoogleLoginView` 與 `EmailLoginView` 共用 `throttle_scope = "login"`（10/min），DRF 的 `ScopedRateThrottle` 把計數放在 default cache（LocMemCache），測試程序內不會自動清空。`apps.accounts` 單獨執行原本就會撞 429 而失敗（本次修改前後皆然，已還原驗證）；完整套件原本因耗時久、滑動視窗排空而僥倖通過。**但本次為 400/401 分界新增的測試多吃了一個 login 配額，且 unittest 依類別名排序讓 `EmailAuthTests` 先於 `GoogleLoginTests` 執行，於是完整套件也由綠轉紅**，必須一併修掉。

## 影響範圍

- **掃描結算**：結算失敗時使用者不再獲得全額退款，預扣維持扣除、差額待補結算。這是刻意的取捨——寧可少退也不要錯退，且掃描結果保留可用。需要補結算時可用 `warning_summary["settlement_error"]` 篩出這些 job。
- **前端登入**：不受影響。`frontend/src/api.js:26` 的 401 攔截器以 `url.startsWith("/auth/")` 排除認證端點，不會觸發 refresh 或導向迴圈；`AuthPages.jsx` 只讀 `err.response?.data?.detail`，不判斷狀態碼。已 grep 驗證，無其他呼叫端。
- **`run_scan_job` 回傳值**：新增 `settlement_error` 鍵。已確認無測試對 completed 分支的 dict 做精確相等斷言（cancelled 分支的 `assertEqual(result, {...})` 不受影響）。
- **未動 production code 的部分**：`process_runner.py` 完全沒改，只改測試；`cache.clear()` 也只在測試 `setUp`，不影響正式環境的 throttle 行為。
- **副作用**：`cache.clear()` 會清掉整個 default cache，不只 throttle 計數。這些測試類別沒有依賴其他 cache 資料，但日後若在 accounts 測試引入 cache 相關斷言需留意。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py check` → no issues
- 新測試有效性驗證：`git stash` 掉 `tasks.py` 的修改後重跑 `tests_settlement`，兩項都失敗（舊行為拋 `RuntimeError: 掃描執行失敗。`），確認測試確實鎖得住迴歸。
- flaky 測試：單一測試連跑 5 次、整個模組連跑 3 次、4 個並行加負載 → 全 OK。
- `uv run python backend/manage.py test apps` → Ran 684 tests，OK（skipped=1）
- `uv run python backend/manage.py test apps.accounts` → Ran 19 tests，OK（修正前必失敗）

## 未處理／待決事項

- **稽核第 2 項未修（使用者未指定）**：compose 這套 PostgreSQL 只有 1 個帳號（bootstrap superuser）、`ScanJob` 0 筆，掃描鏈路只有元件層證據（worker ping、Redis、Chromium 可啟動），沒有端到端實跑。preflight 第 4 條要求的「用正常 API 建一筆新掃描驗證」仍待補。
- **同類風險已回頭掃過（無其他待修）**：其餘 throttle scope 逐一核對——`register`（10/hour）與 `password_reset`（5/hour）額度最緊，但兩者都在 `apps.accounts` 內，已被本次的 per-test `cache.clear()` 覆蓋；`scan_create`（30/hour，測試中 8 次呼叫，且多數測試各自建立使用者故 bucket key 不同）與 `insights`（30/hour，測試中 5 次呼叫）餘裕充足。目前不需再動。
