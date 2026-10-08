# 目標關鍵字 × Search Console 落差分析（roadmap §1 SEO 第 4 項）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 先確認現況：
  - SEO 分頁已有目標關鍵字的頁面內容比對（後端 `seo/keywords.py`）。
  - 已有 Search Console 搜尋詞表（`gsc/performance`，前 200 個查詢）。
  - 兩者只做「完全相同字詞」的對照：「台北 咖啡豆」這類包含目標關鍵字的搜尋詞完全不會計入，也沒有排名分段與落差提示。
- 新增 `frontend/src/features/projects/seoKeywordGap.ts`（純函式），只用頁面已有的資料，不新增 API。
  - `keywordGap`：每個目標關鍵字彙總包含它的搜尋詞（不分大小寫、全形空白視為空白，不斷詞）。
    - 彙總內容：曝光、點擊、最佳平均排名與對應搜尋詞。
    - 排名分段：第 1 頁（≤10）、第 2 頁（11–20）、第 3 頁以後、沒有曝光。
    - 曝光最多的搜尋詞帶到的頁面，與內容最相關的頁面不同時，提示確認主題主頁並加內部連結。
    - 沒有曝光時，依頁面有沒有提到給不同建議。
  - `untargetedQueries`：有曝光但不包含任何目標關鍵字（也不被目標包含）的搜尋詞，依曝光排序取前 10。
- `ProjectSeoPage.jsx` 的「目標關鍵字」區：
  - Search Console 欄改顯示分段徽章（附文字）、彙總數字、最佳排名與 Google 帶到的頁面。
  - 建議欄合併頁面比對與落差建議。
  - 下方新增「有曝光但還不是目標的搜尋詞」表，每列「設為目標」（達 20 個上限時停用並說明）。
- 樣式：`legacy-member/95-seo.css` 加 `.seo-subtitle`；徽章沿用 `.seo-chip`。
- 文件：frontend CLAUDE.md、roadmap、需求書 SEO 段落。

## 原因
網站主設定的目標關鍵字和 Google 實際帶來曝光的字詞常常對不上：想經營的字沒有曝光、排在第 2 頁差一點，或 Google 帶到錯的頁面；而有曝光的字詞卻沒被注意。

## 影響範圍
- 只影響 SEO 分析頁的搜尋關鍵字分頁，連接 Search Console 時才有落差資訊。
- 後端與 API 不變，也不需要 migration。

## 尚未驗證
- 沒有真實 Search Console 帳號可測，只用測試資料驗證。
- 請在已連接 Search Console 的專案確認數字與「設為目標」流程。

## 驗證方式
- `seoKeywordGap.test.ts`（5 項）：
  - 包含比對與彙總、第 2 頁分段建議。
  - 大小寫與全形空白；第 1 頁沒有分段建議。
  - Google 帶到的頁面不同時提示。
  - 沒有曝光時依頁面有沒有提到給不同建議。
  - 未設為目標的搜尋詞排除包含／被包含的字詞並依曝光排序。
- `ProjectSeoPage.test.tsx`：新增頁面整合測試，涵蓋分段徽章、彙總文字、Google 帶到的頁面、「設為目標」送出正確的關鍵字清單。
- 前端：
  - lint 0 error（1 個 AdminPages.jsx 既有 warning）。
  - typecheck 通過；全部 235 項測試通過；vite build 通過。
