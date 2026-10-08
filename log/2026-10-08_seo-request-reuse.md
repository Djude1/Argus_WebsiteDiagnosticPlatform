# 同一次掃描不重複請求同一網址（roadmap §11 第 1 項）

**日期**：2026-10-08  
**操作者**：Claude

## 盤點
- 掃描中對外請求的模組：爬蟲、SEO 連結檢查與站台檢查、圖示、PageSpeed、EPSS／OSV、ZAP、敏感檔案探測。
- 同一次掃描內的重複請求集中在 SEO 連結檢查：
  - **robots.txt**：爬蟲讀過一次，`fetch_robots` 又抓一次。
  - **頁面連到的檔案**：頁面連到的 `/sitemap.xml`、`/llms.txt`（爬蟲讀過）會被連結檢查再查一次。
  - **站台檢查的 sitemap 等網址**：可能和連結檢查重複。
- 其他模組原本就不重複：EPSS／OSV 快取 1 天；PageSpeed 每次掃描只呼叫一次；爬蟲已造訪且沒轉址的頁面原本就不進連結檢查。

## 變更內容
- **爬蟲記錄狀態**：`probe_site_signals`／`discover_sitemap_urls` 在 `site_signals["fetched"]` 記下 robots.txt、llms.txt、sitemap 的 HTTP 狀態（不跟隨轉址）。
- **`seo/collect.build_link_report(..., site_signals=)`**：
  - 已取得且沒轉址的網址不再送進連結檢查，直接用已知狀態。
  - robots.txt 以爬蟲原文解析（`link_check.parse_robots`，從 `fetch_robots` 拆出）。
  - 站台檢查（`site_checks(..., known, reused)`）先沿用已有結果，包含連結檢查查過的網址。
  - 轉址的不沿用，照常檢查跳轉鏈。兩邊都是不跟隨轉址的單次請求，狀態語意相同。
- **可觀測**：沿用數記在 `seo_report.reused`（links／robots／site_checks），掃描 log 加一句「沿用爬取階段已有結果 N 個請求」。
- **不做跨掃描沿用**：每次掃描要反映網站當下的狀態。
- **文件**：roadmap、scans CLAUDE.md。

## 驗證方式
- 新增 `tests_seo_reuse.py`（4 項）：
  - 沿用 robots.txt／sitemap／llms.txt 的結果、轉址網址照常檢查。
  - 沒有爬蟲訊號時行為與以前相同，且連結檢查查過的網址站台檢查會沿用。
  - robots.txt 轉址時重新抓。
  - 爬蟲記錄 sitemap 狀態。
- 既有 SEO 分析、sitemap、連結趨勢測試通過。
- 全套後端測試、`ruff check backend`。
- 未做：本機測試站實際計數請求次數。
