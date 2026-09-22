# frontend nginx：/assets/ 缺檔改回 404，避免被 CDN 快取成 HTML

**日期**：2026-09-22  
**操作者**：Claude

## 變更內容
- `frontend/nginx.conf`：在 SPA fallback 的 `location /` 之前新增 `location /assets/ { try_files $uri =404; }`，讓 Vite 產出的 hashed 資產缺檔時回 404，不再落入 `try_files $uri $uri/ /index.html`。

## 原因
承接同日「Argus 之眼 loader」上線時踩到的實際事故：rollout 尚未完成的空窗期內，對新 chunk（`argus-loader-*.webp`、`ScanExperience-*.js`）的請求在 origin 上還找不到檔案，被 SPA fallback 以 **200 + text/html** 回應。Cloudflare 是依副檔名（`.js` / `.webp` 等）決定是否快取、不檢查 content-type，於是把那份 HTML 當成該資產存了下來（實測 `cf-cache-status: HIT`、`cache-control: max-age=14400`），即使 rollout 完成、真檔案已就位，CDN 仍持續餵錯誤內容達 4 小時。

hashed 檔名本來就是「檔名即版本」，缺檔的正確語意是 404 而非首頁。同檔案的 favicon 區塊早已用 `try_files ... =404` 處理過同一類問題（註解寫著「避免 SPA fallback 回 HTML」），本次只是把同樣作法補到 `/assets/`。

## 影響範圍
- 只影響 frontend image 內 nginx 對 `/assets/` 的處理；SPA 路由（`/scans/:id` 等）的 fallback 行為不變。
- 此修正是**預防下一次**滾動更新再污染 CDN；對已經存進 Cloudflare 的錯誤快取無效，那些仍須 purge 或等 TTL 過期。
- 會觸發一次 frontend image rebuild 與 rollout。

## 驗證方式
- `docker run nginx:alpine nginx -t` → syntax is ok / test is successful。
- 以 nginx:alpine 掛載本設定與假的 html root 實際起容器測 6 個案例，全部符合預期：
  - `/assets/real-ABC123.js`（存在）→ 200 application/javascript
  - `/assets/real-image-XYZ.webp`（存在）→ 200 image/webp
  - `/assets/missing-DEAD00.js`（缺檔）→ **404**（修正前會是 200 + HTML）
  - `/assets/argus-loader-GONE.webp`（缺檔）→ **404**
  - `/scans/123`（SPA 路由）→ 200 text/html（fallback 正常）
  - `/`（首頁）→ 200 text/html
- **待人工確認**：rollout 後在正式站對一個不存在的 `/assets/xxx.js` 打一次，應回 404。
