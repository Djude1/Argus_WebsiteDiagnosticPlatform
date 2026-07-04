# 爬蟲 Content-Length 上限（防超大回應撐爆記憶體）

## 變更內容

**修改檔案：** `backend/apps/scans/crawler.py`

1. 新增常數 `_MAX_RESPONSE_BYTES = 30 * 1024 * 1024`（30 MB）
2. 新增 helper `classify_oversized(headers, body=None)`
   - 優先看 Content-Length header（免下載 body 就能判斷）
   - 沒 header 時（chunked encoding）用實際 body 長度 fallback
3. `crawl_site()` 的 goto 流程加入雙層檢查：
   - **早期檢查**：拿到 response headers 立刻查 Content-Length，超過則跳過 `scroll_to_bottom` / `page.content()` / `response.text()` / `page.screenshot()` / `extract_links()` / `collect_element_boxes()`——所有耗記憶體操作
   - **fallback 檢查**：抓完 body 後用 `len(html)` 再驗一次（Content-Length 缺席時捕捉）

## 原因

原本 `page.goto()` 之後直接無條件執行：
```
scroll_to_bottom → page.content() → response.text() → page.screenshot(full_page=True)
```

任一步碰到 100 MB 的 PDF/影片/惡意 gzip bomb 都會：
- `page.content()` 把整個 body 複製一份成 str（記憶體 × 2）
- `page.screenshot(full_page=True)` 依內容高度分配 image buffer（記憶體 × N）
- 這幾步在 Celery worker 進程內執行，撐爆會拖垮整個 worker

Playwright 沒有原生 `max_body_size`，只能事後檢查 Content-Length 決定是否進入耗記憶體操作。

## 行為說明

**超大回應（Content-Length > 30 MB）：**
- 記錄 `blocked_reason` = `"回應過大（Content-Length {size:,} bytes 超過上限 {LIMIT:,}）"`
- 加入 `warnings["blocked_urls"]`
- `html` / `title` / `element_boxes` 等欄位為空
- **不呼叫** `page.screenshot()`（避免二次放大記憶體佔用）
- **不呼叫** `extract_links()`（不從錯誤頁繼續延伸爬取）
- Page record 仍會寫入，`screenshot_path` 為空字串

**無 Content-Length（chunked）但實際 body > 30 MB：**
- `page.content()` 已跑完（記憶體已佔），但後續 `page.screenshot(full_page=True)` 仍會執行——這是已知殘留成本
- 記錄 `blocked_reason`，避免 scanners 對超大 body 做正則分析（scanners 遇大字串會 CPU 燒爆）

**上限可未來透過 env 覆寫**（目前 30 MB 硬編碼，需擴充時加 `os.getenv(...)`）。

## 影響範圍

- 攔截超大回應時記憶體峰值降低數倍；worker 崩潰風險大幅減少
- 已被 `is_binary_resource()` 過濾的檔案（.pdf、.mp4 等）不受影響（本來就不進 queue）
- 保留完整的 blocked 資訊供使用者/管理員追查為何某頁沒被掃描

## 驗證方式

- AST 語法檢查 — 通過
- 全套 scans 測試（263 項）— 全部通過（既有測試不觸發此路徑，行為改變僅在遇 > 30 MB 回應時生效）
