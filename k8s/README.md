# Argus k8s 部署

把 Argus 從 Docker Compose 搬到 PVE k8s（1 master + 2 worker）的 manifest。
image 由 GitHub Actions build 後推到 Docker Hub：`shijie85/argus-backend`、`shijie85/argus-frontend`。

> backend image 以 `uv sync --frozen --no-dev` 建立 `/app/.venv`。正式 Pod 必須使用 `/app/.venv/bin/python`、`/app/.venv/bin/gunicorn`、`/app/.venv/bin/celery` 的絕對路徑，不可依賴 image 是否已把 `.venv/bin` 加入 `PATH`；也不要改用 `uv run`，否則 uv 會在 runtime 嘗試解析與下載 dev dependency。
>
> web 的 HTTP readiness / liveness probe 固定送出 `Host: localhost`。Kubernetes 預設使用 Pod IP 作為 Host header，但正式環境的 `DJANGO_ALLOWED_HOSTS` 不應放寬到動態 Pod IP；`localhost` 已在允許清單內，可讓 probe 通過並保留 Host header 防護。

## GitOps 實際流程與狀態判讀

1. push 到 `main` 後，Quality Gate 會檢查 backend、frontend、追蹤文字檔與 Kustomize manifests。
2. 改到 `backend/**`、`Dockerfile`、`pyproject.toml`、`uv.lock` 等 backend image 相依檔時，Backend Image workflow 才會 build / push image；`frontend/**` 由另一個 workflow 處理。只有 `k8s/**` 的變更不會建新 image。
3. image 成功推送後，workflow 才會用 `kustomize edit set image` 更新 `k8s/kustomization.yaml`，並由 `github-actions[bot]` 把 image tag commit 回 `main`。Build 失敗時不會有 write-back commit。
4. Argo CD 偵測 Git revision 後，是否自動套用取決於 Application 當下的 Auto Sync 設定；不可只看到 Git push 成功就宣稱部署完成。
5. backend Sync 會先執行 `migrate` PreSync Job，再 rollout web / worker。Argo UI 的容器 `Terminated` 只表示程序已結束：必須檢查 reason、exit code 與 logs，`Completed / 0` 才是成功。
6. cloudflared ingress / DNS 是 GitOps 之外的服務層；Git push、image build 或 Argo Sync 都不會自動修改 cloudflared 設定，操作方式見 [`../docs/cloudflared-guide.md`](../docs/cloudflared-guide.md)。

除錯時依序保留各層證據：source commit → Quality Gate → image build → write-back commit → Argo Sync / Health → migrate logs → Pod Ready / restart count → 公開 GET / API。任何一層失敗，都不可用前一層的成功取代。

## 檔案

| 檔案 | 內容 |
|---|---|
| `01-namespace-config.yaml` | `argus` namespace + 非機密環境變數 ConfigMap |
| `02-secret.example.yaml` | 機密**範本**（複製成 `secret.yaml` 填真值，勿 commit） |
| `03-data.yaml` | PostgreSQL（StatefulSet）、Redis、共享 `media` PVC（RWX/NFS） |
| `04-backend.yaml` | migrate Job + `web`（Gunicorn ×2）+ `worker`（Celery ×2） |
| `05-frontend.yaml` | nginx 前端（ConfigMap 覆蓋 nginx.conf）×2 + ClusterIP |
| `06-gateway.yaml` | Gateway API 對外入口（NGINX Gateway Fabric，class `nginx`） |
| `07-network-policies.yaml` | web/data ingress 白名單與 frontend/migrate/application/data egress 邊界（含 IPv4+IPv6 公網 allow / 私網 deny） |
| `09-ngf-client-settings.yaml` | NGF `ClientSettingsPolicy`：對齊 frontend nginx 的 `client_max_body_size 6m`，避免 NGF 資料平面回 413 |

## 前置（已就緒）

- **StorageClass**：已裝 NFS provisioner，`nfs-client` 為 default 且支援 **RWX**（`kubectl get sc` 確認）。`media` PVC 走 RWX → web/worker 可跨節點共用截圖；postgres PVC 走 nfs-client（RWO 單寫）。
  - ⚠ **postgres 跑在 NFS 有風險**：NFS 的 root_squash / 檔案鎖可能讓 initdb 失敗（權限）或運行不穩。若 `db-0` pod CrashLoop 報 `permission denied` / `could not create lock file`，把 postgres 的 PVC 改指向 block 儲存（local-path / Ceph RBD）——只有 `media` 需要 NFS 的 RWX，DB 不需要。
- **Gateway 控制器**：已裝 NGINX Gateway Fabric（GatewayClass `nginx`）。

## 部署步驟

```bash
# 1. namespace + 設定
kubectl apply -f 01-namespace-config.yaml

# 2. 機密：複製範本 → 填真值 → apply（secret.yaml 已被 .gitignore 排除）
cp 02-secret.example.yaml secret.yaml
#   至少改 POSTGRES_PASSWORD（兩處一致）、DJANGO_SECRET_KEY、JWT_SECRET_KEY、PASSWORD_RESET_TOKEN_PEPPER
kubectl apply -f secret.yaml
#   （或從既有 .env 建：kubectl -n argus create secret generic argus-secret --from-env-file=../.env）

# 3. 資料層，等 db ready
kubectl apply -f 03-data.yaml
kubectl -n argus rollout status statefulset/db

# 4. 後端：migrate Job 先跑，web/worker 用 initContainer 等 migrate 完成才起
kubectl apply -f 04-backend.yaml
kubectl -n argus wait --for=condition=complete job/migrate --timeout=300s
kubectl -n argus rollout status deploy/web
kubectl -n argus rollout status deploy/worker

# 5. 前端
kubectl apply -f 05-frontend.yaml
kubectl -n argus rollout status deploy/frontend

# 6. Gateway 對外入口
kubectl apply -f 06-gateway.yaml

# 7. 網路邊界（先確認下方 CoreDNS label 與 CNI enforcement）
kubectl apply -f 07-network-policies.yaml

# 8. NGF ClientSettingsPolicy（對齊 frontend nginx 的 client_max_body_size 6m）
kubectl apply -f 09-ngf-client-settings.yaml

# 檢查
kubectl -n argus get pods,svc,pvc
kubectl -n argus get gateway,httproute
kubectl -n argus get networkpolicy
kubectl -n argus get clientsettingspolicies.gateway.nginx.org
```

> ⚠ **不要用 `kubectl apply -f .` 套整個目錄**——那會把 `02-secret.example.yaml` 的佔位值一起套進去，蓋掉你真正的 `secret.yaml`。請照上面逐檔套用（web/worker 的 initContainer 會自動等 migrate Job 完成，套用順序不怕錯）。

## 對外存取（Gateway API）

```bash
kubectl -n argus get gateway argus-gateway     # 看 ADDRESS 與 PROGRAMMED=True
# NGINX Gateway Fabric 會為此 Gateway 佈署一個 nginx 資料平面 Service，查它的對外埠：
kubectl -n argus get svc                       # 找 argus-gateway 相關的 nginx service
```

- Service 是 **LoadBalancer** 且叢集有 MetalLB → 用配到的 `EXTERNAL-IP`。
- 沒有 MetalLB（LoadBalancer 卡 `<pending>`）→ 用它的 **NodePort**：`http://<任一節點IP>:<nodeport>`。

⚠ 拿到實際對外位址後，若用 `IP:port` 存取，要把來源補進 `01-namespace-config.yaml`（三個節點 IP 已預填，MetalLB VIP 或其他 IP 需自行加）：
- `DJANGO_ALLOWED_HOSTS`：加該 IP
- `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS`：加 `http://<IP>:<port>`
- `TRUSTED_PROXY_CIDRS`：必須改成叢集實際 Pod CIDR；目前 `10.0.0.0/8` 僅涵蓋常見 10.x 配置。web ingress NetworkPolicy 只允許 frontend pod 連入，代理仍必須覆寫 forwarded headers。

改完 `kubectl apply -f 01-namespace-config.yaml && kubectl -n argus rollout restart deploy/web`。

## NetworkPolicy 部署前檢查與封包驗證

`07-network-policies.yaml` 採最小白名單：

- frontend 只可連 web:8000 與 CoreDNS。
- migrate 只可連 PostgreSQL:5432 與 CoreDNS。
- web/worker 只可連 PostgreSQL、Redis、CoreDNS，以及排除內網/保留網段後的公開 IPv4 80/443/587。
- web/worker 另外允許 IPv6 global unicast `2000::/3` 的 80/443/587，並排除 IETF special-purpose `2001::/23`、兩段 documentation prefix（`2001:db8::/32`、`3fff::/20`）與 6to4；dual-stack 叢集若 CNI 支援 IPv6 NetworkPolicy，掃描目標 IPv6 endpoint 才會通。IPv6 `ipBlock.except` 不可混入 IPv4-mapped prefix，否則 API Server 會以位址族不一致拒絕整份 NetworkPolicy。
- PostgreSQL/Redis 不得主動 egress，且 ingress 只接受對應的 backend workload。

套用前先確認 CNI 支援 NetworkPolicy，且 CoreDNS 使用目前 selector：

```bash
kubectl -n kube-system get pods -l k8s-app=kube-dns --show-labels
kubectl get namespace kube-system --show-labels
```

若第一個命令找不到 Pod，或叢集使用 NodeLocal DNSCache，先依實際 DNS Pod label／精確 DNS IP 調整 policy；不要改回允許任意目的端的 53 port。

套用後可用受 policy 選取的暫時 worker Pod 驗證。以下「應阻擋」項目應 timeout 或連線失敗；若成功，代表 CNI 未執行 policy 或規則有缺口：

```bash
kubectl -n argus run egress-policy-check \
  --image=nicolaka/netshoot --restart=Never --labels=app=worker \
  --command -- sleep 3600
kubectl -n argus wait --for=condition=Ready pod/egress-policy-check --timeout=120s

# 應允許：CoreDNS、資料服務、公開 HTTPS
kubectl -n argus exec egress-policy-check -- nslookup example.com
kubectl -n argus exec egress-policy-check -- nc -vz -w 3 db 5432
kubectl -n argus exec egress-policy-check -- nc -vz -w 3 redis 6379
kubectl -n argus exec egress-policy-check -- curl -I --max-time 5 https://example.com

# 應阻擋：叢集 API、雲端 metadata、任意外部 DNS、節點／私網服務
kubectl -n argus exec egress-policy-check -- nc -vz -w 3 kubernetes.default.svc 443
kubectl -n argus exec egress-policy-check -- curl --max-time 3 http://169.254.169.254/
kubectl -n argus exec egress-policy-check -- dig @8.8.8.8 example.com +time=2 +tries=1
kubectl -n argus exec egress-policy-check -- nc -vz -w 3 <node-private-ip> 22

kubectl -n argus delete pod egress-policy-check --ignore-not-found
```

NetworkPolicy 是否真正阻擋封包取決於叢集 CNI；必要時搭配 CNI flow log 或節點側封包紀錄確認「應阻擋」測試沒有送達目的端。若未來使用叢集內 MinIO、私有 SMTP 或 egress proxy，應為該服務新增精準的 namespace/pod selector，不可放寬整段私網。

## 更新 image（CI 推了新版後）

```bash
kubectl -n argus delete job migrate     # Job 不可變，要重跑 migration 先刪再套
kubectl apply -f 04-backend.yaml
kubectl -n argus rollout restart deploy/web deploy/worker deploy/frontend
```

> `04-backend.yaml`／`05-frontend.yaml` 的 base manifest 使用 `:latest`，但 Argo CD 實際套用時由 `kustomization.yaml` 覆寫成 CI 產生的 `sha-xxxxxxx` tag；查正式版本應以 Kustomization 與 live workload 為準。

## 2026-07-14 驗證覆蓋與待驗證功能

以下是本輪 runtime、probe、NetworkPolicy 與 Quality Gate 修復的證據邊界；「已通過結構／單元測試」不代表新 image 已在正式叢集完成端到端驗證。

| 範圍 | 已有證據 | 目前邊界 |
|---|---|---|
| Quality Gate | [run 29316906689](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/actions/runs/29316906689) 的 backend、frontend、repository-text、kubernetes-manifests 全部成功 | 驗證的是 commit `420a296` 原始碼與 render 結果，不是新 backend image 的正式 rollout |
| Backend image | 品質閘門內的 Django tests / Ruff / check 成功；本機 Docker contract、`docker buildx build --check` 與修復後完整 image build 均通過；成品內 Gunicorn 23.0.0、Docker CLI 27.3.1、Nuclei 3.8.0、Katana 1.1.2 可啟動 | [run 29316906711](https://github.com/Djude1/Argus_WebsiteDiagnosticPlatform/actions/runs/29316906711) 仍是既有多行 `CMD` 的 parser 失敗紀錄，因此遠端尚無 `sha-420a296` image、沒有 write-back；本地修復仍須 push 後重跑 |
| Backend runtime / probes | root deployment contracts 驗證 `/app/.venv/bin/...` 與 `Host: localhost`；完整本機 image 的 production Gunicorn CMD 可解析且可執行；目前正式叢集 migrate 完成、web / worker / frontend Ready | 正式叢集仍運行既有 `sha-9f4f868` backend image，須在新 image write-back 後重新確認 migrate、web / worker rollout、restart count 與 probes |
| NetworkPolicy | Django manifest tests、Kustomize render、API Server server-side dry-run 與先前 Argo Sync 已通過 | 尚未從受 policy 選取的 Pod 執行完整允許／阻擋封包矩陣，公開 IPv6 target 也未做實際連線驗證 |
| favicon | Django 回歸測試與 Quality Gate 已確認 `/favicon.svg` 可從 tracked `frontend/public/favicon.svg` 讀取 | 尚未在新 backend image 與正式公開路由確認 status、Content-Type、內容與 cache header |
| Secret 啟動契約 | 正式叢集已補齊必要 key，先前 migrate / web 可啟動；測試環境覆蓋 password reset 邏輯 | 本輪未執行正式寄信、token link、確認頁與重設密碼的端到端流程；不得輸出 Secret 值來驗證 |
| Kali 主動攻擊鏈 | Kali / Hermes SQLi 的 25 項授權鎖與 Finding 契約測試通過；正式節點確認使用 containerd 2.2.5 | 正式 namespace 沒有 Kali workload；worker 沒有 Docker socket、連不上 daemon、沒有 sqlmap / msfconsole / nmap，且 `ARGUS_KALI_ENABLED` 未設定，因此目前 K8s 上不可執行 |

### 可能受影響、但本輪尚未完成正式實機測試

- **完整掃描主流程**：尚未用測試帳號與獲授權目標執行 `POST /api/scans/` → coin hold → Celery → Playwright / scanners → findings → completed / refund 的完整鏈路。
- **Celery worker 長時間狀態**：尚未觀察新 image 的 worker liveness、任務重試、取消、失敗回收與多 worker 併發。
- **實際 CNI egress enforcement**：尚未執行本文件的 CoreDNS、PostgreSQL、Redis、公開 IPv4 / IPv6 allow，以及 Kubernetes API、metadata、外部 DNS、節點私網 deny 矩陣。
- **密碼重設正式流程**：尚未驗證真實寄信、cloudflared / proxy 產生的 HTTPS link、token pepper 驗證與密碼更新。
- **新 backend image 的 GitOps 鏈**：尚未確認 Docker Hub push、bot write-back、Argo 新 revision Sync、PreSync migrate 與 web / worker 滾動更新。
- **Kali 主動攻擊鏈**：現行 `docker exec argus-kali-1` 只適用明確疊加 `docker-compose.attack.yml` 的隔離 Compose demo；K8s 必須另建受控 Job / Pod 執行模型與最小 RBAC，不能把 host Docker socket 掛進 production worker。
- **公開入口 smoke test**：新版本上線後仍需對三個公開網域執行首頁、`/api/health/live/`、`/api/health/ready/` 與 `/favicon.svg` 的 GET；HEAD 不能取代 GET。

## 尚未處理的待辦

1. **掃描 egress 隔離**：manifest 已限制 CoreDNS、資料服務與公開 IPv4/IPv6 80/443/587，並排除 private、loopback、link-local、metadata 與保留網段。仍必須在實際 CNI 執行上方封包矩陣；Compose/其他平台也需等效 firewall 或受控 proxy。
2. **Kali 主動攻擊鏈**：2026-07-14 實機確認三節點皆為 containerd 2.2.5，worker 僅有 Docker CLI、沒有 socket／daemon，也沒有 Kali 工具或啟用設定；現行 `docker exec` 鏈在 K8s 不可用，需改成受控 Job，且 `attack` profile 預設不啟動。
3. **Google service account JSON**：若功能需要，另建 Secret 掛檔並設 `GOOGLE_APPLICATION_CREDENTIALS`，不得放進 image 或 repo。
4. **TLS / 網域**：Gateway 必須終止 HTTPS、清洗 `X-Forwarded-For/Proto`；frontend 只保留可信 Gateway 傳入的標頭。
5. **DB 連線數**：Gunicorn 目前每 pod 2 workers × 4 threads，且 `conn_max_age=0`。若出現 `too many clients already`，依實際併發調整 worker/thread 與 PostgreSQL 上限。
