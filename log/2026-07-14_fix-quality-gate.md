# 修復 Quality Gate 契約漂移

**日期**：2026-07-14
**操作者**：Codex

## 變更內容

- Django `/favicon.svg` 改為服務被 Git 追蹤的 `frontend/public/favicon.svg`，backend CI 不再依賴未建置的 `frontend/dist`。
- 更新 backend NetworkPolicy 測試，要求 IPv6 egress 使用 `2000::/3` 及四個同位址族排除前綴。
- 更新 GitHub Kubernetes manifest job，拒絕舊 `::/0` 與 `::ffff:0:0/96`。
- 同步 backend 路由文件與實作計畫。

## 原因

GitHub Actions Quality Gate run `29313200523` 的 backend job 在 460 tests 中失敗 2 項：favicon 因 backend job 不會先 build frontend 而回 404；NetworkPolicy 測試仍期望已被正式 API Server 拒絕的舊 IPv6 契約。`kubernetes-manifests` job 也仍 grep 舊 `cidr: ::/0`，因此即使 Kustomize 渲染成功仍回傳失敗。

favicon 的 canonical source 已存在於 `frontend/public/favicon.svg`。直接由 Django 服務該 tracked asset 可避免重複一份 backend favicon，也讓 backend tests 不依賴另一個平行 CI job 的 build artifact。

## 影響範圍

- 影響 Django 開發／測試環境的 `/favicon.svg` 來源，不改變圖示內容。
- 影響 backend 與 Kubernetes Quality Gate assertion，不改變已上線的 NetworkPolicy 行為。
- 不修改 Secret、image tag、Argo Auto Sync 或資料庫 schema。

## 驗證方式

- favicon RED：`404 != 200`；修正後 `HealthEndpointTests` 2 項通過。
- NetworkPolicy RED：`'2000::/3' != '::/0'`；修正後該模組 5 項通過。
- Kustomize workflow 等價 assertion：包含 `2000::/3`，不含舊 `::/0` 與 `::ffff:0:0/96`。
- `uv run --frozen ruff check backend`：通過。
- `backend/manage.py check`：0 issues；`makemigrations --check --dry-run`：No changes detected。
- `backend/manage.py test apps`：460 項全部通過，0 failures。
- root K8s runtime contract：4 項通過。
