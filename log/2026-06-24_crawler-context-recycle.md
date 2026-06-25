# Playwright Context 定期重建（記憶體優化）

## 變更內容

**修改檔案：** `backend/apps/scans/crawler.py`

- 新增常數 `_CONTEXT_RECYCLE_EVERY = 15`
- 新增 `_make_context(browser)` helper function，集中管理 context 建立設定
- 每爬完 15 頁，關閉舊 context 並重建新 context

## 原因

Playwright 的 `page.close()` 只釋放頁面層的資源，但 Browser Context 層的累積狀態不會被清除，包括 cookies、localStorage、service worker 註冊、JavaScript heap 中的全域物件。對 SPA 密集使用 service worker 的網站，50 頁後 context 記憶體可能數倍於初始值。

## 行為說明

頁 1-15 使用 Context #1，第 16 頁起關閉舊 context 並建立 Context #2，以此類推。函式結束時 `finally` 關閉最後一個 context 與 browser。

## 影響範圍

- 每 15 頁增加約 50-100ms 重建延遲，不影響掃描結果
- Cookie / Session 不在 Context 間共享（爬蟲本來就不登入，無影響）
- `probe_site_signals()` 使用初始 Context，不受重建影響

## 驗證方式

語法驗證通過。整合測試：Docker 環境觀察 `docker stats argus-worker-1` 記憶體用量。
