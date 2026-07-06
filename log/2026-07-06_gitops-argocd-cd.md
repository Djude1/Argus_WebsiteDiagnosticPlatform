# GitOps CD（Kustomize + CI write-back，供 Argo CD）+ 網路/入口強化

## 變更內容

**GitOps CD 管線（本次重點）：**
- 新增 `k8s/kustomization.yaml`：Argo CD 的進入點，把 image 版本集中在 `images:` 一處管理。只納入 argus namespace 那批（01/03/04/05/06），排除 `02-secret.example.yaml`（佔位）、`secret.yaml`（gitignored）、`08-nginxproxy.yaml`（NGF helm 管、不同 namespace）。
- `build-frontend.yml` / `build-backend.yml` 加 **GitOps write-back**：build+push 後用 `kustomize edit set image` 把該次 commit 的 `sha-<7碼>` 寫回 `kustomization.yaml`，commit + push 回 repo。
  - 加 `permissions: contents: write`、checkout `fetch-depth: 0`。
  - 防迴圈：build workflow 的 `paths` 不含 `k8s/**`，且 `GITHUB_TOKEN` 產生的 commit 不觸發 workflow（GitHub 內建防遞迴）。
- `04-backend.yaml` 的 migrate Job 標成 **Argo PreSync hook**（`argocd.argoproj.io/hook: PreSync` + `hook-delete-policy: BeforeHookCreation`），避開「Job spec 不可變」在 image bump 時的同步衝突。`kubectl` 會忽略這兩個 annotation，本地直接 apply 不受影響。

**入口 / 網路（部分為叢集 runtime 設定，manifest 對應如下）：**
- `08-nginxproxy.yaml`：NGF 資料平面（gateway nginx）開 2 副本，入口跨 worker1/worker2、不再單點。
- MetalLB（叢集內裝，pool `172.16.2.200`）給 `argus-gateway-nginx` 一顆 VIP，取代 NodePort。
- `01-namespace-config.yaml`：加對外域名 `argus.clouda.dpdns.org`（ALLOWED_HOSTS/CSRF/CORS）、Redis throttle cache（`DJANGO_CACHE_*`，多 replica 共用計數）、三個節點 IP、agent 啟用。

**穩定性修正：**
- postgres StatefulSet 加 `startupProbe`（防 NFS 慢 initdb 被 liveness 中斷成半殘資料目錄）。

## 原因

原本推新 image 到 Docker Hub 後 k8s 不會自動更新（k8s 盯 git/spec、不盯 registry）。改採正統 GitOps：CI 把版本寫回 git → Argo CD（下一步安裝）盯 git 自動同步部署，可追溯、可回滾。

## 影響範圍

- 純新增部署/CI 設定，不動應用程式碼、不影響 Docker Compose 流程。
- **前置**：GitHub repo Settings → Actions → Workflow permissions 需設「Read and write permissions」，否則 CI write-back 的 push 會 403。
- 真機密仍走 gitignored `secret.yaml`，需手動 apply 一次（Argo CD 不管它）。

## 驗證方式

- 兩個 workflow 與 `04-backend.yaml` 以 PyYAML 解析通過；確認 `permissions: contents:write`、checkout `fetch-depth:0`、write-back 步驟、migrate Job 的 Argo hook annotations 皆到位。
- **待使用者手動**：設好 repo 寫入權限 → 裝 Argo CD → 建 Application（path `k8s`）→ 手動 apply secret.yaml → 驗證推程式碼後自動部署。
