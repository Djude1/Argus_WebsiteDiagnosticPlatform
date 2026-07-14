# Quality Gate 修復實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 main 分支 Quality Gate 的 favicon、IPv6 NetworkPolicy 測試與 workflow 契約漂移。

**Architecture:** Django 的 `/favicon.svg` 直接讀取被 Git 追蹤的 canonical `frontend/public/favicon.svg`，避免 backend CI 相依於未建置且被忽略的 `frontend/dist`。Kubernetes backend test 與 workflow assertion 統一使用已經正式 API 驗證的 `2000::/3` 及四個特殊用途排除前綴。

**Tech Stack:** Django、Python `unittest`、GitHub Actions、Kubernetes manifests

## Global Constraints

- 不複製 favicon 到 backend，避免同一資產產生兩份事實來源。
- 不變更已上線的 `k8s/07-network-policies.yaml` 行為，只修正過期測試與 workflow 契約。
- 每個修復先觀察正確失敗，再做最小修改並重跑完整 Quality Gate 等價命令。
- 同步 `backend/CLAUDE.md` 與當日 `log/`；push 前重新取得使用者明確同意。

---

### Task 1: 修復 backend CI favicon 404

**Files:**
- Modify: `backend/config/urls.py`
- Verify: `backend/apps/scans/tests.py`
- Modify: `backend/CLAUDE.md`

**Interfaces:**
- Consumes: tracked asset `frontend/public/favicon.svg`。
- Produces: Django `/favicon.svg` 回傳 SVG 及 `Cache-Control: no-cache`，不需要先 build frontend。

- [x] **Step 1: 確認既有回歸測試為 RED**

Run: `uv run --frozen python backend/manage.py test apps.scans.tests.HealthEndpointTests.test_favicon_is_served_as_static_asset_not_spa_html`

Expected: FAIL，`404 != 200`。

- [x] **Step 2: 讓 favicon route 使用 canonical public asset**

```python
FRONTEND_PUBLIC = settings.BASE_DIR.parent / "frontend" / "public"

path(
    "favicon.svg",
    _serve_no_cache,
    {"path": "favicon.svg", "document_root": FRONTEND_PUBLIC},
)
```

- [x] **Step 3: 驗證 favicon 測試轉為 GREEN**

Run: `uv run --frozen python backend/manage.py test apps.scans.tests.HealthEndpointTests`

Expected: 2 tests OK。

### Task 2: 同步 IPv6 NetworkPolicy 稽核契約

**Files:**
- Modify: `backend/apps/scans/tests_k8s_network_policy.py`
- Modify: `.github/workflows/quality.yml`

**Interfaces:**
- Consumes: `application-egress-boundary` 的 `2000::/3` desired/live contract。
- Produces: backend test 與 GitHub Kubernetes job 都拒絕舊 `::/0`／`::ffff:0:0/96`。

- [x] **Step 1: 保留 GitHub run 的 RED 證據**

Run: `gh run view 29313200523 --log-failed`

Expected: backend test 期望 `::/0`，Kubernetes job grep `cidr: ::/0`，兩者失敗。

- [x] **Step 2: 更新 backend manifest assertion**

```python
self.assertEqual(ipv6_block["cidr"], "2000::/3")
self.assertEqual(
    set(ipv6_block["except"]),
    {"2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20"},
)
```

- [x] **Step 3: 更新 workflow render assertion**

```bash
grep -q 'cidr: 2000::/3' "$RUNNER_TEMP/argus-rendered.yaml"
! grep -q 'cidr: ::/0' "$RUNNER_TEMP/argus-rendered.yaml"
! grep -q -- '::ffff:0:0/96' "$RUNNER_TEMP/argus-rendered.yaml"
```

- [x] **Step 4: 驗證 K8s backend test 與 render assertion**

Run:

```powershell
uv run --frozen python backend/manage.py test apps.scans.tests_k8s_network_policy
kubectl kustomize k8s
```

Expected: backend test OK；render 含 `2000::/3`，不含兩個舊字串。

### Task 3: 文件、完整驗證與提交準備

**Files:**
- Create: `log/2026-07-14_fix-quality-gate.md`
- Modify: `docs/superpowers/plans/2026-07-14-quality-gate-repair.md`

**Interfaces:**
- Consumes: 前兩項修復與 GitHub run 證據。
- Produces: 可審查、可重現且不含機密的提交。

- [x] **Step 1: 執行完整 Quality Gate 等價驗證**

Run:

```powershell
uv run --frozen ruff check backend
uv run --frozen python backend/manage.py check
uv run --frozen python backend/manage.py makemigrations --check --dry-run
uv run --frozen python backend/manage.py test apps
kubectl kustomize k8s
```

Expected: Ruff、Django check、migration 漂移、460 項 backend tests 與 Kustomize 全部 exit 0。

- [x] **Step 2: 依 MD checklist 與 Git 安全規範審查**

Run: `git diff --check`、`git diff`、`git status --short`。

Expected: 只有本計畫列出的檔案，無機密與無關變更。

- [x] **Step 3: 建立 SmallLoOwO commit，不 push**

Commit subject: `fix(ci): restore quality gate contracts`

Commit body:

```text
- serve favicon from the tracked frontend public asset
- align IPv6 NetworkPolicy checks with the API-valid CIDR
- document the failed-run evidence and verification
```
