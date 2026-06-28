# 修正 handoff / email-setup-guide 內 docker exec 的 manage.py 路徑

**日期**：2026-06-20
**操作者**：Claude

## 變更內容

| 檔案 | 行 | 改動 |
|---|---|---|
| [docs/handoff-2026-06-15-email-and-ui.md](../docs/handoff-2026-06-15-email-and-ui.md) | L14 | `docker exec ... backend/manage.py test_email` → `docker exec ... manage.py test_email` |
| 同上 | L142 | 同上 |
| 同上 | L177 | `docker exec -it ... backend/manage.py createsuperuser` → 移除 `backend/` |
| [docs/email-setup-guide.md](../docs/email-setup-guide.md) | L85 | 同上模式（L82 是 host 用法，保持不動）|

> 改動只是把 4 處 docker exec 指令裡多餘的 `backend/` 前綴拿掉，host（開發機）用法仍保留 `backend/manage.py`。

## 原因

[Dockerfile](../Dockerfile) L45 設 `WORKDIR /app/backend`，所以 container 內 cwd 就是 `/app/backend`。`docker exec` 預設沿用 image 的 WorkingDir，因此：

- container 內 `manage.py` 在 cwd 直接可見 ✅
- container 內 `backend/manage.py` 會被解讀成 `/app/backend/backend/manage.py`（不存在）→ Python 立刻 `[Errno 2] No such file or directory` ❌

而 host 開發機 cwd 是 repo root，所以 host 上 `uv run python backend/manage.py ...` 是對的。

兩種環境路徑不同，handoff 與 email-setup-guide 之前 4 行 docker exec 指令誤照搬 host 路徑，會讓公網機部署機 Claude 一執行就掛。

**為什麼之前沒被發現**：根據 [log/2026-06-15_resend-smtp-verified.md](2026-06-15_resend-smtp-verified.md) L7-8 / L37-58 / L112-118，6/15 那場只在開發機本機完成 SMTP 驗證，公網機部署是「待做」、從未實際跑過 `docker exec ... test_email`，所以這 4 行錯誤從未被觸發。

本次任務（建立 `交接資料/` 給公網機 Claude）開始前發現指令會誤導，提前修正。

## 影響範圍

- **文件層**：4 行純文字修正，無程式碼變動
- **下游**：之後任何照 handoff/email-setup-guide 在 container 內跑 `manage.py` 指令的人/agent 不會再卡 `[Errno 2]`
- **未影響**：[`docs/superpowers/plans/*`](../docs/superpowers/plans/) 內出現的 `backend/manage.py` 都是 host 開發機指令，不在此次範圍

## 驗證方式

| 項 | 結果 |
|---|---|
| `grep -n "backend/manage.py" docs/handoff-2026-06-15-email-and-ui.md` | ✅ 0 個殘留 |
| `grep -n "backend/manage.py" docs/email-setup-guide.md` | ✅ 只剩 L82（host 用法，正確）|
| `git diff docs/` 確認只動 4 行 | ✅ 4 處 `-backend/manage.py / +manage.py` |
| 機密掃描（含 unstaged 改動）| ✅ 無機密命中 |
| Dockerfile WORKDIR 事實確認 | ✅ L45 `WORKDIR /app/backend` 未被改過（git log Dockerfile） |
