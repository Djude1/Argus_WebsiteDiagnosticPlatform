# 2026-06-19 修復公網 API 全 502（nginx 上游 IP 快取）+ 部署合併後新碼

## 變更內容

1. **`frontend/nginx.conf`**：加 `resolver 127.0.0.11 valid=10s ipv6=off;` + `set $web_upstream web;`，
   4 個 proxy_pass（`/api/`、`/django-admin/`、`/media/`、`/static/`）全改 `http://$web_upstream:8000;`，
   讓 nginx 每次請求重新解析 `web` 容器 IP，而非啟動時記死。
2. **`.gitignore`**：新增 `backups/`（pg_dump 含真實使用者個資，絕不可推上公開 repo）。

## 原因（root cause）

公網 `argus6.qzz.io` / `巧.tw` 首頁 200 但**所有 `/api/` 回 502，已壞約 6 天**。
排查確認：frontend(nginx) 比 web 早約 2.5h 啟動，`proxy_pass http://web:8000;` 無 `resolver`/`upstream`
→ nginx 只在啟動當下解析一次 `web` IP 並寫死；web 容器後來重建換 IP（172.19.0.5），nginx 仍連舊 IP
→ connection failed → 502。busybox wget 每次重查 DNS 所以連得到，造成「手動連得到、nginx 連不到」的矛盾。

## 影響範圍

- 公網 API 從 6 天前的中斷恢復；未來 web 容器再重啟/重建也不會復發此 502。
- 同時把 git 分岔合併後的後端新碼（SRI/DNS/Kali + exposure/secret）與前端 UI 部署上線。

## 處置與驗證方式

- **即時止血**：`docker compose exec frontend nginx -s reload`（reload 後公網 /api 立即 200）。
- **永久修法**：改 nginx.conf 如上 → 拋棄式 `nginx:alpine` 容器跑 `nginx -t` 驗證語法 OK。
- **部署**：`docker compose up -d --build web worker frontend`（**只動這三個，不碰 db、無 `-v`**）。
  - 動手前先 `pg_dump` 全庫備份（`backups/`，51.8 MB / 30 表）。
  - 部署後容器：db/redis/kali 維持 Up 9 天未重建；web/worker/frontend 為新建。
  - web log：`accounts.0003_passwordresettoken... OK`、System check 0 issues、Django 啟動。
  - **資料筆數零變動**：users 21 / scan_jobs 42 / findings 3659 / coin_txns 125 / wallets 21（部署前後一致）。
  - 永久修法生效驗證：web 重建換 IP 後公網 `/api/` 仍 200（不再 502）。
  - worker 容器實跑 `analyze_dns('argus6.qzz.io')` 回 3 筆 finding（SPF/DMARC/DNSSEC 缺失），
    證明 `dnspython` 與新掃描器在生產環境可運作。

## 待辦 / 後續

- 永久修法的 nginx.conf 之前是在工作區直接 build（線上已生效），本 commit 補進 git。
- nginx `proxy_pass` 變數化後若未來要再調 location，注意維持 `resolver` 在 server 區塊內。
