# 修復 K8s 正式容器的 uv runtime dependency sync

**日期**：2026-07-13

**操作者**：Codex

## 變更內容
- 將 `k8s/04-backend.yaml` 中 migrate、web、worker、兩個 initContainer 與 worker liveness probe 的六處正式命令改為直接使用 image PATH 內的 `python`、`gunicorn`、`celery`。
- 新增 `tests/test_k8s_runtime_commands.py`，防止 K8s backend manifest 再度使用 `uv run`。
- 更新 `k8s/README.md`，記錄正式 backend image 的 runtime command 契約。

## 原因
Argo CD PreSync `migrate` Pod 可穩定重現啟動失敗。previous container log 顯示 `uv run` 嘗試下載 dev dependency `ruff==0.15.13`，對 PyPI 請求三次逾時後退出；migration 本身尚未開始。Dockerfile 已用 `uv sync --frozen --no-dev` 安裝正式依賴，因此 runtime 不應再由 uv 解析 dependency。

## 影響範圍
- 僅影響 K8s backend 的 migrate、web、worker 啟動與 worker liveness probe。
- 不修改 Django migration、應用程式邏輯、Dockerfile 或 Docker Compose。
- 正式容器不再需要在啟動時連線 PyPI，既有 NetworkPolicy 不需放寬。

## 驗證方式
- `python tests/test_k8s_runtime_commands.py`：1 test，PASS；修改前已確認會因 `uv run` 存在而 FAIL。
- `kubectl kustomize k8s`：PASS，rendered manifest 不含 `uv run`，並包含 direct `python`、`gunicorn`、`celery`。
- `ruff check backend tests/test_k8s_runtime_commands.py`：PASS。
- `python backend/manage.py check`：0 issues。
- `python backend/manage.py test apps.accounts --verbosity 1`：18 tests，PASS。
- `python backend/manage.py test apps --verbosity 1`：460 tests，PASS。
- `frontend/build-node22.ps1`：使用 Node v22.22.3，Vite production build PASS，並產生測試所需的 `frontend/dist/favicon.svg`。
- Argo CD：已終止無效重試；舊版 web/worker 在修復部署前維持 Healthy。
