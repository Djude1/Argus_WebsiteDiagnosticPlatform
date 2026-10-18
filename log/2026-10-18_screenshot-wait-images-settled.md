# 截圖前等圖片／字型載完，修「截到半成品畫面」

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者反映「有時候爬取截到的網頁畫面是還沒有加載完全的」。

## 根因
爬蟲擷取順序：`goto(domcontentloaded)` → `wait_for_render_ready`（只量**文字／元素數**穩定）→
`scroll_to_bottom`（觸發延遲載入圖片）→ `page.content()` → `_capture_screenshot`。

`wait_for_render_ready` 不等圖片與 web font，且 scroll_to_bottom 剛觸發的延遲載入圖片還沒畫出來
就截圖 → 整頁截圖出現空白圖片／字型跳動的半成品畫面。專案刻意不用 networkidle（分析工具／
長輪詢會讓網路永遠不安靜）。

## 修法（有上限、只等已存在資源，不用 networkidle）
`crawler.py` 新增 `wait_for_images_settled(page, max_seconds)`：截圖前等**目前 DOM 裡尚未
完成的 `<img>`**（load／error 任一）與 `document.fonts.ready`，上限
`ARGUS_SCREENSHOT_SETTLE_SECONDS`（settings，預設 3 秒），逾時或出錯就直接截圖、不卡住掃描。
`_capture_screenshot` 在 `page.screenshot(full_page=True)` 前呼叫它（桌面版與行動版截圖都套用）。

只等已在 DOM 的資源＋硬上限 → 不會像 networkidle 那樣被長輪詢卡死；scroll_to_bottom 已先把
延遲載入圖片觸發出來，這步確保整頁截圖前畫完。

## 驗證
`ruff check backend` 乾淨、`manage.py check` 乾淨、`tests_crawl_budget`（8，真實瀏覽器 3 項略過）通過。
真實瀏覽器行為需沙箱實掃驗證（本環境無 chromium 跑真爬蟲）。文件同步 `apps/scans/CLAUDE.md`
crawler 條目。

## 備註
- 失敗隔離不變：截圖仍走 `_capture_screenshot`，等圖片逾時不影響該頁其他分析。
- 待爬蟲 image rebuild 後生效；想更保守可調大 `ARGUS_SCREENSHOT_SETTLE_SECONDS`。
