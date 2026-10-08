# 問題分析依根本原因分組（roadmap 跨領域工程化：Root Cause Correlation 第一階段）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- **`apps/scans/root_causes.py`**：以 rule_id 把同一處修法的問題歸類。
  - 目前的歸類：
    - 伺服器回應標頭：CSP、HSTS、X-Frame-Options、X-Content-Type-Options、`header-*`。
    - Cookie 屬性。
    - TLS。
    - SPF／DMARC。
    - 圖片替代文字：SEO 的 alt 檢查與 axe-core 的 image-alt 等規則。
    - 文章作者與日期標記。
  - 只收修法確實在同一處的規則。頁面沒用 HTTPS、CSRF、DNSSEC 不歸類，因為修法不在同一處。
  - 同一原因有 2 個以上問題才成組。
  - 排序依最高嚴重度、問題數、受影響頁數。
- **`projects.project_issues`**：回傳 `root_causes`，同組的問題標上 `root_cause`。
- **前端問題分析**：新增第三種顯示模式「依根本原因」（`?group=cause`），沒有可成組的問題時不顯示這個按鈕。
  - 每組標題列寫原因、在哪裡修和說明；其餘問題列在「其他問題」。
  - 樣式：`.issue-cause-*`，不用彩色左邊條。
- **只是呈現**：不改嚴重度、計分、歷史比較，PDF 報告也還沒有這個分組。
- **文件**：roadmap、scans CLAUDE.md、frontend CLAUDE.md、需求書。

## 驗證方式
- **後端 `tests_root_causes.py`，4 項**：
  - 真實掃描規則名稱的歸類結果。
  - 不該歸類的規則確實沒歸類。
  - 成組門檻與排序。
  - API 回傳的內容。
- **前端 `ProjectPages.test.tsx` 新增 2 項**：分組標題列與「其他問題」、沒有根本原因時不顯示按鈕。
  - 前端整體：lint 0 error（1 個既有 warning）、typecheck 通過、vitest 252 項通過。
- **示範專案的三次真實掃描資料**：回應標頭分別歸出 5、4、2 項，SPF／DMARC 每次都是 2 項；cookie 只有 1 項，所以不成組。
- **實際瀏覽器截圖**：本機 runserver＋build 後的前端，看示範專案的問題分析頁。
  - 桌面淺色、深色與手機 390px 都正常，沒有水平捲動。
  - 本機測試資料庫先補跑了 migration（只動沙箱資料庫）。
- 全套後端測試、`ruff check backend`。

## 尚未做
- 根本原因還沒放進 PDF 報告和總覽的「優先改善建議」。
