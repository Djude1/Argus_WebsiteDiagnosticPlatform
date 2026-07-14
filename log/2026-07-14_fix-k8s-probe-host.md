# 修復 K8s web probe Host header

**日期**：2026-07-14
**操作者**：Codex

## 變更內容

- 在 `k8s/04-backend.yaml` 的 web readiness 與 liveness HTTP probes 加入 `Host: localhost`。
- 將 IPv6 egress `ipBlock` 收斂為 `2000::/3`，移除 API Server 不接受的 IPv4-mapped exclusion，並保留同位址族的特殊用途排除。
- 新增回歸測試，要求兩個 web HTTP probes 都保留允許的 Host header。
- 新增回歸測試，要求 IPv6 egress 使用合法的 global-unicast CIDR，且不得包含 `::ffff:0:0/96`。
- 同步 `k8s/README.md`，記錄 probe 與 Django `ALLOWED_HOSTS` 的安全契約。

## 原因

正式叢集 rollout 到 Gunicorn image `sha-9f4f868` 時，Kubernetes probe 以 Pod IP 作為 Host header，Django 在 `DJANGO_DEBUG=false` 下依 `ALLOWED_HOSTS` 回傳 HTTP 400，造成新版 Pod liveness 重啟並阻塞 Argo CD Sync。實測同一 Pod 使用 Pod IP Host 回 400，使用 `Host: localhost` 回 200。

修復 Secret 與 migrate 後，Argo CD 又被 `application-egress-boundary` 阻塞：API Server 判定 `::ffff:0:0/96` 不是 IPv6 `::/0` 的合法 strict subset。改用 `2000::/3` 可直接表達公開 global-unicast 邊界，也避免在 IPv6 `ipBlock` 混入會被正規化為 IPv4 的 mapped prefix；依 IANA registry 另排除 `2001::/23`、`2001:db8::/32`、`2002::/16` 與 `3fff::/20`。

## 影響範圍

- 影響 `argus` namespace 的 web Deployment probes，以及 web/worker 的公開 IPv6 egress CIDR。
- 不放寬 `DJANGO_ALLOWED_HOSTS`，不影響公開網域、API 路由或 worker。
- IPv6 egress 由近似全域 `::/0` 排除清單收斂為 IANA global-unicast `2000::/3`，安全邊界更精準。
- manifest 更新 push 後需重新執行 Argo CD Sync，才能讓正式叢集套用。

## 驗證方式

- `uv run python tests/test_k8s_runtime_commands.py`：4 項通過。
- `uv run ruff check tests/test_k8s_runtime_commands.py`：通過。
- `kubectl kustomize k8s`：完整渲染成功，兩個 web probes 都含 `Host: localhost`。
- `uv run python backend/manage.py check`（注入測試用必要環境變數）：0 issues。
- `kubectl apply --dry-run=server -f -`（正式叢集 API）：全部資源通過，包含 `application-egress-boundary` NetworkPolicy。
- 正式叢集 rollout 後確認 migrate Job 完成、web/worker/frontend Ready、Argo Sync 成功與公開首頁 GET 回 200。
