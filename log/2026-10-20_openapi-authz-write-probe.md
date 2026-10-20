# OpenAPI 規格端點餵進未授權探測＋寫入型端點授權探測（BFLA）

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- `security/exposure_scanner.py`：
  - 新增 `extract_openapi_operations(results)`——從本次 exposure 探到的 api-docs（OpenAPI 3.x／Swagger 2.0）解析 `paths`＋方法，組出外部路徑（`_apidoc_base_prefix`＝規格所在前綴，＋2.0 的 `basePath`；3.x 的 `servers` 多為內網，不用）；`MAX_OPENAPI_OPERATIONS=120`。
  - `_PacedRequester` 抽出 `_before()`（取消檢查＋RPS 時鐘），新增 `fetch(method=...)` 供非 GET 探測，一律 `max_redirects=0`、不帶 body。
  - 補 `import json`。
- `security/authz_probe.py`：
  - `openapi_probe_plan(operations, origin)`：把規格 operation 拆成「GET 讀取候選 URL（path 參數代入 `1`）」與「寫入授權探測目標」。
  - `probe_write_endpoints(write_targets, scan_job_id)`：對 POST／PUT／PATCH／DELETE 送未登入、無 body 請求（`ARGUS_AUTHZ_PROBE_WRITE_ENABLED`、`ARGUS_AUTHZ_PROBE_MAX_WRITE`）。
  - `analyze_write_probe_results(results)`：401／403／404／405／429／3xx＝有擋下不報；到達處理邏輯才算缺授權——2xx＝high、400／415／422／500＝medium；每端點一筆（合併多方法）；`security-unauth-api-write`。
- `tasks.py`：`stage_exposure` 解析 `openapi_operations` 傳給 `_run_authz_probe`；後者把規格 GET 併入讀取候選、對寫入目標跑寫入探測並記錄 finding、log 改寫讀取／寫入端點數。
- `security/owasp_mapper.py`：`security-unauth-api-write` → A01／CWE-862。
- `config/settings.py`：`ARGUS_AUTHZ_PROBE_WRITE_ENABLED`（預設 True）、`ARGUS_AUTHZ_PROBE_MAX_WRITE`（40）。
- `versions.py`：`RULESET_VERSION` 2026.10.17 → 2026.10.20（新增找問題的規則）。
- 測試：`tests_exposure_scanner.py`（`ExtractOpenapiOperationsTests`）、`tests_authz_probe.py`（`OpenapiProbePlanTests`、`AnalyzeWriteProbeResultsTests`）。

## 原因
ntubimdbirc.tw 報告中「成員名單匿名可讀」等後台外洩原本只有 AI Agent 讀 Swagger 後偶然發現，等級隨 AI 那一輪在高／嚴重間浮動，且前端不呼叫的端點不在確定性探測候選內。把規格列出的端點全部餵進確定性探測，讓這類問題每次都測得到、等級固定。使用者另要求把寫入端點（POST／PUT／PATCH／DELETE）也納入授權檢測。

## 影響範圍
- 只在「全站＋主動＋網域已驗證」的授權掃描執行（沿用 authz_probe 既有閘門）。
- **安全界線（硬性）**：寫入探測不送任何有效資料、不做真正的新增／修改／刪除；path 參數一律代入不存在的 id（`987654321`），裸集合的 DELETE 直接跳過，即使端點缺授權也只會打到「查無此物」。
- 新 finding `security-unauth-api-write` 計入資安分數、進問題清單與報告；`vuln_class=auth`、跨掃描正典身分 `auth|<正規化端點>|A01|CWE-862`（sentinel id 正規化為 `#`，不會 churn），可被跨層去重與歷史比較正確處理。
- 外部網路行為增加：對規格端點多送讀取／寫入請求，受既有 active RPS 預算與端點上限控制。

## 驗證方式
- `uv run ruff check`（變更檔）：All checks passed。
- `uv run python backend/manage.py check`：no issues。
- `manage.py test apps.scans.tests_authz_probe apps.scans.tests_exposure_scanner`：72 pass。
- `apps.scans.tests_pipeline_stages tests_coverage tests_scoring_versions tests_cross_layer`：72 pass。
- `apps.scans.tests_api_passive tests_security_redaction tests_cross_layer tests_scoring_and_report_grouping`：68 pass。
- shell 實測：`analyze_write_probe_results` → owasp A01／CWE-862、vuln_class auth、finding_identity `auth|/orders/#|A01|CWE-862`。
- 未自動驗證：正式叢集對真實授權目標的端對端行為（需部署 backend 後實機確認；不影響本機與 CI）。
