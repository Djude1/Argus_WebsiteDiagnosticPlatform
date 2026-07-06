# k8s manifests：從 Docker Compose 遷移到 PVE k8s 並實機部署成功

## 變更內容

新增 `k8s/` 目錄，把 Docker Compose 的 Argus 翻成 k8s 宣告式部署：

| 檔案 | 內容 |
|---|---|
| `01-namespace-config.yaml` | `argus` namespace + 非機密 env ConfigMap |
| `02-secret.example.yaml` | 機密**範本**（佔位值，可 commit） |
| `03-data.yaml` | postgres StatefulSet + redis + 共享 media PVC |
| `04-backend.yaml` | migrate Job + web（runserver ×2）+ worker（celery ×2） |
| `05-frontend.yaml` | nginx 前端（ConfigMap 覆蓋 nginx.conf）×2 + ClusterIP |
| `06-gateway.yaml` | Gateway API 對外入口（NGINX Gateway Fabric，class `nginx`） |
| `.gitignore` / `README.md` | 排除真實 `secret.yaml` / 部署說明 |

真實機密放 gitignored 的 `k8s/secret.yaml`（**不進 git**）。

## 關鍵設計決策

- **儲存 NFS(RWX)**：`nfs-client` 為 default SC 且支援 ReadWriteMany。media PVC 走 RWX → web/worker 可跨節點共用截圖，無需 podAffinity。postgres PVC 走 nfs-client(RWO)。
- **replicas=2**：web/worker/frontend 各 2。因 replicas>1 不能讓每個 web pod 各自 migrate → 抽成單次 **migrate Job**，web/worker 用 initContainer `migrate --check` 迴圈等 migrate 完成才啟動（寫入單點化、其他人唯讀等待）。
- **對外走 Gateway API**：NGINX Gateway Fabric（GatewayClass `nginx`）。Gateway(HTTP:80) + HTTPRoute(無 hostname，全導 frontend:80)。無 MetalLB → LB Service EXTERNAL-IP pending，用其 NodePort（本次 30212）。
- **前端 nginx.conf 用 ConfigMap 覆蓋**：image 內建版寫死 Docker 專用 `resolver 127.0.0.11`，k8s 會解析不到 web；改靜態 `proxy_pass http://web:8000`（Service ClusterIP 穩定），不動 image、不影響 compose。
- **Redis 當 throttle cache**：ConfigMap 設 `DJANGO_CACHE_BACKEND=RedisCache` + `LOCATION=redis://redis:6379/2`，讓多 replica 共用 rate-limit 計數（否則 LocMemCache per-process 失準）。

## 實機踩雷與修正

**postgres 在 NFS 上 initdb 被 liveness 中斷 → 半殘資料目錄**：
- 症狀：migrate 報 `database "argus" does not exist` + `no pg_hba.conf entry for user argus`，db-0 RESTARTS≥1。
- 成因：NFS 上 initdb 慢，被 liveness（原 initialDelay 20s）在「建 argus role/db」前殺掉；重啟後 PGDATA 非空 → entrypoint 跳過初始化 → 永久半殘（`POSTGRES_*` 只在首次空目錄生效）。
- 修正：postgres 加 `startupProbe`（pg_isready，failureThreshold 60×5s≈5 分鐘）擋住 liveness 直到 init 完成。復原：`kubectl -n argus delete statefulset db && delete pvc data-db-0` 清 NFS 資料後重套。

## 影響範圍

- 純新增 k8s 部署設定，不影響既有程式碼與 Docker Compose 流程。
- 需使用者手動建立 gitignored `secret.yaml`（真金鑰）；`.env` 的本機專用值（sqlite/DEBUG=true/localhost）不可照抄，k8s 用 postgres/false/service 名。

## 驗證方式

- 6 個 manifest YAML 以 PyYAML `safe_load_all` 解析 — 全通過。
- 實機 `kubectl apply` 全部套用；修正 postgres 初始化後：全 pod Running、`migrate` Job Completed、`psql \l` 確認 argus role/db 建立。
- Smoke test：`curl http://172.16.2.122:30212/` = **200**、`/api/content/features/` = **200**（整條 Gateway→frontend→web→postgres 打通）。

## 待辦（未阻擋，公開前處理）

- runserver → gunicorn；改強 superuser（現 1124/1124）；輪換金鑰；TLS（Gateway 加 HTTPS listener + cert-manager）；Kali 攻擊鏈改寫。
