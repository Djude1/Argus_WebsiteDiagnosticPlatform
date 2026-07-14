# K8s Kali SQLmap 實作紀錄

**日期**：2026-07-14
**操作者**：Codex

## Task 1：安全結果契約、遮罩與設定

### 變更內容

- 新增 `backend/apps/scans/security/kali_contracts.py`，定義 SQLmap 目標、結果、執行結果、保留結果與 executor protocol。
- 新增嚴格的 runner JSON 邊界：限制 16384 bytes、固定 schema 與欄位、驗證索引與安全字元，並將不可信資料轉成 `KaliResult`。
- 新增 URL query value 遮罩；保留 origin、path 與 query key，移除 fragment，避免完整參數值進入證據或紀錄。
- `KaliResult.as_dict()` 固定輸出既有八個欄位，且永不回傳 raw stdout；本 Task 不加入 `correlation_id` 或 `tool_version`。
- 新增 Kali backend、namespace、runner image、SQLmap 版本、timeout、鎖、預算、TTL、結果大小與 Redis URL 設定；功能及 backend 預設維持停用。
- 更新 `.env.example`，列出可由環境設定的 Kali 安全預設值。
- 新增 `backend/apps/scans/tests_kali_contracts.py`，鎖定 URL 遮罩、stdout 隔離及 runner payload 拒絕行為。

### 原因

在加入 Docker 與 Kubernetes executor 前，先建立兩者共用且可驗證的安全結果契約，避免不可信 runner 輸出、URL query value 或 raw SQLmap stdout 被持久化或傳遞到後續流程；同時讓尚未完成 Secret at-rest encryption 的環境維持 disabled-by-default。

### 影響範圍

- 影響 `scans.security` 後續 Kali policy 與 executor 的共用型別及 parser 邊界。
- 影響 Django Kali 設定與 `.env.example` 範例；無 migration、套件、billing、前端或既有 scanner 行為變更。
- 本 Task 尚未把新契約接入既有 `kali_tools.py`；後續 Tasks 依計畫完成 facade 與 executor 整合。

### 驗證方式

- RED：`uv run python backend/manage.py test apps.scans.tests_kali_contracts -v 2` → exit 1，因 `apps.scans.security.kali_contracts` 尚不存在而出現預期 `ModuleNotFoundError`。
- GREEN：同一 focused test 命令 → 3 tests，全部通過。
- Ruff 首跑：指定三檔檢查發現一項 `UP035`；最小修正 `Sequence` import 後重跑通過。
- 指定 Ruff：`uv run ruff check backend/apps/scans/security/kali_contracts.py backend/apps/scans/tests_kali_contracts.py backend/config/settings.py` → `All checks passed!`。
- Django：`uv run --frozen python backend/manage.py check` → 0 issues。
- 相關回歸：`uv run --frozen python backend/manage.py test apps.scans.tests_kali_contracts apps.scans.tests_kali_tools -v 1` → 23 tests，全部通過。
- 全 backend Ruff：`uv run --frozen ruff check backend` → `All checks passed!`。

## Task 1 review fix：嚴格 schema 型別與 parser 覆蓋

### 變更內容

- `parse_runner_result()` 現在要求 `schema_version` 的實際型別為 `int` 且值為 1，拒絕 JSON `true` 與 `1.0`。
- contract tests 新增合法 payload 映射、有效 JSON 的 16384/16385 bytes 邊界，以及 UTF-8、schema/tool、result 欄位、索引完整性／重複／越界、bool/int 型別、安全字元與 technique allowlist 覆蓋。
- 所有拒絕測試均斷言結構化錯誤碼，避免因非預期解析錯誤而假綠。

### 原因

review 發現 Python 的相等比較會讓 `True == 1` 與 `1.0 == 1` 成立，且原始測試未完整證明不可信 runner payload 的每一道契約邊界。

### 影響範圍

- 僅收緊 SQLmap runner schema 驗證與補強既有 contract tests；沒有改變結果固定 keys、settings、facade 或其他 Task 行為。

### 驗證方式

- RED：focused suite 共 4 tests；新增 schema test 的 `True`、`1.0` 兩個 subtests 皆因未拋出 `KaliResultContractError` 而失敗。
- 最小修正 GREEN：同一 focused suite 4 tests 全部通過。
- 完整 focused suite：`uv run --frozen python backend/manage.py test apps.scans.tests_kali_contracts -v 2` → 15 tests，全部通過。
- 指定 Ruff：`uv run --frozen ruff check backend/apps/scans/security/kali_contracts.py backend/apps/scans/tests_kali_contracts.py backend/config/settings.py` → `All checks passed!`。

## Task 2：原子授權、deadline、去重與目標預算

### 變更內容

- 新增共用 `reserve_sqlmap_targets()`，依固定順序檢查 Kali 開關、backend、ScanJob、取消、
  active mode、主動測試授權、公網、同源與 query parameter。
- 以標準化 URL 的 SHA-256 指紋送入 Redis；Redis 僅使用每個 scan 的 `targets` 與
  `started` 兩個 key。
- 使用 Redis server `TIME` 與 Lua 原子套用 900 秒 deadline、最多 3 個不同目標、去重與
  86400 秒 TTL，並映射固定結構化錯誤碼。
- 新增 unit policy matrix 與隔離 Redis DB 的雙執行緒 race 測試；取消案例透過既有 Cancel
  API 寫入真實 DB 狀態，不直接更新 status。
- Quality Gate backend job 新增 `redis:7.4.2-alpine` service，僅設定
  `KALI_TEST_REDIS_URL` 指向 DB 15，不改 Django cache 或 Celery broker 預設。

### 原因

AI tool call 與規則式 fallback 必須共用同一個 pre-Redis 授權及目標預算，避免兩個 worker
同時對同一 URL 重複執行 SQLmap，並確保每個 scan 的執行時間與目標數均有硬上限。

### 影響範圍

- 只新增 Kali policy 與其測試，並調整 backend Quality Gate 的隔離測試服務。
- Redis 不保存完整 target URL 或 query value；production 呼叫端整合由後續 Task 負責。
- 真 Redis 測試未設定 `KALI_TEST_REDIS_URL` 時會 skip；提供 URL 時要求使用非 0 的隔離 DB，
  且 setup／teardown 只 `flushdb` 該 DB。

### RED / GREEN 與驗證

- RED：`uv run --frozen python backend/manage.py test apps.scans.tests_kali_policy -v 2`
  因 `apps.scans.security.kali_policy` 尚不存在而失敗，符合預期。
- GREEN：同一 focused unit command 共 9 tests，全部通過。
- 真 Redis race：以一次性 `redis:7.4.2-alpine` 容器映射 localhost 6389、隔離 DB 15，
  `apps.scans.tests_kali_policy_redis` 共 1 test 通過；兩個 thread 中恰好一個保留共享指紋。
- Race 首跑揭露全域 `socket.getaddrinfo` mock 也攔截 Redis localhost；將 mock 縮小到
  `services._resolve_host_ips` 後通過，兩次容器皆由 `finally` 停止並移除。
- `uv run --frozen ruff check` 檢查三個 Task 2 Python 檔，全部通過。
