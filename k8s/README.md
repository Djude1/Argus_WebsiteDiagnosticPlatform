# Argus k8s 部署

把 Argus 從 Docker Compose 搬到 PVE k8s（1 master + 2 worker）的 manifest。
image 由 GitHub Actions build 後推到 Docker Hub：`shijie85/argus-backend`、`shijie85/argus-frontend`。

> backend image 以 `uv sync --frozen --no-dev` 建立 `/app/.venv`。正式 Pod 必須使用 `/app/.venv/bin/python`、`/app/.venv/bin/gunicorn`、`/app/.venv/bin/celery` 的絕對路徑，不可依賴 image 是否已把 `.venv/bin` 加入 `PATH`；也不要改用 `uv run`，否則 uv 會在 runtime 嘗試解析與下載 dev dependency。
>
> web 的 HTTP readiness / liveness probe 固定送出 `Host: localhost`。Kubernetes 預設使用 Pod IP 作為 Host header，但正式環境的 `DJANGO_ALLOWED_HOSTS` 不應放寬到動態 Pod IP；`localhost` 已在允許清單內，可讓 probe 通過並保留 Host header 防護。

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

> 目前用 `:latest`。要可回滾改用 CI 產的 `sha-xxxxxxx` tag（把 04/05 的 image tag 換掉再 apply）。

## 尚未處理的待辦

1. **掃描 egress 隔離**：manifest 已限制 CoreDNS、資料服務與公開 IPv4/IPv6 80/443/587，並排除 private、loopback、link-local、metadata 與保留網段。仍必須在實際 CNI 執行上方封包矩陣；Compose/其他平台也需等效 firewall 或受控 proxy。
2. **Kali 主動攻擊鏈**：compose 的 `docker exec` 不適用 k8s containerd，需改成受控 Job；`attack` profile 預設不啟動。
3. **Google service account JSON**：若功能需要，另建 Secret 掛檔並設 `GOOGLE_APPLICATION_CREDENTIALS`，不得放進 image 或 repo。
4. **TLS / 網域**：Gateway 必須終止 HTTPS、清洗 `X-Forwarded-For/Proto`；frontend 只保留可信 Gateway 傳入的標頭。
5. **DB 連線數**：Gunicorn 目前每 pod 2 workers × 4 threads，且 `conn_max_age=0`。若出現 `too many clients already`，依實際併發調整 worker/thread 與 PostgreSQL 上限。
