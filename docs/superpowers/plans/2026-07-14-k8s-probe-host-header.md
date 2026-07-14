# K8s Probe Host Header 修復實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復阻塞正式 Argo Sync 的 web probe Host header 與不合法 IPv6 NetworkPolicy CIDR。

**Architecture:** 保留嚴格的 `DJANGO_ALLOWED_HOSTS`，只在 `k8s/04-backend.yaml` 的兩個 web HTTP probe 加入 `Host: localhost`。IPv6 egress 改用 Kubernetes 可接受且更精準的 global-unicast `2000::/3`，只保留同位址族的特殊用途排除；以文字契約測試鎖定兩項部署契約，並同步 K8s 操作文件與任務 log。

**Tech Stack:** Kubernetes manifests、Django、Python `unittest`、Argo CD

## Global Constraints

- 不放寬 `DJANGO_ALLOWED_HOSTS`。
- 不修改或輸出 Kubernetes Secret 值。
- 不開啟 Argo CD Auto Sync；push 前取得使用者明確同意。
- 前端不在本次範圍，不執行前端 build。

---

### Task 1: 鎖定並修復 probe Host header

**Files:**
- Modify: `tests/test_k8s_runtime_commands.py`
- Modify: `k8s/04-backend.yaml`
- Modify: `k8s/README.md`
- Create: `log/2026-07-14_fix-k8s-probe-host.md`

**Interfaces:**
- Consumes: Django `ALLOWED_HOSTS` 預設包含 `localhost`，Kubernetes HTTP probe 支援 `httpHeaders`。
- Produces: readiness／liveness probe 都送出 `Host: localhost` 的 manifest 契約。

- [x] **Step 1: 新增失敗回歸測試**

```python
def test_web_http_probes_use_allowed_host_header(self):
    manifest = (
        Path(__file__).resolve().parents[1] / "k8s" / "04-backend.yaml"
    ).read_text(encoding="utf-8")

    for probe, path in (
        ("readinessProbe", "/api/health/ready/"),
        ("livenessProbe", "/api/health/live/"),
    ):
        expected_probe = (
            f"          {probe}:\n"
            "            httpGet:\n"
            f"              path: {path}\n"
            "              port: 8000\n"
            "              httpHeaders:\n"
            "                - name: Host\n"
            "                  value: localhost"
        )
        self.assertIn(expected_probe, manifest)
```

- [x] **Step 2: 執行測試並確認因缺少 header 失敗**

Run: `uv run python tests/test_k8s_runtime_commands.py`

Expected: `test_web_http_probes_use_allowed_host_header` FAIL，實際數量為 0。

- [x] **Step 3: 對兩個 web HTTP probes 加入 Host header**

```yaml
httpHeaders:
  - name: Host
    value: localhost
```

- [x] **Step 4: 同步文件與任務 log**

在 `k8s/README.md` 說明 HTTP probe 固定使用 `Host: localhost`，避免 Pod IP 被 Django 拒絕；依 `docs/log-template.md` 建立當日 log。

- [x] **Step 5: 完整驗證**

Run:

```powershell
uv run python tests/test_k8s_runtime_commands.py
uv run ruff check tests/test_k8s_runtime_commands.py
kubectl kustomize k8s
$env:DJANGO_SECRET_KEY='test-secret-for-check-only-32bytes-padding'
$env:PASSWORD_RESET_TOKEN_PEPPER='test-reset-pepper-only-for-system-check'
$env:JWT_SECRET_KEY='test-jwt-32bytes-padding-for-hmac'
$env:DJANGO_DEBUG='true'
uv run python backend/manage.py check
```

Expected: 測試、Ruff、Kustomize render、Django check 全部 exit 0。

### Task 2: 修復 IPv6 NetworkPolicy server-side validation

**Files:**
- Modify: `tests/test_k8s_runtime_commands.py`
- Modify: `k8s/07-network-policies.yaml`
- Modify: `k8s/README.md`
- Modify: `log/2026-07-14_fix-k8s-probe-host.md`

**Interfaces:**
- Consumes: Kubernetes `ipBlock.except` 必須是同位址族且為 `cidr` 的 strict subset。
- Produces: 以 `2000::/3` 表示公開 IPv6 global unicast，排除 IETF special-purpose、documentation 與 6to4 前綴。

- [x] **Step 1: 新增失敗測試**

測試要求 manifest 包含 `cidr: 2000::/3`，且不包含 `cidr: ::/0` 或 `::ffff:0:0/96`。

- [x] **Step 2: 確認測試因現有不合法 CIDR 失敗**

Run: `uv run python tests/test_k8s_runtime_commands.py`

Expected: IPv6 egress 測試 FAIL。

- [x] **Step 3: 最小修正 IPv6 ipBlock 與文件**

把 `cidr: ::/0` 改為 `cidr: 2000::/3`，排除 `2001::/23`、`2001:db8::/32`、`2002::/16`、`3fff::/20`，並同步 README／log。

- [x] **Step 4: 執行本地與 server-side 驗證**

重跑 Python 測試、Ruff、Kustomize render、Django check，再把 render 結果送到正式 API Server 執行 `kubectl apply --dry-run=server -f -`，不得實際套用。

- [x] **Step 5: 檢查文件、diff 與提交**

依 `docs/md-checklist.md` 檢查連結／一致性，執行 `git diff --check` 與 `git diff`；只 stage 本計畫列出的檔案並建立精確 commit，不 push。
