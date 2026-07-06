# Argus k8s 部署

把 Argus 從 Docker Compose 搬到 PVE k8s（1 master + 2 worker）的 manifest。
image 由 GitHub Actions build 後推到 Docker Hub：`shijie85/argus-backend`、`shijie85/argus-frontend`。

## 檔案

| 檔案 | 內容 |
|---|---|
| `01-namespace-config.yaml` | `argus` namespace + 非機密環境變數 ConfigMap |
| `02-secret.example.yaml` | 機密**範本**（複製成 `secret.yaml` 填真值，勿 commit） |
| `03-data.yaml` | PostgreSQL（StatefulSet）、Redis、共享 `media` PVC（RWX/NFS） |
| `04-backend.yaml` | migrate Job + `web`（runserver ×2）+ `worker`（celery ×2） |
| `05-frontend.yaml` | nginx 前端（ConfigMap 覆蓋 nginx.conf）×2 + ClusterIP |
| `06-gateway.yaml` | Gateway API 對外入口（NGINX Gateway Fabric，class `nginx`） |

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
#   至少改 POSTGRES_PASSWORD（兩處一致）、DJANGO_SECRET_KEY、JWT_SECRET_KEY
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

# 檢查
kubectl -n argus get pods,svc,pvc
kubectl -n argus get gateway,httproute
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

改完 `kubectl apply -f 01-namespace-config.yaml && kubectl -n argus rollout restart deploy/web`。

## 更新 image（CI 推了新版後）

```bash
kubectl -n argus delete job migrate     # Job 不可變，要重跑 migration 先刪再套
kubectl apply -f 04-backend.yaml
kubectl -n argus rollout restart deploy/web deploy/worker deploy/frontend
```

> 目前用 `:latest`。要可回滾改用 CI 產的 `sha-xxxxxxx` tag（把 04/05 的 image tag 換掉再 apply）。

## 尚未處理的待辦

1. **runserver → gunicorn**：`web` 目前跑 `runserver`（開發伺服器）。多執行緒、×2 replica 可運作，但非正式級（穩定性 / 效能 / 連線管理）。正式環境應換 gunicorn：`pyproject.toml` 加 gunicorn、重 build image、改 `04-backend.yaml` 的 command。（註：Django Admin 已在程式碼移除，故**沒有** admin 靜態檔失效問題。）
2. **NGF 上傳大小**：前端 nginx 設 `client_max_body_size 16m`，但 NGINX Gateway Fabric 資料平面預設 client body 上限較小。上傳大圖 / 報告若回 `413`，用 NGF 的 `ClientSettingsPolicy` 調高 `body.maxSize`。
3. **Kali 主動攻擊鏈**：compose 靠掛 `docker.sock` + `docker exec`，k8s（containerd）不適用，需改寫成 k8s Job / `kubectl exec`。預設 `attack` profile 不啟動，暫不影響。
4. **Google service account JSON**（`GoogleCloud_ApiKey.json`）：若啟用需要它的功能，另建 Secret 掛檔並設 `GOOGLE_APPLICATION_CREDENTIALS` 指向掛載路徑。
5. **TLS / 網域**：要 HTTPS，於 `06-gateway.yaml` 的 Gateway 加 HTTPS listener + cert-manager 簽憑證，HTTPRoute 補 `hostnames: [xn--gst.tw]`，並把網域 DNS 指到 Gateway 位址。
6. **DB 連線數**：postgres 預設 `max_connections=100`。web ×2（多執行緒 runserver）+ 前端高頻輪詢可能逼近上限（settings 已用 `conn_max_age=0` 緩解）。若 API 冒 `too many clients already`，調高 postgres `max_connections` 或改 gunicorn 綁定固定 worker 數。
