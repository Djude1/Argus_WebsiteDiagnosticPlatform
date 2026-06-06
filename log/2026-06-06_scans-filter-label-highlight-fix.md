# scans 頁篩選器標籤與截圖高亮修復

**日期**：2026-06-06  
**操作者**：Claude

## 變更內容
- `frontend/src/App.jsx`：`FindingsWorkspace` 的兩個篩選 `<select>` 包上 `<label>` 並加「分類」/「嚴重度」小標題
- `frontend/src/App.jsx`：`ScreenshotCanvas.useEffect` 開頭加 `setImageUrl("")`，確保換頁時立即清除舊截圖 URL

## 原因
1. 篩選器沒有外部標籤，選了值之後（例如顯示「SEO」、「中」）完全看不出哪個是分類、哪個是嚴重度
2. 展開 finding group 時，`selectFinding` 切換 `targetPage` → effect cleanup revoke 舊 objectUrl → `imageUrl` state 仍指向失效 URL → `<img>` 高度歸零 → `whole-page-highlight` 因父容器高度為 0 而不可見

## 影響範圍
- `FindingsWorkspace` 篩選器 UI（純視覺，不影響篩選邏輯）
- `ScreenshotCanvas` 截圖載入流程：切換頁面時先清空再載入，避免殘留失效 URL

## 驗證方式
- 手動瀏覽 http://localhost:8080/scans/18，確認「分類」/「嚴重度」標籤顯示於對應 select 上方
- 展開「核心內容高度依賴 JavaScript 渲染」群組，確認截圖區立即顯示 `site-banner-overlay`（紅色頂部 banner）與 `whole-page-highlight`（紅色整頁外框）
- URL 切換至 `?finding=1593&page=124`，截圖載入正確無破圖閃爍
