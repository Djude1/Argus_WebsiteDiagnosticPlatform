# 部署 kali disabled 版本到正式 K8s + 修復 kali 架構

**日期**：2026-07-24  
**操作者**：Claude（commit/push 用 SmallLoOwO 身份）

## 變更內容
- 將 `codex/docs-deployment-handoff`（commit `b87c5ce..d637add`，18 commits）的 K8s Job-based kali 鏈 merge 進 `main`（`1340441`，branch `feat/kali-k8s-integration` fast-forward）並 push origin。
- 正式 K8s 部署 disabled 版本：apply `k8s/10-kali-runtime.yaml`（`argus-kali` namespace + ServiceAccount + Role/RoleBinding + ResourceQuota + LimitRange）與 `k8s/11-kali-admission.yaml`（ValidatingAdmissionPolicy + Binding，cluster-scoped）。
- 取代 main 原 Docker-based kali（`docker exec argus-kali-1`，需 host docker.sock，與 K8s containerd 不相容且是 host root 安全風險）→ 改為 backend dispatch（`disabled` / `docker` 僅本機 demo / `kubernetes` 正式 K8s Job）。

## 原因
使用者反映「K8s 環境無法使用 kali 掃描」。根因：main 原 kali 是 Docker-based，與 K8s containerd 先天不相容。改部署 K8s Job-based 版本（維持 disabled），讓架構正確就位、可隨時啟用，但不承擔啟用風險。

## 影響範圍
- kali **雙重 disabled**（ConfigMap `ENABLED=false` + VAP `approvedImage=sentinel`），正式環境完全不觸發；即使誤翻 ConfigMap flag，VAP 仍擋（真實 image ≠ sentinel）。
- `argus-kali` namespace + RBAC（最小權限）+ ResourceQuota（單 runner）+ VAP（fail-closed）就位。
- web/worker 滾動更新至 `sha-1340441`。
- 啟用（主動 SQLi）屬 Task 11 手動控制平面 gate，本次未做。

## 驗證方式
- **本機**：`ruff check` 通過；`manage.py check` 0 issues；`apps.scans + apps.agent` 453 tests OK；root `tests/` 36 OK；`kali-runner/tests` 38 OK；`promote_kali_image.py --check` exit 0；`kubectl kustomize k8s` render OK。
- **正式叢集（唯讀 kubectl）**：`argus-kali` 資源齊全；ConfigMap `ENABLED=false`/`BACKEND=disabled`；VAP `failurePolicy=Fail` + `approvedImage=sentinel`；RBAC `create jobs`=yes / `get secrets`=no / `create pods`=no；`kubectl apply --dry-run=server` 全 manifest 有效。
- web/worker Running `sha-1340441`、0 restarts、migrate Completed。
- **未驗證**（待辦）：基本滲透測試 smoke test（主要任務，見 `docs/handoff-2026-07-24-pentest-baseline-and-kali-disabled.md` §3）；Docker runner image smoke（本機 Docker 故障）；2 個 kali CI（Runner Image digest 推廣、kind Integration）。
