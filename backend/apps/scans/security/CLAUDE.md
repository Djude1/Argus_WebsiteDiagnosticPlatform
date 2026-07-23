# scans/security 子模組規則

Claude 操作 `backend/apps/scans/security/` 時，本檔在 `scans/CLAUDE.md` 之後自動載入。

---

## 職責定義

此 sub-package 負責**深度主動式資安檢查**，與 `scanners.py` 的被動式基本檢查嚴格分離。

| 位置 | 負責什麼 | 不負責什麼 |
|---|---|---|
| `scanners.py` → `analyze_security()` | HTTPS 判斷、安全 header 存在性、CSRF token 偵測（被動、已有的） | 任何深度分析 |
| `scanners.py` → `analyze_data_exposure()` | PII 偵測（被動、已有的） | 主動掃描 |
| **此 sub-package（security/）** | SSL/TLS 深度、Cookie 旗標、CORS/CSP 品質、OWASP 對映、Kali 呼叫 | 修改 ScanJob.status、呼叫 billing |

**規則：** 凡是「被動讀取已有 response headers/HTML」的安全性判斷留在 `scanners.py`；凡是「需要額外連線、工具呼叫、或深度解析」的放進此 sub-package。

---

## 檔案規劃

| 檔案 | 職責（待建） | 狀態 |
|---|---|---|
| `ssl_scanner.py` | SSL/TLS 深度分析：憑證到期、弱 cipher、過期協議（TLS 1.0/1.1）| 已建 |
| `cookie_scanner.py` | Cookie 安全旗標：Secure、HttpOnly、SameSite | 已建 |
| `header_scanner.py` | 資訊洩露標頭（Server/X-Powered-By）、CORS 設定、CSP 品質分析 | 已建 |
| `owasp_mapper.py` | Finding 對映 OWASP Top 10（A01~A10）與 CWE 編號（`tag()` + `backfill()`） | 已建 |
| `secret_scanner.py` | 硬編碼/外洩秘鑰偵測（AWS/Google/GitHub/Stripe/連線字串/私鑰/明文密碼）+ 遮罩 `redact_secrets_in_text` | 已建 |
| `exposure_scanner.py` | 敏感檔案主動探測（content discovery）：robots/sitemap + 內建字典 → Playwright 探測 → 檔案分類 + 秘鑰/PII 解析 | 已建 |
| `kali_tools.py` | Facade：`run_sqlmap` / `run_sqlmap_batch` / `validate_findings_with_kali` / `run_metasploit`；統一走 `reserve_sqlmap_targets` 預算 + backend dispatcher | 已建 |
| `kali_contracts.py` | 安全結果契約：`KaliResult` / `ReservedSqlmapTarget` / `SqlmapExecutor` protocol / `parse_runner_result` / `redact_url_query_values` | 已建（Task 1） |
| `kali_policy.py` | 原子授權 + Redis 三目標預算 + 900s deadline + SHA-256 去重：`reserve_sqlmap_targets()` | 已建（Task 2） |
| `kali_kubernetes.py` | K8s Job executor：`KubernetesSqlmapExecutor`、Redis 單一 owner global lock、Job-first/Secret-second lifecycle、cancellation-aware watch | 已建（Task 4） |
| `sri_scanner.py` | SRI 缺失偵測：外部跨來源 `<script>/<link>` 缺 `integrity` | 已建 |
| `dns_scanner.py` | DNS/郵件安全：SPF / DMARC / DNSSEC（不做 DKIM） | 已建 |
| `js_library_scanner.py` | 第三方 JS 庫版本→CVE 比對：解析 <script> 用 Retire.js 規則庫離線比對已知漏洞 | 已建 |

---

## 整合規則

- **所有 scanner 函式回傳 `list[dict]`**，格式與 `scanners.py` 的 `make_finding()` 相同
- **不直接寫入 DB**：回傳 findings list，由 `tasks.py` 統一寫入
- **呼叫點在 `tasks.py`**：在 Nuclei 掃描完成後，`tasks.py` 依序呼叫此 sub-package 的各 scanner
- **Kali 工具呼叫順序**：Nuclei 偵測完成 → Hermes-Agent 判斷 → `kali_tools.py` 執行，不可與 Nuclei 同時對同一目標打

---

## SSL Scanner 設計原則

```python
# ssl_scanner.py 的函式簽名
def analyze_ssl(hostname: str, port: int = 443, scan_job_id: int = 0) -> list[dict]:
    """連線取得憑證資訊，回傳 Finding list。任何例外 silent-fail 回傳 []。"""
```

- 使用 Python 內建 `ssl` 模組，不依賴外部 binary
- 憑證到期 ≤ 30 天 → HIGH；≤ 7 天 → CRITICAL
- 協議版本低於 TLS 1.2 → HIGH
- 弱 cipher（RC4、DES、3DES）→ HIGH

---

## Cookie Scanner 設計原則

```python
# cookie_scanner.py 的函式簽名
def analyze_cookies(cookies: list[dict], url: str) -> list[dict]:
    """接收 Playwright 的 context.cookies()，回傳 Finding list。"""
```

- Secure flag 缺失且 URL 為 HTTPS → MEDIUM
- HttpOnly flag 缺失 → LOW
- SameSite 為 None 且無 Secure → MEDIUM

---

## SRI Scanner 設計原則

```python
def analyze_sri(pages: list[dict]) -> list[dict]:
    """掃 crawled_pages 的外部無 integrity <script>/<link>，回 Finding list。"""
```

- 解析用 stdlib `html.parser.HTMLParser`，不引入 BeautifulSoup
- 只報**跨來源**資源（同源/相對路徑跳過，避免噪音）；已有 `integrity` 跳過
- 依解析後資源 URL 去重，整個 scan 同一 CDN URL 只報一次 → 一律 LOW

## DNS Scanner 設計原則

```python
def analyze_dns(host: str) -> list[dict]:
    """用 dnspython 查 SPF/DMARC/DNSSEC，回 Finding list。例外回 []。"""
```

- SPF 缺失 → MEDIUM；SPF `+all` → HIGH
- DMARC 缺失 / `p=none` → LOW；DNSSEC 缺失 → LOW（措辭採最佳實務建議）
- SPF/DMARC 查不到時退父網域一層；**不做 DKIM**（黑盒無法可靠列舉 selector）
- 只查目標自身網域，無 SSRF 面；新增相依 `dnspython`

---

## JS Library Scanner 設計原則

```python
def analyze_js_libraries(pages: list[dict]) -> list[dict]:
    """解析爬蟲已抓 HTML 的 <script>，用 vendored Retire.js 規則庫離線比對版本→CVE。例外回 []。"""
```

- 被動、零額外 HTTP（只讀 `page["html"]` 的外部 src URL + inline 內容）、零新第三方套件（純 stdlib）
- 版本萃取用 Retire.js `extractors` 的 uri/filename/filecontent（`§§version§§` 替換為 `([0-9][0-9.a-z_\-]+)`）；不做 func（需 runtime eval）/ hashes（需完整檔位元組）
- severity 沿用 Retire.js 值但 **critical 封頂 HIGH**（被動偵測未實機確認可利用）
- 單一 rule_id `js-lib-known-vuln` → A06/CWE-1104；per-CVE 的具體 CWE/CVE/summary/連結進 `evidence_json`
- 以 `(庫名, 版本)` 去重；規則庫 vendored 於 `data/jsrepository.json`（Apache-2.0），手動更新

---

## Secret / Exposure Scanner 設計原則

- **`secret_scanner.detect_secrets_in_text(text)`**：純函式，高訊號前綴 regex（避免誤報）；回傳遮罩後結果。
  - **被動使用**（任何模式）：`tasks.py` per-page 對已抓到的 HTML/inline script 偵測（零額外請求）。
  - `redact_secrets_in_text(text)` 用於把「檔案內容片段」當證據前遮罩，**一律遮罩**（不因 placeholder 子字串豁免，否則真密碼會二次外洩）。
- **`exposure_scanner.probe_paths(...)`**：主動內容探測，**只在 `deep_mode`（`scan_mode==ACTIVE and active_testing_authorized`）由 tasks.py 呼叫**；被動模式不得發探測請求。
  - `build_probe_targets` 強制 **same-origin**（內建字典含 dotted/非 dotted/.txt 變體）。
  - `probe_paths` 的逐路徑 GET 用 `max_redirects=0`，避免目標站 open-redirect 把探針導向 metadata/外站。
  - sitemap 解析前截 512KB，防 XML entity expansion。
  - 每次請求前 `is_cancelled` 檢查 + active RPS 速率限制；任何例外 silent-fail。
- **`analyze_robots_disclosure(disallow)`**：被動，robots.txt 列出 ≥3 條敏感路徑時報「以 Disallow 當地圖洩露」。
- **已知待辦（產品層級）**：scans 目前不擋 private/loopback 目標（crawler 既有行為），主動探測會放大內網 SSRF 風險；是否加 SSRF 政策需產品層級決定，勿只在單一 scanner 片面封鎖。

## Kali Tools 設計原則

架構由四個模組串接：`kali_contracts.py`（安全結果契約）→ `kali_policy.py`（原子授權 + Redis 預算）
→ `kali_tools.py`（facade / dispatcher）→ `kali_kubernetes.py` 或 Docker executor（backend 實作）。

```python
# kali_tools.py 的對外 facade 簽名
def run_sqlmap(target_url: str, scan_job_id: int) -> dict:
    """單目標：一律先 reserve_sqlmap_targets(max_count=1) 再依 backend 派發。
    回傳 dict（{ok, tool, blocked_reason, returncode, stdout, error, confirmed, evidence_summary}）
    與 agent/tools.py 既有契約相容；stdout 固定為 ""。"""

def run_sqlmap_batch(scan_job_id: int, candidate_urls: list[str], max_targets: int = 3) -> dict:
    """批次：reserve max_count=min(max_targets, 3)；每個 admitted target 執行一次。
    回傳 {blocked_reason, executions: tuple[SqlmapExecution, ...]}。"""

def validate_findings_with_kali(scan_job_id: int, candidate_urls: list[str], max_targets: int = 3) -> list[dict]:
    """tasks.py 編排層入口：先挑帶 query parameter 的候選，再跑 run_sqlmap_batch；
    只信任 KaliResult.confirmed；產出 rule_id=kali-sqlmap-sqli (A03/CWE-89) critical Finding。"""

def run_metasploit(module: str, options: dict, scan_job_id: int) -> dict:
    """僅 docker backend 支援；kubernetes / 未知 backend 一律回
    blocked_reason=tool_not_supported_by_backend，不會呼叫 docker。"""
```

### Backend dispatcher（Task 3 / Task 4）

- `_executor_for_backend()` 依 `settings.ARGUS_KALI_BACKEND` 選擇 executor：
  - `docker` → `DockerSqlmapExecutor`：raw stdout 只在 process 內解析，回 `KaliResult`（`stdout=""`），
    `evidence_summary` 限 `parameter` / `techniques` / `dbms` / `ARGUS_KALI_SQLMAP_VERSION`。
  - `kubernetes` → lazy import `KubernetesSqlmapExecutor`：見下方「Kubernetes executor」。
  - `disabled` / 未知 → 回 `None`；facade 走 `backend_misconfigured` blocked 分支並寫 warn audit。
- base `docker-compose.yml` **完全不掛** docker.sock、不裝 docker CLI；Docker demo 走獨立
  `docker-compose.attack.yml` override（worker environment 加 `ARGUS_KALI_BACKEND: "docker"`）。
  正式 K8s 參集則設 `ARGUS_KALI_BACKEND=kubernetes`，由 worker 透過 in-cluster config 操作叢集。

### Settings（Task 1 新增，全預設停用）

| Setting | 預設 | 說明 |
|---|---|---|
| `ARGUS_KALI_ENABLED` | `False` | 總開關；必須為 True 才會進一步 dispatch |
| `ARGUS_KALI_BACKEND` | `"disabled"` | `disabled` / `docker` / `kubernetes` |
| `ARGUS_KALI_CONTAINER` | `"argus-kali-1"` | 僅 Docker backend 使用 |
| `ARGUS_KALI_NAMESPACE` | `"argus-kali"` | 僅 Kubernetes backend 使用 |
| `ARGUS_KALI_RUNNER_IMAGE` | `""` | K8s runner image，正式啟用時為 `repository@sha256:<64 hex>` |
| `ARGUS_KALI_SQLMAP_VERSION` | `"1.10"` | 寫進 evidence_summary 的版本標籤 |
| `ARGUS_KALI_TIMEOUT` | `120` | 單一 target SQLmap timeout（秒） |
| `ARGUS_KALI_MAX_TARGETS` | `3` | 每 scan 最多目標數（policy 強制上限） |
| `ARGUS_KALI_LOCK_WAIT_SECONDS` | `420` | K8s global lock 等待上限 |
| `ARGUS_KALI_SCAN_DEADLINE_SECONDS` | `900` | 每 scan Kali 總 deadline（policy 端） |
| `ARGUS_KALI_STATE_TTL_SECONDS` | `86400` | Redis 去重 fingerprint TTL |
| `ARGUS_KALI_RESULT_MAX_BYTES` | `16384` | runner stdout JSON 上限（contract 端） |
| `ARGUS_KALI_REDIS_URL` | `redis://localhost:6379/0` | policy + K8s global lock 共用 Redis |

### 共用授權與預算（kali_policy）

`reserve_sqlmap_targets()` 是 docker / kubernetes / agent-tool-call / fallback **共用**的入口，
依固定順序檢查：Kali 開關 → backend → ScanJob 存在 → cancel → active mode → 主動授權 → 公網 →
同源 → query parameter；通過後才以 Redis Lua 原子套用 900s deadline、最多 3 個目標、SHA-256
去重與 86400s TTL。Policy 不保存完整 target URL 或 query value（只用標準化後的 SHA-256 指紋）。

### Kubernetes executor（kali_kubernetes.py，Task 4）

- 僅 `config.load_incluster_config()`，無本機 kubeconfig fallback；worker 必須掛
  `argus-worker-kali-orchestrator` SA（見 `k8s/10-kali-runtime.yaml`）。
- 單一 owner global lock：`SET NX PX` + Lua compare-and-* ；mismatched token 無法續約或釋放。
- Job-first / Secret-second：先建 Job 拿 UID，再建 owner-referenced Secret（只含 `targets.json`）；
  worker 只 `create` / `delete` Secret，**不** get/list/read 回。
- 動態 deadline = `min(active_deadline + 30, 420)`；watch 5s/片，每片 I/O 前後皆做 cancellation
  + ownership checkpoint；`ScanCancelled` 原樣重拋，不遮蔽。
- `append_log` 只記 `correlation_id` / phase / fixed safe error code（如 `job_deadline_exceeded`、
  `runner_failed`、`invalid_result`），**不記** URL、query value、API exception body、raw log。
- Cleanup 在 finally 必跑；NotFound 視為成功。

### 掃描流程接線（AI-first，Task 6）

`tasks.py` 的順序固定為：被動 + 主動 scanner → **Hermes-Agent（先）** → **Kali fallback（後）** → scoring。
Agent 確認的 `security_findings` 會餵進 scoring（DB 落地由 `runner.persist_agent_security_findings`）；
Redis 指紋讓 fallback 只處理 agent 沒驗證過的獨特 target（單一 batch）。`probe_sql_injection` 在
agent 端額外有同源 + query parameter + deep_mode 三層閘，AgentStep 持久化前經
`redact_tool_arguments` / `redact_tool_result` 遮罩 URL 與 raw 結果。

### 不可放寬的硬性規則

- **授權與預算一律經 `reserve_sqlmap_targets`**：facade / executor / agent 都不再自做 scan_mode /
  active_testing_authorized 檢查；任何新增 backend 都必須接在同一個 policy 入口後。
- **任何例外 silent-fail**，回結構化 `KaliResult` / dict，**不**影響主掃描流程；唯一例外是
  `ScanCancelled` 必須原樣重拋讓取消流程傳遞。
- **所有呼叫（含被擋）都記錄進 `scan_logger.append_log`**；helper `_log_kali_decision` 只記
  fixed structured reason，嚴禁拼接 URL / query value / raw stdout / exception body。
- **runner raw stdout 永不離開 executor process**：持久化內容必經 `KaliResult` schema 與
  `redact_url_query_values`；Finding 的 `evidence_json` 只放 `evidence_summary`。
- subprocess 一律 list 形式（非 shell=True）+ module/option/URL 輸入驗證，防命令注入。

### 目前狀態與啟用

軟體已 merge 並通過單元／合約測試，但正式叢集仍維持 disabled：`ARGUS_KALI_ENABLED=false`、
`ARGUS_KALI_BACKEND=disabled`、runner image 為 disabled sentinel digest
`shijie85/argus-kali-runner@sha256:0000…`（見 `k8s/01-namespace-config.yaml` 與
`k8s/11-kali-admission.yaml`）。啟用流程（靜態加密 → digest 推廣 → dry-run → RBAC/Admission/
Network 實機 → disabled smoke → enablement → 授權 positive test → rollback）見 operator runbook
[`../../../docs/runbooks/kali-sqlmap-rollout.md`](../../../docs/runbooks/kali-sqlmap-rollout.md)；
靜態加密前置見 [`../../../docs/runbooks/kubernetes-secret-at-rest-encryption.md`](../../../docs/runbooks/kubernetes-secret-at-rest-encryption.md)。
Docker Compose demo（`docker-compose.attack.yml`，本機或隔離 demo 專用）維持原狀，不在本啟用鏈上。

---

## 禁止事項

| 禁止 | 原因 |
|---|---|
| `kali_tools.py` 在 passive mode 執行 | 未授權主動攻擊 |
| 任何函式直接寫入 Finding model | 職責分離，DB 寫入只在 tasks.py |
| 修改 `ScanJob.status` | 狀態機只在 tasks.py 管理 |
| Kali 工具與 Nuclei 同時對同一目標執行 | 目標可能因流量異常封鎖 IP |

---

## 長遠遷移計畫（專題後）

目前 `scanners.py` 的 `analyze_security()` 和 `analyze_data_exposure()` 仍留在原處（被動式）。
專題結束後可將這兩個函式移至此 sub-package 的 `passive_scanner.py`，同時將 `nuclei_scanner.py`
和 `katana_scanner.py` 也移進來，使資安邏輯完全集中。遷移不涉及 model 或 migration 變更，
只需更新 `tasks.py` 的 import 路徑。
