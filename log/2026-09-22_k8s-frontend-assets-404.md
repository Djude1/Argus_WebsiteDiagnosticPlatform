# K8s 前端 nginx ConfigMap 補上 /assets/ =404（先前修錯地方）

**日期**：2026-09-22  
**操作者**：Claude

## 變更內容
- `k8s/05-frontend.yaml`：
  - `frontend-nginx` ConfigMap 的 `default.conf` 在 `location /` 之前補上 `location /assets/ { try_files $uri =404; }`，並註明與 `frontend/nginx.conf` 為同一條規則、兩邊必須同步。
  - frontend Deployment 的 pod template 新增 annotation `argus.io/nginx-conf-revision: "2"`。

## 原因
同日 commit `db6cecb` 把 `/assets/ =404` 加在 `frontend/nginx.conf`，但**那個檔案在 K8s 上根本沒被使用**：`k8s/05-frontend.yaml` 用 ConfigMap 以 `subPath` 掛載 `/etc/nginx/conf.d/default.conf`，完整覆蓋 image 內建設定（該檔開頭就寫著「用 ConfigMap 覆蓋 image 內建的 nginx.conf」）。因此實測正式站缺檔仍回 200 + HTML，修正等同死碼——當時只 grep 了 repo 內的 `nginx.conf`，沒查 k8s manifest。

新增 annotation 的理由：ConfigMap 以 `subPath` 掛載時掛載後不會同步更新，且 `k8s/kustomization.yaml` 用的是純 `resources:` 而非 `configMapGenerator`（沒有 name hash 可觸發滾動更新）。只改 ConfigMap 內容，既有 pod 不會重啟、設定不會生效。改用 annotation 讓 pod template 產生差異來觸發滾動重啟；註解已寫明「每次改 default.conf 都要把數字 +1」。

## 影響範圍
- 只動 `k8s/**`，依 CI 規則不會觸發 image build，由 Argo CD 直接套用 manifest。
- 會造成 frontend Deployment 一次滾動重啟（`replicas: 2`）。
- `frontend/nginx.conf` 的同條規則保留不動——它對本機 docker-compose 仍有效，兩份需保持同步。
- 本修正只防止未來滾動更新再污染 CDN；不影響已上線的 loader 動畫。

## 驗證方式
- `kubectl kustomize k8s` 渲染成功，共 40 個物件。
- `yaml.safe_load_all` 解析 `k8s/05-frontend.yaml` 通過，確認 ConfigMap 含該規則、Deployment annotation 為 `{'argus.io/nginx-conf-revision': '2'}`。
- 從**渲染結果**抽出 `default.conf`，掛進 nginx:alpine 實際起容器測試（需 `--add-host web:127.0.0.1`，因 k8s 版用靜態 upstream，啟動時即解析）：
  - `/assets/argus-eye-IXQvva_4.webp`（存在）→ 200 image/webp
  - `/assets/argus-eye-OLDHASH.webp`（缺檔）→ **404**
  - `/assets/missing-chunk.js`（缺檔）→ **404**
  - `/scans/42`（SPA 路由）→ 200 text/html
  - `/`（首頁）→ 200 text/html
  - （`/favicon.ico` 回 404 是測試用假 html root 未放 `favicon.svg` 所致，非迴歸）
- **待人工確認**：Argo 同步並滾動重啟後，對正式站一個不存在的 `/assets/xxx.js` 應回 404。

## 另附：本次已完成的事實
- 去背放大版 loader（commit `a6ff247`）已上線，端到端驗證線上資產 md5 與本機來源一致：`argus-eye-IXQvva_4.webp` = `ef269066…`、`argus-eye-still-0e27pH6_.webp` = `7254affe…`。
