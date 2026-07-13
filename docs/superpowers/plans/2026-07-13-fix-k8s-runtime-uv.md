# K8s 正式容器避免 uv Runtime Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 Argus K8s 正式容器直接使用 image 內既有的 Python 執行檔，避免 `uv run` 在啟動時解析並下載 dev dependency。

**Architecture:** Dockerfile 已以 `uv sync --frozen --no-dev` 建立 `/app/.venv`，並把 `/app/.venv/bin` 放入 `PATH`。K8s 的 migrate、web、worker、initContainer 與 liveness probe 應直接呼叫 `python`、`gunicorn`、`celery`，不讓正式 runtime 再執行 dependency sync。

**Tech Stack:** Kubernetes manifests、Kustomize、Python `unittest`、Django、Docker image `shijie85/argus-backend`

## Global Constraints

- 只修改 K8s runtime commands，不修改 migration、Docker Compose 或應用邏輯。
- 不在正式 image 安裝 `ruff` 等 dev dependency。
- 不 push，直到使用者看過檔案清單、commit 訊息草稿與驗證結果並明確同意。
- 本次變更必須包含 `log/2026-07-13_fix-k8s-runtime-uv.md`。

---

### Task 1: 建立 K8s runtime command 回歸測試

**Files:**
- Create: `tests/test_k8s_runtime_commands.py`
- Test: `tests/test_k8s_runtime_commands.py`

**Interfaces:**
- Consumes: `k8s/04-backend.yaml` 的原始 YAML 文字
- Produces: 防止 production manifest 再度出現 `uv run` 的回歸測試

- [x] **Step 1: 寫入失敗測試**

```python
from pathlib import Path
import unittest


class K8sRuntimeCommandsTest(unittest.TestCase):
    def test_backend_manifest_does_not_run_uv_at_runtime(self):
        manifest = (
            Path(__file__).resolve().parents[1] / "k8s" / "04-backend.yaml"
        ).read_text(encoding="utf-8")

        self.assertNotIn('["uv", "run"', manifest)
        self.assertNotIn("uv run ", manifest)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: 執行測試確認 RED**

Run: `python tests/test_k8s_runtime_commands.py`

Expected: FAIL，訊息指出 `k8s/04-backend.yaml` 仍包含 `["uv", "run"` 或 `uv run `。

### Task 2: 讓 K8s 正式容器直接使用 image 內執行檔

**Files:**
- Modify: `k8s/04-backend.yaml:25`
- Modify: `k8s/04-backend.yaml:67`
- Modify: `k8s/04-backend.yaml:76`
- Modify: `k8s/04-backend.yaml:132`
- Modify: `k8s/04-backend.yaml:141`
- Modify: `k8s/04-backend.yaml:155`
- Test: `tests/test_k8s_runtime_commands.py`

**Interfaces:**
- Consumes: Dockerfile 提供的 `/app/.venv/bin` PATH
- Produces: 不需網路下載 dependency 的 migrate、web、worker 與 probe 命令

- [x] **Step 1: 實作最小命令替換**

```yaml
command: ["python", "manage.py", "migrate", "--noinput"]
command: ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120"]
command: ["celery", "-A", "config", "worker", "-l", "info"]
```

兩個 initContainer 的 shell command 改為 `python manage.py migrate --check`；worker liveness probe 改為 `celery -A config inspect ping ...`。

- [x] **Step 2: 執行測試確認 GREEN**

Run: `python tests/test_k8s_runtime_commands.py`

Expected: PASS（1 test）。

- [x] **Step 3: 渲染 Kustomize**

Run: `kubectl kustomize k8s`

Expected: exit code 0，輸出包含 direct `python`、`gunicorn`、`celery`，且不含 `uv run`。

### Task 3: 同步部署文件與任務紀錄

**Files:**
- Modify: `k8s/README.md`
- Create: `log/2026-07-13_fix-k8s-runtime-uv.md`
- Modify: `docs/superpowers/plans/2026-07-13-fix-k8s-runtime-uv.md`

**Interfaces:**
- Consumes: Task 2 的最終 runtime 行為與驗證結果
- Produces: 可供後續部署與接手者查證的操作說明

- [x] **Step 1: 更新 K8s README**

在 backend image 說明中記錄：正式 Pod 直接使用 image `.venv/bin` 中的執行檔，不得用 `uv run` 觸發 runtime dependency sync。

- [x] **Step 2: 建立任務 log**

依 `docs/log-template.md` 記錄 root cause、六處 manifest 修改、影響範圍與實跑驗證。

- [x] **Step 3: 完成驗證**

Run:

```powershell
python tests/test_k8s_runtime_commands.py
kubectl kustomize k8s
uv run ruff check backend
uv run python backend/manage.py check
uv run python backend/manage.py test apps.accounts
git diff --check
```

Expected: 全部 exit code 0；MD 核對無失效連結、矛盾或未同步事實。

### Task 4: 準備人工核准的 commit／push 交接

**Files:**
- Review only: `k8s/04-backend.yaml`
- Review only: `tests/test_k8s_runtime_commands.py`
- Review only: `k8s/README.md`
- Review only: `log/2026-07-13_fix-k8s-runtime-uv.md`
- Review only: `docs/superpowers/plans/2026-07-13-fix-k8s-runtime-uv.md`

**Interfaces:**
- Consumes: 完整 diff 與驗證輸出
- Produces: 使用者可核准的檔案清單、commit 訊息草稿與 push 請求

- [x] **Step 1: 檢查工作區與 diff**

Run: `git status --short && git diff --check && git diff -- k8s/04-backend.yaml tests/test_k8s_runtime_commands.py k8s/README.md log/2026-07-13_fix-k8s-runtime-uv.md docs/superpowers/plans/2026-07-13-fix-k8s-runtime-uv.md`

Expected: 只有本計畫列出的五個檔案有變更，沒有 whitespace error 或敏感資訊。

- [x] **Step 2: 向使用者請求明確 push 同意**

Commit message draft:

```text
fix(k8s): prevent uv dependency sync in production pods

- run migrate, gunicorn and celery directly from image PATH
- add regression coverage for K8s runtime commands
- document the production runtime contract and verification evidence
```

在取得使用者明確「推」之前，不執行 commit 或 push。
