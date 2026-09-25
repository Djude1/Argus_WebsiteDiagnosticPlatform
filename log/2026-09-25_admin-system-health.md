# 系統健康頁（Q1 決策後實作）

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容

### 後端
- 新增 `GET /api/admin/health/`（`IsAdminUser`），回傳四項檢查與整體狀態。
- `_probe_celery_workers()`：`celery_app.control.ping(timeout=1.5)`。
- `_probe_redis()`：對 `CELERY_BROKER_URL` 做 `PING`；broker 非 Redis 時回 `warn` 並略過。
- 佇列深度：`ScanJob.status=queued` 筆數與逾時筆數。
- 近一小時成功率：completed vs failed；**無樣本時回 `unknown` 而非 `ok`**。
- 整理模組層 import（`timedelta`、`dj_settings`），移除 `system_settings` 內的重複區域 import。
- 新增 `SystemHealthTests` 6 項。

### 前端
- 新增 `features/admin/AdminHealthPage.jsx`，掛在側欄「營運」組。
- 每項檢查顯示狀態（色＋符號＋文字三重編碼）、細節與**判定依據**。

## 原因
使用者 2026-09-25 回覆 Q1：健康頁要做，可新增探測端點。

規劃 §4-7：把 `docs/environment-preflight.md` 的人工檢查變成畫面。掃描鏈路（Redis／Celery worker／Playwright）任一環節斷掉會讓整批掃描卡住，先前後台完全看不到，只能查資料庫。

## 幾個刻意的設計決定
- **無樣本回 `unknown` 而非 `ok`**：沒有資料不等於沒有問題，給綠燈是說謊。`unknown` 不計入整體狀態的嚴重度。
- **每項都必須有 `basis`**：沒有判定依據的綠燈是不可信的綠燈，測試會檢查此欄位非空。
- **探測失敗回 `bad` 而非 500**：broker 連不上時，這個端點本身必須還活著才能告訴你 broker 連不上。
- **逾時 1.5 秒**：這是給人看的儀表板，不值得讓管理員等；也因此頁面明說偶發抖動可能誤報，連續兩次異常才值得追查。
- **明確標示這是即時探測不是歷史監控**：它回答「現在通不通」，不回答「過去壞過幾次」。

## 影響範圍
- 純新增；未改動既有端點行為。
- 側欄「營運」組由 3 項增為 4 項。

## 驗證方式
- `apps.admin_api` 共 77 項測試全過（新增 6 項）：非 staff 403、四項檢查齊全且都有判定依據、broker 不可達回 bad 而非 500、無樣本回 unknown、成功率計算正確、逾時佇列標記 bad。
- `uv run ruff check backend` 全過；`manage.py check` 0 issues。
- `npx vite build` 通過；`AdminHealthPage` 獨立 chunk 2.79 kB。
- **待人工確認**：在真實環境（Celery worker 實際運作／停止）各看一次，確認綠燈與紅燈都如實反映。本機測試是以 mock 驗證邏輯，不等於實機驗證。
