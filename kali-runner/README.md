# kali-runner —— Argus 專屬 SQLmap runner image

> Task 5 交付物：在 Kubernetes 受限 Job 內執行 SQLmap，只回傳符合契約的安全摘要。
> 設計規格：[`docs/superpowers/specs/2026-07-14-k8s-kali-sqlmap-job-design.md`](../docs/superpowers/specs/2026-07-14-k8s-kali-sqlmap-job-design.md)

## 角色與定位

`runner.py` 是 SQLmap 攻擊鏈的**深層防禦第二層**：上層 `kali_policy` 已經過三重授權
鎖、公網／同源／query 驗證；runner 在 Pod 內啟動後會**再驗一次**，避免任何繞過上層
的惡意 input 直接打到內網。它在 Pod 中以 UID/GID 65532 非 root 執行，唯讀 root
filesystem，僅能讀短效 target Secret 與寫入 size-limited emptyDir。

| 項目 | 值 |
|---|---|
| Base image | `python:3.12.11-slim-bookworm` 固定 digest |
| SQLmap 版本 | pinned commit `ea8c6bdb63a3b2da1584f328836eb0d28116f7c4`（1.10 系列） |
| 執行身份 | `USER 65532:65532`、`HOME=/tmp` |
| Entry point | `/usr/local/bin/python /opt/argus/runner.py` |
| 第三方套件 | **無**（runner.py 純標準庫；image 不裝 Metasploit / Nmap / kubectl / Docker CLI） |

## 輸入

Task 4 的 `KubernetesSqlmapExecutor` 會建立一把短效、由 Job owner reference 控制
的 Secret，唯讀掛載到 `/run/argus-targets/targets.json`：

```json
{"schema_version":1,"scan_id":123,"targets":[{"index":0,"url":"https://authorized.example/path?parameter=value"}]}
```

完整目標 URL 只存在這個 Secret 與 runner process 記憶體；不會進入 Job args、labels
或任何 log。

## 輸出（與 `backend/apps/scans/security/kali_contracts.py::parse_runner_result` 對齊）

runner 會在 stdout 印出**恰好一份** ≤ 16384 bytes 的 UTF-8 compact JSON：

```json
{
  "schema_version": 1,
  "tool": "sqlmap",
  "results": [
    {
      "index": 0,
      "ok": true,
      "confirmed": false,
      "returncode": 0,
      "parameter": "id",
      "techniques": [],
      "dbms": "",
      "error_code": ""
    }
  ]
}
```

每筆 result 恰為 8 個鍵；欄位格式：

| 欄位 | 規則 |
|---|---|
| `index` | 必須出現在 `expected_targets`；不可重複 |
| `ok` / `confirmed` | bool；`confirmed=True` 時 `ok` 必須為 True |
| `returncode` | int 或 null |
| `parameter` | regex `[A-Za-z0-9_.-]{0,64}` |
| `techniques` | list；值須來自六值白名單 |
| `dbms` | regex `[A-Za-z0-9 ._-]{0,64}` |
| `error_code` | regex `[a-z0-9_]{0,64}`；`ok=True` 時只能為空字串 |

技術名稱白名單：`boolean-based blind`、`error-based`、`inline query`、
`stacked queries`、`time-based blind`、`union query`。

`runner_output_too_large` 是 runner 私有 code：當正常彙整後的輸出仍超過 16384 bytes
時，每筆 result 一律退化為只帶 index 與此 code 的 placeholder。Executor 會把它映射
成 outward 的 `runner_failed`，不外洩任何細節。

**輸出禁止包含**：raw sqlmap stdout、完整 query value、HTTP body、資料庫列值、目標
host（除了 runner 本身需要的內部處理）。

## 深層驗證（runner 自驗，不假設上層正確）

每次執行前，runner 對整批 targets 做以下檢查；任一失敗即整批回 `ok=False` 的安全
錯誤碼，不揭示是哪一目標觸發：

| 條件 | 失敗時錯誤碼 |
|---|---|
| URL 可被 `urlsplit` 解析、有 scheme 與 host | `malformed_url` |
| scheme 為 `http` 或 `https` | `invalid_scheme` |
| 顯式 port 為 80 或 443（或未指定 port 套預設） | `invalid_port` |
| 不含 `userinfo`（無 `user:pass@`） | `userinfo_forbidden` |
| 帶非空 query string | `no_query_parameter` |
| 所有 DNS 解析結果皆為公開可路由（排除 private / loopback / link-local / multicast / reserved / unspecified） | `target_not_public` |
| 整批 scheme+host+port 一致（同源） | `cross_origin_forbidden` |

## 本機開發與測試

`runner.py` 只用標準庫，可以直接用 `python -m unittest` 跑單元測試（不需要 K8s /
sqlmap / Docker）：

```powershell
# 從 worktree 根目錄
uv run python -m unittest discover -s kali-runner/tests -t kali-runner -v

# 或從 kali-runner 目錄
cd kali-runner
uv run python -m unittest discover -s tests -v
```

測試涵蓋：命令形狀、sqlmap stdout 解析、run_target（含 timeout / 例外 / 非零
returncode）、validate_batch（所有錯誤碼）、main()（malformed / >3 / 重複 index /
cross-origin / private DNS）、`--self-test`、16384-byte size guard。

## Image smoke test

```powershell
docker build -t argus-kali-runner:test kali-runner

# self-test：固定輸出，不讀 Secret、不啟動 sqlmap
docker run --rm --read-only --user 65532:65532 `
  --tmpfs /tmp:rw,nosuid,nodev,size=1g `
  argus-kali-runner:test --self-test

# 驗證 sqlmap 版本以 1.10 開頭
docker run --rm --read-only --user 65532:65532 `
  --tmpfs /tmp:rw,nosuid,nodev,size=1g `
  --entrypoint /usr/local/bin/python `
  argus-kali-runner:test /opt/sqlmap/sqlmap.py --version
```

預期：

- 第一個命令輸出 `{"schema_version":1,"tool":"sqlmap","results":[]}` 並以 exit 0 結束。
- 第二個命令版本字串以 `1.10` 開頭（可能帶 stable 後綴）。

## 與 Task 4 / Task 6+ 的接點

- **Task 4 (`kali_kubernetes.py`)**：`KubernetesSqlmapExecutor` 建立短效 Secret、
  觀察 Job 狀態、讀取單一 Pod log（`limit_bytes=16385`，超過 16384 由
  `parse_runner_result` 拒絕）。runner 與之間沒有額外耦合，僅透過 schema 溝通。
- **Task 6+ (CI / GitOps)**：CI build 時必須使用本 Dockerfile 與 pinned digest；
  promotion 流程會把 `shijie85/argus-kali-runner@sha256:...` 寫回 Kustomization 與
  ValidatingAdmissionPolicy，pod 方能建立。

## 安全屬性摘要

- image build 時 pin base digest + sqlmap commit，**啟動時不執行 apt install / 更新**。
- runner 只能讀 targets Secret；不能讀 `argus-config` / `argus-secret` 或任何
  application credential。
- 預設無任何對 K8s API、Redis、PostgreSQL、LLM provider 的 egress；NetworkPolicy
  另由 `k8s/` 規範。
- stdout 內容已通過嚴格 whitelist；意外大於 16384 bytes 時退化為 placeholder，不洩漏。
