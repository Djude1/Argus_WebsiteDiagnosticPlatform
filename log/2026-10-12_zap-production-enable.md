# 正式 K8s 預設部署並啟用 OWASP ZAP 被動分析

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
- `k8s/optional/zap-passive.yaml` 移為 `k8s/12-zap-passive.yaml` 並列入 `k8s/kustomization.yaml`（Argo 會同步 `argus-zap` namespace、ZAP Deployment／Service、NetworkPolicy）；檔頭註明同步前要先手動建立的 Secret 與回滾方式。
- `k8s/01-namespace-config.yaml`：`ARGUS_ZAP_ENABLED: "true"`、`ARGUS_ZAP_API_URL` 指向 `zap.argus-zap.svc.cluster.local:8090`。
- `k8s/04-backend.yaml`：worker 的 `argus.io/config-revision` 改為 `zap-2026-10-12`，讓 worker 重啟讀新設定。
- `k8s/07-network-policies.yaml`：新增 `worker-egress-to-zap`（worker → argus-zap 的 zap Pod TCP 8090）。原本的 `application-egress-boundary` 排除叢集內網段，沒有這條 worker 連不到 ZAP。
- `k8s/02-secret.example.yaml`：`ARGUS_ZAP_API_KEY` 註解寫明必須與 `argus-zap/zap-api` 的值相同。
- 合約測試 `tests/test_zap_optional_contract.py` 改名為 `tests/test_zap_contract.py`：改為鎖定「已列入 kustomization、ConfigMap 啟用、網址正確、API key 不在 ConfigMap」，並新增 worker egress 測試。
- 文件：`docs/zap-passive.md` 的 K8s 一節（正式環境預設啟用、同步前建立 Secret、驗證、回滾）、`k8s/README.md`、`.env.example`、`docs/scan-upgrade-roadmap.md`、`backend/apps/scans/security/CLAUDE.md`、`CLAUDE.md`／`AGENTS.md`（K8s 操作底線加 ZAP 一條）。
- `docs/scan-stage-checks.md`：HAR 錄製條件更正為「勾資安且已啟用 ZAP（被動模式也會）」，與 `tasks._runs_zap_passive` 一致。
- 系統手冊附錄三 md 恢復 ZAP（取代 `8f64485` 的移除）：表 9-2-3 第 10 列與 C-13 註明正式環境 2026-10-12 起部署並啟用。

## 原因
使用者要在正式 K8s 啟用 ZAP，並讓正式環境預設開啟。程式預設仍為關閉（本機與 CI 沒有 ZAP daemon）。

## 影響範圍
- 勾資安的掃描在正式環境會多一個 `zap_passive` 階段；爬蟲錄 HAR（只同 origin、用完即刪），ZAP 只跑被動規則、不對目標發請求。
- ZAP Pod 需要約 1 GiB 記憶體（request 1Gi）。
- **Argo 同步前必須先手動建立 Secret**：`argus-zap` namespace 的 `zap-api`（key `api-key`），以及 `argus-secret` 的 `ARGUS_ZAP_API_KEY`（同一個值）。沒有的話 ZAP Pod 會 `CreateContainerConfigError`；只缺後者時 `zap_passive` 不執行。值不得進 Git 或 log。
- 回滾：ConfigMap 改回 `"false"`、改 worker config-revision 後同步。

## 驗證方式
- `uv run python -m unittest tests.test_zap_contract tests.test_k8s_runtime_commands`：14 項通過。
- `uv run ruff check`（tests）通過。
- 尚未完成（需正式叢集）：Argo Sync／Health、ZAP Pod Ready、worker 連得到 ZAP、一次勾資安的掃描覆蓋紀錄 `zap_passive=completed`。

## 補充：文件全面核對（同日）
- 全 repo 搜尋 ZAP 相關敘述後修正：`k8s/12-zap-passive.yaml` 與 `docs/zap-passive.md` 的測試檔名改為 `test_zap_contract`；`docs/scan-stage-checks.md` 第 10 節註明正式環境已啟用；`k8s/README.md` 檔案表 12 列移到 11 列之後。
- 競賽文件：`需求書_複賽版完整內容.md` 的 ZAP 敘述由「平台部署時」改為「正式環境 2026-10-12 起部署」；`設計文件_圖表與成本模組.md` 部署架構圖加 `argus-zap` namespace 與 worker → ZAP 連線，事實依據範圍改到 `12-zap-passive.yaml`，部署要點加 ZAP 一條（資源取自 manifest）。
- 不改：`docs/business-model-plan.md`（資源量測後才定價，仍成立）、ADR-0004 與研究文件（未來規劃與調研紀錄）、`settings.py` 註解（程式預設關閉仍成立）。
