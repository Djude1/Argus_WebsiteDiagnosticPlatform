# 連結檢查覆蓋狀態與失效連結趨勢（roadmap §11 第 2、3 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- **覆蓋狀態（§11 第 2 項）**：
  - 逾時從「無法連線」分出成獨立判定 `timeout`（`seo/link_check.py`）。
  - `check_links` 的未檢查數分成 `over_limit`（超過數量上限）與 `budget_exhausted`（時間用完），存 `seo_report.unchecked_reasons`；`unchecked` 總數保留，舊資料相容。
  - 新增 `seo/link_trend.link_coverage`：每個連結歸到已確認／對方限制檢查／逾時／無法連線／非公開位址／超過數量上限／時間用完，存 `seo_report.coverage`。
  - `seo_links` 覆蓋紀錄的說明改成列出沒有明確結果的連結數，例如「逾時 2、超過數量上限 30」。
- **趨勢（§11 第 3 項）**：
  - `seo/link_trend.link_trend` 和同專案上一次有連結檢查的完成掃描比較，存 `seo_report.trend`。
  - 失效連結標記為新壞掉、持續失效、已確認恢復或本次無法確認。
  - 只有這次真的檢查過且正常（含轉址後正常）才算恢復；沒檢查、逾時、被拒，或這次頁面上找不到這個連結，一律「本次無法確認」。
  - 爬蟲已造訪的頁面不做連結檢查，所以兩次掃描都併入爬蟲量到的 HTTP 狀態（上一次從 `Page` 表取），避免把爬蟲確認正常的頁面判成無法確認。
  - 趨勢計算失敗只記 log，不影響掃描。
- **呈現**：
  - `seo/report.py`：連結列帶 `trend`；links 區塊帶 `coverage` 與 `trend` 計數（不含逐網址明細）；逾時列為「連結檢查逾時」提示。輸出結構改變，`CACHE_VERSION` 改為 2。
  - `seo-broken-internal-links`：描述註明幾個是新壞掉、幾個持續失效，證據每筆附趨勢。
  - 前端 SEO 分析頁連結分頁：新增「逾時」狀態徽章（歸在「無法確認」篩選）、每列趨勢徽章、說明列顯示已確認數、沒有明確結果的連結與趨勢計數。
- 文件：scans／frontend CLAUDE.md、roadmap、需求書 SEO 段落。

## 影響範圍
- 勾 SEO 的掃描：`seo_report` 多 `coverage`、`unchecked_reasons`，有上一次掃描時多 `trend`。不需要 migration。
- 舊掃描的 `seo_report` 沒有新欄位：SEO 分析頁即時計算覆蓋，舊報告的未檢查數全算超過數量上限；沒有趨勢。
- 不改評分與規則嚴重度。

## 驗證方式
- 新測試 `tests_link_trend.py`（12 項）：
  - 覆蓋計數與舊報告相容。
  - 四種趨勢標記、受限／未檢查不算恢復。
  - 爬蟲狀態併入，且連結檢查結果優先。
  - `timeout` 判定；未檢查依原因拆分。
  - 問題描述與證據。
  - 掃描階段：上一次掃描含爬蟲 404 頁、第一次掃描沒有趨勢。
  - SEO 分析輸出：列的趨勢、逾時問題、計數。
- 全套後端測試、`ruff check backend`、`makemigrations --check`。
- 前端 `npm run lint`（0 error；1 個 warning 是既有的 AdminPages.jsx）、`npm run typecheck`、`npx vitest run`（236 項通過）。
- 尚未以畫面截圖確認連結分頁的新徽章與說明列，請在 SEO 分析頁「連結」分頁目視確認。
