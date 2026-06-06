# 開放 PostgreSQL 給 Navicat

**日期**：2026-05-30  
**操作者**：Codex

## 變更內容
- 在 `docker-compose.yml` 的 `db` 服務新增 `ports: "5432:5432"`。
- 重新執行 `docker compose up -d db web worker`，讓 PostgreSQL 對主機開放本機開發連線。

## 原因
使用者使用 Navicat 連 `localhost:5432` 時得到 connection refused。檢查 `docker compose ps` 後確認 DB 容器只有容器內 `5432/tcp`，沒有映射到主機 port。

## 影響範圍
- 本機開發環境可用 Navicat / DBeaver / psql 連線 Docker PostgreSQL。
- 僅影響本機 compose；正式部署不應直接公開資料庫 port。

## 驗證方式
- `docker compose ps` 顯示 `argus-db-1` 為 `0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp`。
