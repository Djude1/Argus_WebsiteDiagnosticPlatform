# Smart Scan 階段 1：網站特徵只記錄（roadmap P1、ADR-0004）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/fingerprint.py`：
  - `SiteFingerprint` 與 `build_fingerprint` 只用爬取已有的訊號，不發任何請求。訊號包含頁面 HTML、回應標頭、狀態碼，以及被動攔截的 XHR／fetch 端點。
  - 判斷的特徵：CMS、框架、伺服器、邊緣服務（只看標頭）、登入頁、API、上傳欄位、HTTP 驗證方式。
  - 沒看到的特徵記為 None，並在 `completeness` 註明原因（not_observed／partial／unavailable），不寫成 False。
  - 每個特徵附信心值與證據。
- `tasks.stage_fingerprint`：接在 `enter_scanning` 之後，只吃爬取當下已有的訊號，不依賴後續階段的輸出。
  - 結果寫 `ScanJob.fingerprint`，掃描 log 記一行摘要。
  - 失敗只記 log，不影響掃描。
  - 不改執行計畫、覆蓋紀錄與計費。
- `ScanJob.fingerprint`：新增 migration `scans/0031_scanjob_fingerprint`。
- 準確率資料集 `fingerprint_gold.py`：23 個調整用案例（含 6 個容易誤判的案例）＋5 個保留集，皆人工標註。
- 指標 `fingerprint_benchmark.py`：
  - 項目：precision、recall、未知比例、每站耗時、連線嘗試數。
  - 判定期間以 socket patch 計數並擋下連線。
  - 指令 `manage.py fingerprint_benchmark [--holdout] [--json]`。
- 文件：
  - scans／backend CLAUDE.md。
  - ADR-0004 進度與階段 1 實測結果。
  - `docs/scan-upgrade-roadmap.md` 第 7 項。
- 本次不改對外功能，所以不動需求書與前端；API 也還不回傳這個欄位。

## 原因
roadmap P1：Smart Scan 要依網站特性追加深度檢查，第一步先確認「認得出網站是什麼」夠準，而且只記錄、不改行為，避免判錯就漏檢或多收費。

## 影響範圍
- 部署需套用 migration `scans/0031`。
- 掃描多一個毫秒級的階段，不新增對目標網站的請求，掃描結果與計費不變。
- 尚未做：
  - 以真實掃描結果人工核對的準確率評估。
  - 階段 2：enrichment、`scan_strategy`、動態加掃與計費。
  - 階段 3：前端「Smart」選項與報告呈現。

## 驗證方式
- 資料集首次量測與修正：
  - 規則誤判：空的 `<div id="root">` 被當成 React，Vue、Svelte 也這樣寫，所以只留 `data-reactroot`。
  - 標註錯誤 2 處：`/wp-json/wc/store/v1/cart` 與 `/api/profile` 依標註規則屬於 API，原本漏標，已更正。
- 修正後：調整用 23 站與保留集 5 站都是 precision 1.0、recall 1.0、0 次連線，每站約 0.2 ms；登入／API／上傳回 None 的比例 0.82。
- 真實網站初步檢查：只抓 12 個網站首頁的原始 HTML 與標頭，非完整爬取。
  - wordpress.org／techcrunch.com → WordPress；drupal.org → Drupal；joomla.org → Joomla＋Cloudflare；vercel.com → Next.js＋Vercel；angular.dev → Angular；nuxt.com → Nuxt＋Vue.js＋Vercel；cloudflare.com → Cloudflare。
  - nextjs.org 收到非瀏覽器 User-Agent 時回 Markdown 而非 HTML，所以這次沒判出框架；正式掃描用真實瀏覽器，不受影響。
- 新測試 `tests_fingerprint.py`（12 項）：門檻鎖定、0 次連線、完整度語義、信心值、階段只記錄不改計畫、失敗不中斷。
- 全套 `uv run python backend/manage.py test apps`：1590 項 OK（1 skipped）。
- `ruff check backend`（exit 0）、`makemigrations --check`：通過；openapi 與前次產生的相同。
