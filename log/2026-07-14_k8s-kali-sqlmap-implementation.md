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

## Task 3：Facade dispatch 與 Docker 兼容性

### 變更內容

- `backend/apps/scans/security/kali_tools.py` 改寫 facade：
  - `run_sqlmap()` 一律 `reserve_sqlmap_targets(max_count=1)`，再依
    `_executor_for_backend()` 派發；不再自做三重鎖或直接呼叫 docker。
  - 新增 `run_sqlmap_batch()`：reserve `max_count = min(max_targets, 3)`，每個 admitted
    target 執行一次；若 executor 結果數與目標數不符，所有 admitted target 換成
    `runner_failed` `KaliResult`。
  - 新增 `DockerSqlmapExecutor`：raw stdout 只在 process 內解析，回傳 `KaliResult`
    （`stdout=""`），`evidence_summary` 限 `parameter` / `techniques` / `dbms` /
    `ARGUS_KALI_SQLMAP_VERSION`；單一 target 失敗只影響自身，不中斷 batch。
  - 新增 `_executor_for_backend()`：`docker`→`DockerSqlmapExecutor`，
    `kubernetes`→lazy import `KubernetesSqlmapExecutor`（Task 4 引入），未知→None。
  - `validate_findings_with_kali()` 改為呼叫 `run_sqlmap_batch` 一次，只信任
    `result.confirmed`；description 中的 URL 經 `redact_url_query_values` 遮罩 query
    value；Finding `evidence_json` 只放 `evidence_summary`，不放 raw stdout；
    `ScanCancelled` 原樣重拋，其餘例外 silent-fail。
  - `run_metasploit()` 新增 backend gate：非 `docker` backend 一律回
    `blocked_reason=tool_not_supported_by_backend`，不呼叫 docker。
  - 保留 `_stdout_indicates_sqli()` 與 `run_sqlmap()` 的 dict 形狀（含 `ok` /
    `blocked_reason` / `stdout` / `error` / `confirmed` / `evidence_summary`），
    讓尚未遷移的 `agent/tools.py` `probe_sql_injection` 與其 mock-based 測試不破壞。
- `backend/apps/scans/tests_kali_tools.py` 全面改寫，圍繞加法式安全契約：
  DockerSqlmapExecutor（不外露 raw、target 失敗不中斷、clean stdout 不確認）、
  run_sqlmap（reserve max_count=1、blocked 原因傳遞）、run_sqlmap_batch（預算、
  count mismatch→runner_failed、blocked 短路）、metasploit backend gate（kubernetes
  與未知 backend 都擋）、validate_findings_with_kali（只信任 confirmed、query value
  遮罩、evidence_json 只放 evidence_summary、ScanCancelled 重拋、其他例外 silent-fail）。
  保留 `TestDockerExecProxy`（egress proxy 傳遞）與 `TestKaliOwaspMapping`（A03/CWE-89）。
- `docker-compose.attack.yml`：worker environment 明確加上
  `ARGUS_KALI_BACKEND: "docker"`（settings 預設為 `"disabled"`，未疊加本 override 不會
  啟用）；Docker socket mount 仍只保留在本 override。

### 原因

Task 1 / Task 2 已建立安全結果契約與原子預算，但既有 Docker facade 仍直接呼叫 docker
並把 raw stdout 寫入 Finding，等同讓不可信輸出繞過契約。Task 3 把 facade 接到
`reserve_sqlmap_targets()` 與 backend dispatcher（DockerSqlmapExecutor），確保所有
持久化內容皆經遮罩、每個 scan 有硬上限的目標預算，並保留 attack compose 的隔離展示。

### 影響範圍

- 接線：`scans.tasks` 仍透過 `validate_findings_with_kali` 呼叫；`agent.tools` 仍透過
  `run_sqlmap` + `_stdout_indicates_sqli` 呼叫——兩者對外 API 形狀不變。
- 行為差異：production 端 `agent.tools.probe_sql_injection` 因新的 `run_sqlmap` 一律
  回 `stdout=""`，將不再經 `_stdout_indicates_sqli` 自行確認；該路徑需後續 Task 改用
  `confirmed` / `evidence_summary`（agent 預設關閉，影響可控）。
- 不變：base `docker-compose.yml` 不含任何 `ARGUS_KALI_*` env 或 docker.sock；
  Kali 主動驗證仍預設停用；三重鎖改由 `reserve_sqlmap_targets` 統一把關。
- Kubernetes executor（`kali_kubernetes.KubernetesSqlmapExecutor`）尚未存在；於 Task 4
  接入前， `_executor_for_backend()` 在 `kubernetes` backend 下的 lazy import 會在實際
  使用時 `ImportError`——屬後續 Task 範圍。

### RED / GREEN 與驗證

- RED：`uv run --frozen python backend/manage.py test apps.scans.tests_kali_tools -v 2`
  → 23 tests，18 errors（`DockerSqlmapExecutor` / `run_sqlmap_batch` /
  `_executor_for_backend` 尚不存在；`metasploit` backend gate 未實作）。
- GREEN：同一 focused command → 23 tests，全部通過。
- 回歸：`apps.scans.tests_kali_contracts apps.scans.tests_kali_policy
  apps.scans.tests_kali_tools` → 47 tests，全部通過。
- 相鄰模組：`apps.agent` 全 suite → 30 tests，全部通過（`_stdout_indicates_sqli`
  與 mock-based `run_sqlmap` 契約保留）。
- Django check：`uv run --frozen python backend/manage.py check` → 0 issues。
- 指定 Ruff：`uv run --frozen ruff check backend/apps/scans/security/kali_tools.py
  backend/apps/scans/tests_kali_tools.py` → `All checks passed!`。
- Compose：`docker compose -f docker-compose.yml -f docker-compose.attack.yml config`
  → worker environment 含 `ARGUS_KALI_BACKEND: docker`、`ARGUS_KALI_CONTAINER`、
  `ARGUS_KALI_ENABLED: "true"`，且 docker.sock mount 只在 attack override 出現；
  base `docker-compose.yml` 無任何 `ARGUS_KALI_*` env 或 docker.sock。

## Task 3 review fix：fallback query 篩選與 blocked audit log

### 變更內容

- **Finding 1（fallback 候選未先挑 query URL）**：`validate_findings_with_kali()`
  在呼叫 `run_sqlmap_batch()` 前，先以「URL 含 `?` 與 `=`」粗篩出帶 query 的候選；
  沒有任何帶 query 候選時直接 `return []`，不呼叫 batch。policy 仍會對每個 admitted
  target 再做 same-origin/public/query 檢查；query value 不被此層記錄或保存。
- **Finding 2（blocked facade branch 缺安全 audit log）**：新增私有 helper
  `_log_kali_decision(scan_job_id, reason, *, level="info")`，固定輸出
  `f"Kali sqlmap 已略過（{reason}）"`。`run_sqlmap()` 與 `run_sqlmap_batch()` 在
  `outcome.blocked_reason`、`not outcome.targets`、`executor is None` 三個 blocked
  branch 都各呼叫一次；`backend_misconfigured` 走 `level="warn"`。helper 只接受固定
  structured reason 列舉字串，呼叫端不傳 URL / query value / raw stdout / exception
  body；policy public interface 未改。
- 對應新增測試：`test_filters_to_query_candidates_before_batch`、
  `test_no_query_candidates_does_not_call_batch`、
  TestRunSqlmap 的 `test_blocked_reservation_writes_safe_audit_log` /
  `test_backend_misconfigured_writes_safe_audit_log`、TestRunSqlmapBatch 的
  `test_batch_blocked_reservation_writes_safe_audit_log` /
  `test_batch_backend_misconfigured_writes_safe_audit_log`，並以共用
  `_assert_safe_audit()` 驗證文案不含目標 URL 與 query value（`secret-value`）。

### 原因

reviewer 指出兩項 Important 缺陷：(1) 真實 caller 傳入完整 crawl-order URL list，
入口頁（無 query）排第一筆會讓 policy 整批回 `no_query_parameter`，後續合法 query URL
永遠不執行；(2) 模組 docstring 與 `security/CLAUDE.md` 明定所有 Kali 呼叫（含被擋）
都需 `append_log`，但 facade 的 blocked / zero-admitted / backend-misconfigured 分支
直接 return，缺 audit trail。

### 影響範圍

- `tasks.py` 透過 `validate_findings_with_kali` 呼叫的路徑：現在會先在 facade 粗篩
  query URL，避免入口頁讓整批被擋；policy 的 same-origin/public/query 守門不變。
- scan_log 在 Kali 全域關閉、未授權、backend 未設定、預算耗盡等情境都會多一筆安全
  reason 文字記錄，不增加任何 URL / query value / 機密外洩面。
- 不影響：agent 路徑（仍是 mock-based 測試 + 既有 dict 契約）、Compose、其他 scanner。

### RED / GREEN 與驗證

- **Finding 1 RED**：focused 2 tests
  （`TestValidateFindingsWithKali.test_filters_to_query_candidates_before_batch`、
  `test_no_query_candidates_does_not_call_batch`）→ 2 failures；前者 batch 收到
  完整 4 URL list 而非 2 個 query URL，後者 batch 仍被呼叫一次。
- **Finding 1 GREEN**：focused → 2 tests 通過。
- **Finding 2 RED**：focused 4 tests（單筆 + batch 各 2 個 blocked branch）→
  4 failures，`append_log` 被呼叫 0 次。
- **Finding 2 GREEN**：focused → 4 tests 通過；`_assert_safe_audit` 確認文案不含
  `secret-value` 與 `target.local` / `t.local`。
- **完整 Task 3 suite**：
  `apps.scans.tests_kali_tools` → 29 tests，全部通過。
- **Task 1/2/3 + agent 回歸**：
  `apps.scans.tests_kali_contracts apps.scans.tests_kali_policy
  apps.scans.tests_kali_tools apps.agent` → 83 tests，全部通過。
- **Ruff**：`uv run --frozen ruff check backend/apps/scans/security/kali_tools.py
  backend/apps/scans/tests_kali_tools.py` → `All checks passed!`。
- **Django check**：`uv run --frozen python backend/manage.py check` → 0 issues。
- **Compose 未變動**：引用前述 Step 6 Compose config 證據，不重跑。
