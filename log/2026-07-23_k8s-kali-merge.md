# Merge K8s Kali SQLmap 攻擊鏈（Task 1-10，維持 disabled）

**日期**：2026-07-23  
**操作者**：Claude

## 變更內容
- 將 `codex/docs-deployment-handoff`（commit `b87c5ce..d637add`，18 commits）的 K8s Job-based kali 攻擊鏈 merge 進 `feat/kali-k8s-integration`（基於 main `e60a953`）。
- 新增 `backend/apps/scans/security/kali_contracts.py`、`kali_policy.py`、`kali_kubernetes.py`；`kali-runner/`（pinned SQLmap runner image）；`k8s/10-kali-runtime.yaml`、`k8s/11-kali-admission.yaml`；`docs/runbooks/kali-sqlmap-rollout.md`、`kubernetes-secret-at-rest-encryption.md`；以及 `tests_kali_*` 系列測試。
- `backend/apps/scans/tasks.py` 融合：kali 從 security 掃描前的舊位置，移至 agent 之後的 Hermes-first fallback；保留 main 的 `tested_categories` scoring、`fail_scan_job_before_start` Celery 修復與 `deep_scan_total` 進度條。
- `AGENTS.md` 採 main 跨 Agent 雙入口版，補入 codex 的「K8s / GitOps 操作底線」段落（OpenCode 委派屬個人偏好，不納入）。
- `k8s/README.md` 採 codex 版（完整驗證矩陣），補回 main 的「獲取資料庫密碼」指令。
- `backend/apps/scans/tests_kali_pipeline.py`：mock `calculate_scores` 的 `_capture` 加 `tested_categories` 參數，對齊 main 新 signature（doc-sync 適配，不改測試意圖）。

## 原因
使用者反映「K8s 環境無法使用 kali 掃描」。根因：main 的 kali 為 Docker-based（`docker exec argus-kali-1`），與 K8s containerd 不相容；真正能在 K8s 跑的 Job-based kali 鏈（codex 完成 Task 1-10）尚未 merge。本 merge 把 K8s-compatible kali 軟體納入 main，維持 disabled 直到 Task 11 手動控制平面 gate。

## 影響範圍
- kali 預設完全 inert：`ARGUS_KALI_ENABLED=false`、`ARGUS_KALI_BACKEND=disabled`、runner image 為 sentinel `sha256:0000…`。正式環境不會觸發任何 kali Job。
- 新相依：`kubernetes>=35.0,<36`（`uv sync` 已安裝 35.0.0）。
- 啟用屬 Task 11 手動 gate（Secret 靜態加密 + RBAC/Admission/Network 實機驗證 + 翻旗標 + 授權 positive test），本次未執行。

## 驗證方式
- `uv run ruff check backend scripts`：All checks passed。
- `uv run python backend/manage.py check`：0 issues（注入 CI-only env var）。
- `uv run python backend/manage.py test apps.scans apps.agent`：453 tests OK（skipped=1，Redis 測試）。
- `uv run python -m unittest discover -s tests`：36 OK。
- `uv run python -m unittest discover -s kali-runner/tests`：38 OK。
- `uv run python scripts/promote_kali_image.py --check`：exit 0。
- `kubectl kustomize k8s`：render OK。
- 待驗證（需 K8s 叢集／Docker，本機跑不了）：`kubectl apply --dry-run=server`、`kubectl auth can-i`、Docker runner image smoke。
