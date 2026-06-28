# 2026-06-09 修復 Postgres 連線耗盡（too many clients）

## 變更內容

- `backend/config/settings.py`：DB `conn_max_age` 由 `600` 改為 `0`（每請求結束即關閉連線）。
- Postgres（執行階段）：`ALTER SYSTEM SET max_connections = 200;`（原 100），持久化於 db volume 的 `postgresql.auto.conf`，重啟不失。

## 原因

真實 Docker E2E 測試（Chrome 操作 UI）時，API 出現 HTTP 500，db log 顯示
`FATAL: sorry, too many clients already`。診斷根因：

- web 以多執行緒 `runserver`（dev 伺服器，執行緒數無上限）運行；
- `conn_max_age=600` 使每條請求連線保留 10 分鐘重用；
- 前端每 2 秒輪詢掃描狀態 + 多人操作 → 連線只進不出；
- 撐滿 Postgres `max_connections=100` 後，所有 DB 存取（含 API、shell）全 500。

「定期重啟」被否決：治標不治本，且可能在評審掃描中途重啟造成更嚴重中斷。

## 影響範圍

- 僅 `settings.py` 一行 + 一個執行階段 DB 參數；不動任何掃描 / 業務邏輯。
- 與 `feat/passive-security-scanners` 功能無關，已獨立 commit（`69cded8`）。

## 驗證方式

1. 容器內確認 `settings.DATABASES['default']['CONN_MAX_AGE'] == 0`。
2. `SHOW max_connections;` → `200`。
3. 對會查 DB 的公開端點 `/api/content/features/` 連打 80 次併發後：
   `pg_stat_activity` 中 web 連線 `total=1, idle=0`；2 秒後 `idle=0`。
   → 連線不再累積（修正前同樣負載會殘留約 80 條 idle 連線各 10 分鐘）。

## 已知限制 / 後續

- `max_connections=200` 透過 `ALTER SYSTEM` 存於 db volume，**未進版本控制**；
  若日後 `docker compose down -v` 清空 volume 需重新套用，或改寫進
  `docker-compose.yml` 的 db `command`（本次為避免混到使用者未提交變更而未動該檔）。
- 正統做法是 web 改用 gunicorn 綁定 worker 數（連線數從根本上限），
  但變動較大且需處理靜態檔，距 demo 時間近，暫不更動。
