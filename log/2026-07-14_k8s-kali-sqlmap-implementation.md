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
永遠不執行；(2) 模組 docstring 與 `backend/apps/scans/security/CLAUDE.md` 明定所有 Kali 呼叫（含被擋）
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

## Task 4：Kubernetes Job executor

### 變更內容

- 新增 `backend/apps/scans/security/kali_kubernetes.py`：實作 `KubernetesSqlmapExecutor`，在受限的 Kubernetes Job 中執行 SQLmap。
- 使用官方 Python client 35.x 透過 `config.load_incluster_config()` 僅連線 cluster 內 API server；無本機 kubeconfig fallback。
- 以 Redis Lua 實作單一 owner token 的 global lock，token mismatch 時無法續約或釋除；lock 等待上限 420 秒。
- Job-first / Secret-second lifecycle：先建立 Job 取得 UID，再建立帶 owner reference 的 Secret；Secret 僅含 `targets.json`，使用 string_data 無任何 read/list 操作。
- Names/Labels 不含 URL/domain：job 與 secret 名稱使用 HMAC-SHA256(settings.SECRET_KEY, "kali:{scan_id}")[:10] 與隨機 hex 後綴；labels 固定為 `{"managed-by": "argus", "component": "kali-sqlmap"}`。
- 動態 deadline：單一 target 為預設 timeout + 30 秒；多 target 時 capped at 390 秒；Job TTL 300 秒。
- Bounded watch：整體上限 min(deadline+30, 420) 秒，每片 5 秒，片間檢查取消並每 60 秒續約 lock。
- Safe logging：只記 `correlation_id`、`phase`、`code`，不記 URL、query value、API exception body、runner raw log。
- Cleanup 在 finally block 執行， NotFound 視為成功，其他例外只記 safe code 不外洩 exception body。
- `KaliResult` 新增 `correlation_id` 與 `sqlmap_version` 欄位。
- 新增 `backend/apps/scans/tests_kali_kubernetes.py`：20 個 mocked lifecycle 測試，覆蓋所有 brief 指定場景。
- `pyproject.toml` 新增 `kubernetes>=35.0,<36`；`uv.lock` 已包含對應條目。

### 原因

Task 3 已建立 Docker executor，但正式環境偏好 Kubernetes 隔離。Task 4 實作 Kubernetes Job executor，符合 Task 1-3 的安全契約與 policy，並確保每個 scan 有硬上限的執行時間、目標數與全域並發控制。

### 影響範圍

- `kali_tools.py` 的 `_executor_for_backend()` 在 `kubernetes` backend 下 lazy import `KubernetesSqlmapExecutor`；正式環境啟用前需設定 `ARGUS_KALI_BACKEND=kubernetes`。
- 使用 Redis Lua 實作的 global lock 與 policy 的 `reserve_sqlmap_targets()` 共用同一個 Redis DB。
- Kubernetes Job/Secret 無持久化狀態，所有結果透過 `KaliResult` 傳回；runner stdout 仍不外洩。
- 不影響 Docker executor、其他 scanner、billing、前端。

### 驗證方式

- RED：`uv run python backend/manage.py test apps.scans.tests_kali_kubernetes -v 2` → `ImportError: cannot import name 'kali_kubernetes' from 'apps.scans.security'`，因當時 executor module 尚不存在。
- GREEN（focused）：同一命令 → 20 tests in 0.096s，全部通過。
- GREEN（regression）：`apps.scans.tests_kali_contracts apps.scans.tests_kali_policy apps.scans.tests_kali_tools apps.scans.tests_kali_kubernetes` → 73 tests in 18.024s，全部通過。
- Ruff：`uv run ruff check backend/apps/scans/security/kali_kubernetes.py backend/apps/scans/tests_kali_kubernetes.py` → `All checks passed!`。
- Lock：`uv lock --check` → `Resolved 62 packages in 4ms`。
- Django：`uv run python backend/manage.py check` → `System check identified no issues (0 silenced).`。
- Git：`git diff --check` → 僅有 LF/CRLF 警告（Windows 預期），無空白問題。

## Task 4 review 修復：admission 契約、鎖安全與 bounded lifecycle

### 變更內容

- 對齊後續 Task 5 / Task 7 的 runner 與 admission shape：Job / Secret 名稱改為
  `argus-sqlmap-{hmac10}-{hex12}` / `argus-targets-{hmac10}-{hex12}`，同一 execute
  僅生成一次 correlation ID；補齊 `argus.io/managed-by=argus`、`app=kali-sqlmap`。
- runner Pod 改用 `kali-runner` ServiceAccount、UID/GID/fsGroup 65532、
  `/usr/local/bin/python /opt/argus/runner.py`、read-only targets Secret、`/tmp` 1Gi
  emptyDir，以及 admission policy 要求的 CPU / memory / ephemeral-storage requests/limits。
- Secret `targets.json` 對齊 runner schema：只含 `schema_version`、`scan_id` 與
  `targets[{index,url}]`；移除 fingerprint。可信 evidence 欄位統一為 `tool_version`。
- Redis global lock 補上失去 ownership 與 Redis 例外處理：acquire 例外 silent-fail、
  renew 回 0/例外立即停止 runner lifecycle、release 失敗不遮蔽 `ScanCancelled`；
  stale cleanup、Job 建立、Secret 建立後各做 ownership checkpoint。
- 鎖等待使用 `< deadline` 與 remaining-based sleep；watch 最後一片依剩餘 budget
  縮短，並同時設定 Kubernetes `_request_timeout`，避免 420 秒與 watch 上限各多跑一片。
- executor outward `KaliResult.error` 與 audit `code=` 收斂至固定 taxonomy；
  `DeadlineExceeded` 對應 `job_deadline_exceeded`，其他 runner/watch/log failure 對應
  `runner_failed`，所有 parser contract error 對應 `invalid_result`。runner 私有
  `error_code` 不再直接外露。
- stale cleanup 改用每個既有 Job 自己的 `spec.active_deadline_seconds + 30`，嚴格
  超過才刪；缺失、bool、非正整數等無效值保守跳過。
- Pod log 只允許 exactly one、且 `metadata.name` 為非空字串的 Pod；零個、多個或
  無效名稱皆不讀 log，回 `runner_failed`。

### 原因

Task 4 首次 review 發現 runner Job 尚未符合後續 admission policy、Redis lock 失效可能
繼續建立資源或遮蔽取消、lock/watch equality edge 可超過硬界線、錯誤碼漂移、stale Job
錯用新請求 deadline，以及多 Pod 時任選第一個等安全缺陷。依 Subagent-Driven 流程將
finding 拆成 Fix 1、2A、2B、3A、3B、3C，由 OpenCode 逐一先寫有限 RED 再做最小修正。

### 影響範圍

- 僅調整 Kubernetes SQLmap executor、其 mocked lifecycle tests 與本 implementation log；
  未修改 billing、前端、其他 scanner 或 Django schema。
- 正式 Kali 仍維持預設 disabled；沒有 push、Argo Sync、production apply 或正式啟用。
- `.omo/` 中既有使用者資產保留；OpenCode 自動產生的 `.codegraph/` 暫存已由控制器驗證
  絕對路徑後清除。

### RED / GREEN 與驗證

- Fix 2A RED：5 個 lock ownership／取消測試在 0.026 秒內有限失敗；GREEN 後 29 tests。
- Fix 2B RED：lock equality edge 多跑 1 秒、watch 最後 slice 多跑 3 秒；GREEN 後 31 tests。
- Fix 3A RED：44 tests 中 27 failures，精確暴露 outward/audit taxonomy 漂移；GREEN 全綠。
- Fix 3B RED：long、boundary、missing、boolean deadline Job 均被誤刪；GREEN 後 45 tests。
- Fix 3C RED：多 Pod與非字串 Pod name 會誤讀 log；GREEN 後 48 tests。
- 控制器最終 focused：`apps.scans.tests_kali_kubernetes` → **48 tests，全部通過**。
- 控制器最終 Task 1–4 回歸：`tests_kali_contracts`、`tests_kali_policy`、
  `tests_kali_tools`、`tests_kali_kubernetes` → **101 tests in 16.581s，全部通過**。
- Ruff：兩個 Task 4 Python 檔 → `All checks passed!`。
- Lock：`uv lock --check --offline --no-cache` → `Resolved 62 packages in 2ms`。
- Django：`backend/manage.py check` → `System check identified no issues (0 silenced).`。
- Git：`git diff --check` → 只有 Windows LF→CRLF 提示，無 whitespace error。

## Task 4 第二輪 review 修復（2026-07-15）

依 reviewer findings 再拆成 OpenCode 小任務，全部先 RED 再 GREEN：

- Fix 4D1B：stale Job list 與每筆 stale delete I/O 前後均做 cancellation/ownership checkpoint；lock loss 停止建立新 Job。
- Fix 4D1C：Secret 建立成功返回後、watch 前再做 cancellation/ownership checkpoint。
- Fix 4D2A：Redis SET 成功後立即檢查取消；取消時用同一 owner token compare-and-DEL，release 例外不得遮蔽 `ScanCancelled`。
- Fix 4E：watch stream、Pod list、Pod log 各 I/O 前後均以同一 owner token 做 checkpoint，移除 periodic-only renew。

控制端驗證：focused `apps.scans.tests_kali_policy apps.scans.tests_kali_kubernetes` 共 79 tests 全綠；
Task 1–4 regression `apps.scans.tests_kali_contracts apps.scans.tests_kali_policy apps.scans.tests_kali_tools apps.scans.tests_kali_kubernetes`
共 123 tests in 16.741s 全綠；四個變更檔 Ruff 全綠；`uv lock --check --offline --no-cache` 通過；Django check 無問題。
未 push、未部署、未啟用正式 Kali；Task 5 等待 reviewer amended-commit 重審。

## Task 5：Pinned SQLmap runner image

### 變更內容

- 新增 `kali-runner/`：`runner.py`（純標準庫）在受限 Pod 內執行 SQLmap 並輸出符合 `kali_contracts.parse_runner_result` 的 ≤ 16384 bytes compact JSON；base image 為 `python:3.12.11-slim-bookworm` 固定 digest，SQLmap pinned commit `ea8c6bd…`（1.10 系列），`USER 65532:65532`、`HOME=/tmp`、唯讀 root filesystem。
- Runner 自驗七層深層檢查：URL 可解析、scheme、顯式 port（80/443）、無 userinfo、帶 query、所有 DNS 解析皆為公網可路由、整批同源；任一失敗回固定錯誤碼。
- 新增 `kali-runner/tests/`（38 tests）覆蓋命令形狀、sqlmap stdout 解析、run_target（timeout/例外/非零 returncode）、validate_batch（所有錯誤碼）、main()、`--self-test`、16384-byte size guard；test_runner.py 頂端插 `sys.path` 讓 `python -m unittest discover -s kali-runner/tests` 從 repo root 也能跑（commit `18f8bb6`）。
- `Dockerfile` build 時 `apt install` sqlmap（pinned commit），**啟動時不執行 apt install / 更新**；image 不裝 Metasploit / Nmap / kubectl / Docker CLI。

### 原因

Task 4 的 K8s executor 需要一個不可變、可被 CEL `approvedImage` 鎖定的 runner image；runner 同時是「深層防禦第二層」，在上層 policy 已驗證後再驗一次，避免任何繞過上層的惡意 input 打到內網。

### 影響範圍

- Image 為 disabled sentinel digest（`…@sha256:0000…`）， CEL admission 連合約內 Job 都會擋下；正式啟用前需 `scripts/promote_kali_image.py` 推廣為真實 digest。
- Runner stdout schema 與 `kali_contracts.parse_runner_result` 共用；schema 不一致時 parse 端會以 `invalid_result` 拒絕。

### 驗證方式

- 單元：`uv run python -m unittest discover -s kali-runner/tests` → 38 tests 全部通過。
- Ruff：`uv run ruff check kali-runner` → All checks passed。
- Image smoke（CI 覆蓋，本機 Docker cred-helper 壞掉無法跑）：`docker build` + `--self-test` + `sqlmap --version`；runs in `build-kali-runner.yml`。

## Task 6：AI-first tool exposure 與 confirmed-Finding scoring

### 變更內容

- `agent/tools.py` 新增 `build_tool_schemas(allow_sqlmap)`：非 `deep_mode`（即非 active + authorized）掃描**完全排除** `probe_sql_injection` schema（深拷貝，避免 LLM 看到能力）；`redact_tool_arguments` / `redact_tool_result` 在持久化 AgentStep 前遮罩 `probe_sql_injection` 的 URL 與 raw 結果。
- `agent/loop.py`：`HermesAgent` 依 `deep_mode` 傳入 `allow_sqlmap`；收集 `security_findings`（probe 確認的 SQLi）放進 `AgentRunResult`。
- `agent/runner.py`：`SECURITY_FIRST_PROMPT` 僅在 `deep_mode` 注入；agent 確認的 security findings 經 `persist_agent_security_findings` 落地。
- `scans/tasks.py`：順序固定為 scanner → **Hermes-Agent（先）** → **Kali fallback（後）** → scoring；Agent 確認的 `security_findings` 餵進 scoring；Redis 指紋讓 fallback 只處理 agent 沒驗證過的獨特 target。

### 原因

原本 Agent 與 Kali fallback 是兩條獨立鏈，且 `probe_sql_injection` 在非授權掃描也會出現在 LLM 的 tool 清單，造成提示層與授權層不一致。Task 6 把 Agent 提前到 fallback 之前、確認的 finding 餵進 scoring，並在 schema 層把未授權的 SQLi 能力完全隱藏。

### 影響範圍

- 僅 Agent 啟用（`ARGUS_AGENT_ENABLED=true`）的掃描會受到提示層與 schema 變更影響；Agent 預設關閉，向下相容。
- `scans.tasks` 的 Kali fallback 順序固定後，Redis 指紋去重可避免 agent 已驗證的 target 被重打一次。
- 不變：Docker demo、其他 scanner、billing。

### 驗證方式

- Agent 全 suite：`apps.agent` → 30 tests 通過（含新增 schema gate / redaction 測試）。
- Task 1–6 regression：`apps.scans.tests_kali_contracts apps.scans.tests_kali_policy apps.scans.tests_kali_tools apps.scans.tests_kali_kubernetes apps.agent` 全綠。
- Ruff：`uv run ruff check backend` → All checks passed。

## Task 7：Namespace 隔離 + least-privilege RBAC + 單 runner 配額 + 精確 /32 egress + fail-closed admission

### 變更內容

- `k8s/10-kali-runtime.yaml`：新增 `argus-kali` namespace（PSA `restricted:v1.35` + `argus.io/kali-runner=true` label）；worker SA `argus-worker-kali-orchestrator`（在 argus ns）+ tokenless runner SA `kali-runner`；least-privilege Role（jobs create/get/list/watch/delete、secrets create/delete、pods get/list/watch、pods/log get）；ResourceQuota 鎖死整個 ns 最多 1 Pod + 1 Job 且資源量與 runner 一致；LimitRange 補 per-container max。
- `k8s/11-kali-admission.yaml`：cluster-scoped `ValidatingAdmissionPolicy`（CEL，13 條契約）+ Binding 用 `namespaceSelector argus.io/kali-runner=true` 綁本 namespace；`failurePolicy: Fail` + `validationActions: [Deny]`；`approvedImage` 變數綁 disabled sentinel digest。
- `k8s/07-network-policies.yaml`：worker 對 Kubernetes API 僅允許 Service clusterIP 與 endpoint 兩個精確 /32（不擴大 private CIDR）；新增 `argus-kali-default-deny`（全拒 ingress+egress）與 `argus-kali-runner-egress`（CoreDNS 53 + 公網 IPv4/IPv6 80/443，排除所有 private/reserved/metadata 網段；不開 587）。
- `04-backend.yaml`：worker 掛 `serviceAccountName: argus-worker-kali-orchestrator`。
- `tests/test_kali_k8s_contract.py`：鎖定 manifest 的 namespace label、RBAC verbs、quota、admission expression、NetworkPolicy 等不漂移。

### 原因

Runner 在 argus-kali 跑時雖然 tokenless，仍需防止 worker 被拿來橫向移動；Task 7 以「namespace label → quota → CEL」三層契約＋精確 /32 API egress 把 worker 與 runner 的能力都收最小。

### 影響範圍

- 新增 namespace 與 cluster-scoped VAP；正式啟用前必須在目標叢集實機驗證 RBAC / admission / Network 三層（見 runbook）。
- Disabled sentinel image 让 CEL 連合約內 Job 都會被拒，是 fail-closed 設計。

### 驗證方式

- 契約測試：`uv run python -m unittest discover -s tests` 全綠（含 `test_kali_k8s_contract`）。
- `kubectl kustomize k8s` 成功渲染；`--dry-run=server` 與 `kubectl auth can-i` 須在目標叢集驗證（Task 11）。

## Task 8：Immutable image promotion script + CI build/write-back workflow + quality gate

### 變更內容

- `scripts/promote_kali_image.py`：純 regex 替換，把 `shijie85/argus-kali-runner@sha256:<64 hex>` 原子寫入 `k8s/01-namespace-config.yaml` 的 ConfigMap `ARGUS_KALI_RUNNER_IMAGE` 與 `k8s/11-kali-admission.yaml` 的 CEL `approvedImage`；只接受錨定格式（拒絕 tag）；兩份 manifest 各必須恰恰一個 digest 符記（零或多個 → `ValueError`）；`--check` 比對兩份一致。
- `.github/workflows/build-kali-runner.yml`：觸發 `kali-runner/**`、`scripts/promote_kali_image.py`、測試異動；序列化 GitOps concurrency group；鎖定 Docker Hub 帳號為 `shijie85`；pre-build smoke + `docker buildx` 推 image + 自動呼叫推廣腳本 write-back。
- `.github/workflows/quality.yml`：新增 Kali 推廣與 manifest 契約的 quality gate；CI 內 `promote_kali_image.py --check` 與 `kubectl kustomize` 納入閘門。
- `tests/test_kali_image_promotion.py`：鎖定推廣腳本的拒絕條件與冪等行為。

### 原因

Runner image 必須是不可變 digest（不接受 tag），且 ConfigMap 與 VAP 必須同時換成同一 digest 才能保持 CEL 與 worker 讀到的 image 一致；任何漂移都會讓合約內 Job 被擋或 worker 拉到錯 image。

### 影響範圍

- CI workflow 自動把新 build 的 digest 寫回 repo；本機不應手動改 ConfigMap / VAP 的 digest。
- 推廣腳本是啟用 runbook §1 的唯一入口。

### 驗證方式

- `uv run python scripts/promote_kali_image.py --check` → exit 0（兩份 manifest 一致）。
- `uv run python -m unittest discover -s tests` 全綠（含 `test_kali_image_promotion`）。
- CI run 在 push 後自動跑（本機 Docker build 仍 CI-deferred）。

## Task 9：Isolated Calico 整合測試 CODE（kind + 真實 runner build + scoring）

### 變更內容

- `tests/integration/`：`kind-config.yaml`（kind v1.35 + Calico v3.32 manifest）、`kali-fixture/`（repo-owned vulnerable Flask fixture，固定 `93.184.216.34` externalIP + CoreDNS patch + `/etc/hosts` 在 CI 本機路由，不觸及任何第三方）、`test_kali_job.py`（端對端覆蓋 `_probe_sql_injection → run_sqlmap → KubernetesSqlmapExecutor → 真實 Job/Secret/Watch → parse_runner_result → persist_agent_security_findings → calculate_scores`，含並發 / 取消 / 資源清零驗證）。
- `.github/workflows/kali-integration.yml`：`workflow_dispatch` 或 path trigger；CI 本機起 kind + Calico + 真實 runner build；嚴格 containment（fixture 可達 + 另一公網 IP 被 NetworkPolicy 擋下，任一失敗即 exit 1）；最後一步必刪 kind 叢集 + local registry。
- `tests/integration/kali-fixture/app.py` 與 fixture YAML 的 containment 註解（commit `8810409` 修正：`93.184.216.34` 是 example.com 的真實公網 IP，containment 來自 kube-proxy externalIPs interception + runner NetworkPolicy，而非 TEST-NET-3 不可路由）。

### 原因

單元測試只能 mock K8s API；Task 9 補一條在 CI 本機 kind + Calico + 真實 image build 的整鏈驗證，確保 Task 4–7 的契約在真實 Kubernetes + CNI enforcement 下成立。整合 run **不**在本地跑（kind 未裝），由 `gh workflow run kali-integration.yml` 在 CI 內執行。

### 影響範圍

- 新增測試資源與 workflow；不改變正式參集狀態（仍 disabled）。
- 整合測試以 skipUnless 包裝，單元測試 runner 不會啟動真實叢集。

### 驗證方式

- 本機單元測試：`uv run python -m unittest discover -s tests` + `kali-runner/tests` + `apps` 全綠。
- CI 整合 run：`gh workflow run kali-integration.yml`（Task 11 控制平面 gate 才會在目標叢集正式跑）。

## Task 10：Documentation synchronization and disabled software release

### 變更內容

- 新增 `docs/runbooks/kubernetes-secret-at-rest-encryption.md`（backup → key custody → apiserver manifest → sentinel raw-etcd verification → secret rewrite → health → recovery；頂部維護窗口警示）。
- 新增 `docs/runbooks/kali-sqlmap-rollout.md`（digest promotion → server dry-run → RBAC/admission/network 實機檢查 → disabled smoke → enablement → authorized positive test → rollback；同樣維護窗口警示）。
- 修改 `CLAUDE.md`（根）：新增 K8s Kali disabled-state 條目與兩份 runbook 在「特定操作指南」表的索引。
- 修改 `ONBOARDING.md`：tech-stack 表新增 `kubernetes>=35.0,<36` 列；§2.3 環境範例新增 `ARGUS_KALI_*` settings（預設全 false / disabled）。
- 修改 `backend/apps/scans/CLAUDE.md`：修正「合作式取消機制」段落的錯誤（**DB-status-based**，非 Redis 旗標）並更新 `cancellation.py` 表格列。
- 修改 `backend/apps/scans/security/CLAUDE.md`：重寫「Kali Tools 設計原則」對齊 Task 1–9 的實際架構（contracts / policy / facade / K8s executor / AI-first 接線 / disabled 狀態與 runbook 連結）。
- 修改 `backend/apps/agent/CLAUDE.md`：補 `build_tool_schemas` schema gate、`redact_tool_arguments` / `redact_tool_result` 遮罩、Hermes-before-fallback 順序、disabled 狀態與 runbook 連結。
- 修改 `k8s/README.md`：檔案表新增 10/11 manifest；新增「K8s Kali SQLmap 攻擊鏈（disabled，Task 10 交付）」章節；更新 2026-07-14 驗證表的 Kali row 與待辦第 2 項，反映軟體已完成但仍 disabled。
- 修改 `docs/capstone-roadmap.md`：新增「未開工 Future Backlog」section（8 項皆未實作：Metasploit K8s runner、Nmap runner、dedicated controller、multi-Job scheduler、async ScanJob continuation、SIEM/Prometheus alerts、automatic encryption-key rotation、Compose-only Docker CLI image split）。
- APPEND 本份 Task 5–10 summary 到 implementation log（不重寫既有 Task 1–4 entry）。

### 原因

程式碼是唯一事實來源，文件漂移視同 bug。Task 1–9 完成後必須同步所有受影響文件並交付 operator 啟用手冊，讓 Task 11 的 cluster-admin 能照 runbook 安全啟用；同時明確標示 DONE vs DEFERRED 與 backlog，避免被誤解為已上線。

### 影響範圍

- 純文件變更；不改變任何程式碼、migration、套件、billing、前端或既有 scanner 行為。
- 不新增 / 修改任何 live Secret、encryption key、SSH path、machine-specific value；runbook 範例一律 placeholder。

### 驗證方式

- 完整驗證套件（brief Step 5，扣除本機 Docker 壞掉的兩條 image smoke）：`uv sync --frozen` / `ruff check backend scripts tests kali-runner` / `manage.py check` / `manage.py makemigrations --check --dry-run`（無變更）/ `unittest discover -s tests` / `unittest discover -s kali-runner/tests` / `manage.py test apps` / `promote_kali_image.py --check` / `kubectl kustomize k8s` / `git diff --check` 全部通過。
- 文件與 secret 衛生 greps（brief Step 6）：sensitive-pattern scan 只見刻意 test literals 與 doc warnings，無 real credential。
- 本機 Docker image build / self-test smoke 與 kind+Calico 整合 run 因 local Docker cred-helper 壞掉 / kind 未裝而 CI-deferred，列為 Task 11 前置驗證。
- `kubectl apply --dry-run=server` + `kubectl auth can-i` RBAC 實機檢查 + Secret 靜態加密 + 正式 enablement 全為 Task 11 手動控制平面 gate。
