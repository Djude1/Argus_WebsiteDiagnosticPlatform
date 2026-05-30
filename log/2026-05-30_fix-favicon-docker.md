# 修正 Docker 頁面 Icon 顯示

**日期**：2026-05-30  
**操作者**：Codex

## 變更內容
- 新增 `frontend/public/favicon.svg` 作為瀏覽器分頁 favicon。
- 將 `frontend/index.html` 的 favicon link 從 PWA icon 改為專用 favicon。
- 在 `frontend/nginx.conf` 新增 `/favicon.ico` 與 `/favicon.svg` exact route，避免 SPA fallback 回傳 HTML。

## 原因
Docker nginx 對 `/favicon.ico` 原本會走 SPA fallback，回傳 `index.html`。瀏覽器收到的是 HTTP 200 但 `Content-Type: text/html`，因此分頁 icon 可能不顯示。

## 影響範圍
- Docker 前端 nginx 靜態檔服務。
- 瀏覽器分頁 favicon。

## 驗證方式
- `docker compose up -d --build frontend`：成功。
- `curl -I http://localhost:8080/favicon.ico`：回 200，`Content-Type: image/svg+xml`。
- `curl -I http://localhost:8080/favicon.svg`：回 200，`Content-Type: image/svg+xml`。
- `curl -I http://localhost:8080`：回 200。
