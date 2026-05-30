# 修復掃描詳情頁雙重載入動畫

**日期**：2026-05-26  
**操作者**：Claude

## 變更內容

- `frontend/src/App.jsx`：`ScreenshotViewer` 截圖區（約第 1258 行）在掃描進行中且無截圖時，原本顯示 compact `CrawlingAnimation`，改為顯示簡單的 `.screenshot-pending` 佔位（spinner + 一行文字）
- `frontend/src/styles.css`：新增 `.screenshot-pending` class（flex 置中，最小高度 380px）

## 原因

`/scans/:scanId` 掃描進行中時，`FindingsPanel`（第 1498 行）已有完整的 `CrawlingAnimation`（含進度條、取消鈕），`ScreenshotViewer` 又同時顯示一個 compact `CrawlingAnimation`，導致畫面出現兩個載入動畫，視覺上奇怪。

## 影響範圍

- 僅影響 `/scans/:scanId` 頁面掃描進行中時的截圖佔位區域
- 掃描完成後截圖顯示邏輯不受影響
- 掃描完成或無截圖的文字提示邏輯不受影響

## 驗證方式

- `npm run build` 成功（Node 22，26.92s，無錯誤）
- 確認 `ScreenshotViewer` 僅保留一個 spinner + 文字的簡單佔位
