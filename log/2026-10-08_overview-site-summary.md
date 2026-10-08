# 總覽加入「效能與網站架構」摘要

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容（側邊欄審查建議第 3 項）
- **後端 `projects.site_summary(scan)` → `latest_scan.site_summary`**：只整理已保存的資料，包含：
  - PageSpeed 的 Lighthouse 效能分數、CrUX 整體評等與中文標籤。
  - pagespeed 覆蓋狀態，沒量到時附原因。
  - CDN 邊緣服務商。
  - 使用的技術：前 6 項與總數。
  - 安全標頭參考等第。
  - `profile_available`：較早的掃描沒有網站概況，前端據此寫「沒有資料」，而不是「未偵測到」。
- **前端總覽新增 `SiteSummaryPanel`**：放在優先改善建議下方，共四格。
  - 行動版效能 → 效能分頁。
  - 安全標頭等第 → 資安分析。
  - CDN／反向代理 → 網站架構。
  - 使用的技術 → 網站架構。
  - 沒有數字時寫原因：沒勾使用體驗、平台未設金鑰、量測失敗、較早的掃描。
- **文件**：frontend／scans CLAUDE.md、需求書。

## 驗證方式
- **後端 `tests_project_security.py` 新增 2 項**：
  - 從已保存的報告整理出摘要。
  - 沒有效能資料時保留原因、沒有網站概況時 `profile_available=false`。
- **前端 `ProjectPages.test.tsx` 新增 3 項**：
  - 數值與連結。
  - 效能沒有數字時的原因。
  - 較早掃描寫「沒有這項資料」、不寫「未偵測到」。
- **lint、typecheck、vitest**：通過。
- **實際瀏覽器看示範專案總覽**：桌面淺色、深色與手機 390px 都沒有水平捲動。
  - 示範資料沒有網站概況，第一版寫成「未偵測到／未辨識到」，容易被誤解，所以改成上述說法。
- 全套後端測試、`ruff check backend`。
