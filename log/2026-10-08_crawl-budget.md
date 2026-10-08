# 爬取預算可觀測（roadmap「爬取」第 2 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- `crawler._CrawlState` 記錄：
  - 種子來源：起始網址、sitemap。
  - 頁面連結排入數。
  - 略過與失敗：超過頁數上限沒排入、超過深度、robots.txt 禁止、擷取失敗。
  - 速率限制等待次數與秒數。
  - 每頁耗時。
- `crawl_site` 結束時（含例外）寫 `warnings["crawl_budget"]`＝`budget_summary(stop_reason, 秒數)`：
  - 結束原因 `stop_reason`：達頁數上限／沒有更多頁面／瀏覽器異常。
  - 上述各項數字、總耗時、每頁平均、最慢 3 頁。
  - 隨 `warning_summary` 保存，不需要 migration。
- `tasks.crawl_budget_text`：`stage_crawl` 寫一行說明到掃描 log，例如「爬取結束：達到頁數上限（6／6 頁，耗時 5 秒）；來源：起始網址 1、sitemap 2、頁面連結 3；略過：超過頁數上限未排入 8」。`stage_enter_scanning` 的「爬取警告」不再重複列出這個摘要。
- 後台掃描詳情（`AdminScansPages.tsx`）的「爬取警告」最上方顯示爬取預算；樣式 `22-admin-components.css` 的 `.admin-crawl-*`。
- **同次修正（由這份紀錄發現）**：`enqueue_links` 原本會把 sitemap 已排入的頁面再排一次。重複項目佔掉頁數上限名額，把還沒排到的新頁面擠掉；現在已在佇列的網址不再重複排入。
- 尚未做：render readiness 結果（要等「爬取」第 1 項有界的渲染就緒判斷實作後才有）。
- 文件：scans／frontend CLAUDE.md、roadmap。

## 驗證方式
- 新測試 `tests_crawl_budget.py`（4 項）：
  - 種子來源、超過上限、超過深度、節流與耗時計數。
  - robots.txt 禁止計數。
  - log 說明文字。
  - 已排入的網址不佔名額。修正前這項會失敗：重複的網址佔掉最後一個名額，新頁面被丟掉。
- 前端 `AdminScansPages.test.tsx` 新增 1 項（爬取預算顯示）。
- 實際執行 `crawl_site`：本機測試站（首頁 8 連結、robots 禁止 1 頁、sitemap 2 頁、每頁再連一層），以 DEBUG 的私網目標旁路只在暫存腳本中開啟：
  - 6 頁上限、深度 1：達到頁數上限；來源 1／2／3；超過上限未排入 8。修正前同樣情況顯示 10，含重複排入的 2 個。
  - 30 頁上限、深度 1：沒有更多頁面（8 頁）；頁面連結 13（修正前 15，含 2 個重複）、超過深度 7、robots 禁止 1。
- 真實網站在沙箱內無法經 `crawl_site` 爬取：爬蟲對每個請求做公開位址檢查，沙箱的 DNS 經 proxy 解析而被擋。爬取預算如實記錄為擷取失敗 5 頁。
- 全套後端測試、`ruff check backend`；前端 lint（0 error，1 個既有 warning）、typecheck、vitest。
