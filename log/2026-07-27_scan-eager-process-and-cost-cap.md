# 修正本機掃描失敗與費用估算

**日期**：2026-07-27<br>
**操作者**：Codex

## 變更內容

- 本機 eager 掃描改由背景 executor 管理獨立 Python 子程序，避免 Playwright 直接在 web thread 執行。
- 子程序加入硬逾時、process-tree 終止、非終態工作收斂與冪等退款。
- Windows 建立 asyncio event loop 遇到特定 `WinError 10013` 時做有限重試。
- 單頁 Playwright 暫時錯誤可重試一次，失敗摘要只記錄安全的階段與例外類別。
- 爬蟲 warning 在寫入 scan log 或資料庫前，會遞迴遮罩 URL query、fragment 與個資。
- Playwright page/context/browser 的 cleanup 改為 best-effort，清理失敗不會蓋掉掃描結果或取消狀態。
- 掃描費用估算改為依 `max_pages` 與 billing 單價計算預扣上限，不再連線或解析目標網站。
- 提高費用估算結果在淺色介面中的對比，並補上狀態的無障礙提示。

## 原因

本機 eager 模式原先把 Playwright 放進 web 背景執行緒，Windows 偶發無法建立 asyncio
內部 socket，導致任務在一秒內失敗；同時費用估算結果顏色太淡，且遠端讀取網站會讓
估價變慢並擴大授權、SSRF 與資源耗盡風險。

## 影響範圍

- 影響本機 `DEBUG=true` 且 `CELERY_TASK_ALWAYS_EAGER=true` 的掃描執行方式。
- 正式 Redis／Celery worker 的排程方式不變。
- `/api/estimate/` 現在回傳費用上限，不再猜測網站實際頁數；掃描完成後仍依實際抓取頁數結算並退回差額。
- 未修改 K8s、正式環境、Git 狀態或既有使用者資料。

## 驗證方式

- `uv run python backend/manage.py test apps.scans.tests.EstimateScanTests apps.scans.tests_celery_wiring`：27 項通過。
- `uv run python backend/manage.py test apps.scans`：463 項通過，2 項依平台條件跳過。
- `uv run python backend/manage.py test apps`：656 項通過，2 項依平台條件跳過。
- 隔離 SQLite 與 media 路徑的 API 實測：建立掃描約 0.66 秒回 `201 + queued`，背景狀態依序進入 `crawling`、`scanning`、`completed`，全網站模式成功抓取 2 頁且無失敗網址。
- 費用估算端點直打：50 頁回傳 500 coin 上限與 `billing_cap`，本機處理約 2 ms。
- `uv run ruff check`（本次後端變更檔案）：通過。
- `frontend/build-node22.ps1`：production build 通過。
- `uv run python backend/manage.py check` 與 `makemigrations --check --dry-run`：通過。
- 獨立安全複查：Critical 0、High 0、Medium 0、Low 0；warning 脫敏、子程序異常清理與 Playwright cleanup 的 fault probes 均通過。
