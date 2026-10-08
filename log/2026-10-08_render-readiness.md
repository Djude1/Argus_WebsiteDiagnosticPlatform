# 爬蟲：有上限的渲染就緒判斷（roadmap「爬取」第 1 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- `crawler.wait_for_render_ready`：`goto(domcontentloaded)` 之後、擷取之前，等頁面內容穩定。
  - 每 250ms 量一次正文字數與元素數，至少等 0.5 秒（留給前端框架 hydration）。
  - 連續兩次幾乎不變就算就緒：字數差 ≤ max(20, 0.5%)、元素數差 ≤ 2。容許小幅變動，輪播、跑馬燈不會讓它永遠等下去。
  - 上限 `ARGUS_RENDER_READY_MAX_SECONDS`（預設 5 秒，已加入 `.env.example`）。
  - 不使用 networkidle：分析工具、客服元件、長輪詢會讓網路永遠不靜止。
- 逾時不是失敗：照樣擷取當下的 DOM 與截圖。記錄在：
  - `warning_summary.crawl_budget.render_readiness`（ready／timeout／error 數、平均等待、逾時網址）。
  - 掃描 log 的爬取預算說明。
  - `crawl` 覆蓋紀錄的說明（`render_readiness_timeout`）。不改覆蓋狀態：持續更新的頁面不該讓整次掃描變成部分評估。
- 等待時間從 `load_time_ms` 扣掉：SEO「載入慢」與網站優勢的載入時間依這個值判斷，不能因為 Argus 多等了而變慢。
- 後台掃描詳情的爬取預算多一列「內容穩定」。
- 未做 site-specific selector（roadmap 列為可選）：目前沒有需要的網站實例。
- 文件：scans／frontend CLAUDE.md、roadmap、需求書 NF-002（容量與禮貌爬取）、`.env.example`。

## 真實網站核對（沙箱 Chromium，與爬蟲相同的 goto 方式）
- ntubimdbirc.tw、wordpress.org、cna.com.tw、setn.com、tw.yahoo.com、thenewslens.com、pinkoi.com、nextjs.org、ntub.edu.tw 都在約 0.5 秒（最短等待）判定就緒。
- 就緒之後再等 3 秒，正文字數都沒有增加，沒有判定太早的情況。
- nextjs.org 在等待期間正文由 3880 字增為 4197 字，等待確實多抓到內容。
- udn.com、react.dev 在沙箱連不上。
- 每頁成本約 +0.5 秒，50 頁約 +25 秒。

## 驗證方式
- `tests_crawl_budget.py` 新增 4 項：
  - 渲染就緒摘要與 log 說明。
  - 真實 Chromium：1.2 秒後才填入內容的頁面會等到內容出現（≥1200ms）。
  - 真實 Chromium：每 200ms 換一句的輪播在 1.5 秒內判定就緒。
  - 真實 Chromium：持續新增段落的頁面在上限（1.5 秒）放棄。
- 前端 `AdminScansPages.test.tsx` 爬取預算案例加上內容穩定一列。
- 實際執行 `crawl_site` 爬本機測試站（6 頁）：log 顯示「等內容穩定平均 0.5 秒」。`load_time_ms` 仍約 1000ms，與加入等待前相同，確認等待時間已扣除。
- 全套後端測試、`ruff check backend`；前端 lint（0 error，1 個既有 warning）、typecheck、vitest 239 項。
