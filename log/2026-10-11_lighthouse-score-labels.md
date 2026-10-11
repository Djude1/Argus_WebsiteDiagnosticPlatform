# Lighthouse 分數改標「基本檢查」，避免與 Argus 分數混淆

**日期**：2026-10-11  
**操作者**：Claude

## 變更內容
- **網頁「效能」分頁**（`PerformancePanel.jsx`）：
  - 標題改為「Google Lighthouse 首頁檢查」。
  - 「無障礙」「SEO」改標「無障礙基本檢查」「SEO 基本檢查」。
  - 分數下方加一段說明：這四項是 Google 對首頁的單次檢查，和 Argus 的 SEO、使用體驗分數不是同一個分數。Argus 檢查這次掃描的全部 N 頁、項目較多並計入總分；這裡只看首頁的基本項目、不計入分數，兩邊數字不同是正常的。頁數由 `scan.pages_count` 傳入。
- **PDF 報告**：
  - 第 1 章的效能段落改名「Google Lighthouse 首頁檢查（PageSpeed Insights）」。
  - 圓環下方的名稱同步改為基本檢查。
  - 加同樣的說明，指向本章開頭的 Argus 分類分數。
  - `RENDERER_VERSION` 26 → 27。

## 原因
使用者問到兩個 SEO 分數（Argus 與 Google PageSpeed）差在哪裡、會不會造成混亂。兩者範圍不同：
- Argus 檢查全部掃描頁面、項目多、計入總分。
- Lighthouse 只看首頁的十幾項基本設定、不計分。

兩者名稱卻相同。同一份報告裡出現「SEO 89」和「SEO 85」，讀者會以為其中一個算錯。

## 影響範圍
- 只改名稱與說明，分數本身不變。
- 公開快速檢查頁的測速（`PageSpeedResult.jsx`）沒有 Argus 分數並列，不會混淆，所以不改。

## 驗證方式
- **前端**：`npm run lint`（0 錯誤；1 個 warning 是 `AdminPages.jsx` 既有的）、`npm run typecheck`、`vitest` 44 檔 275 項通過；`PerformancePanel.test.tsx` 新增 1 項。
- **後端**：報告相關 52 項測試通過，含 `tests_report_site_metrics` 新增的名稱與說明斷言；`ruff check backend` 通過。
- **實際排版**：實際產生 PDF，確認圓環下方名稱與說明的排版。
- **人工確認**：前端改動需重新 build 後部署；正式站請到任一掃描的「效能」分頁確認文字。

## 文件同步
- `backend/apps/scans/CLAUDE.md`：PageSpeed 段、RENDERER_VERSION。
- 競賽需求書內容 md：使用體驗段、F-021。
- 修訂提示詞包：R12 增加 12-7。
