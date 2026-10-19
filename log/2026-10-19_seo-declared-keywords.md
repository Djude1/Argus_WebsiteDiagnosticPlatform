# SEO 分析頁：列出網站自己宣告的 meta keywords 並與內容、Search Console 對照

**日期**：2026-10-19  
**操作者**：Claude

## 變更內容
- `backend/apps/scans/seo/page_audit.py`：解析 `<meta name="keywords">`（`split_meta_keywords`：逗號／分號分隔、去空白、去重、每頁最多 30 個），`audit["meta_keywords"]`。
- `backend/apps/scans/seo/keywords.py`：`declared_keywords(targets, audits)`——跨頁（只算 200）去重、依宣告頁數與首次出現排序（最多 30），每個沿用 `keyword_report` 的內容比對（出現頁數、最相關頁面與位置、建議）並標 `is_target`、`declared_pages`。
- `backend/apps/scans/seo/report.py`：`keyword_index` 帶 `meta_keywords`，`project_seo` 回 `declared_keywords`；`CACHE_VERSION` 2→3。
- `frontend/src/features/projects/ProjectSeoPage.jsx`：目標關鍵字表之下新增「網站自己宣告的關鍵字（meta keywords）」表：宣告頁數、頁面內容（最相關頁面＋位置／「沒有頁面提到」）、連接 GSC 時沿用 `keywordGap` 的 Search Console 欄、建議、已是目標／設為目標。
- 測試：`tests_seo_analysis.DeclaredKeywordsTests`（解析去重、跨頁合併、目標標記、API 無標籤時回空清單）、`ProjectSeoPage.test.tsx` 新案例＋既有案例改成在機會表取按鈕。
- 文件：`backend/apps/scans/CLAUDE.md`、`frontend/CLAUDE.md`、`docs/scan-upgrade-roadmap.md`、`專題文件生成/需求書_複賽版完整內容.md`。

## 原因
使用者看到 ntubimdbirc.tw 的 head 有 meta keywords，問它有什麼用、對 Argus 關鍵字功能有何啟發。meta keywords 對 Google 排名無效，但它是網站主親手寫下的意圖；拿它和頁面內容、Search Console 實際搜尋詞並排，能指出「想被搜的字沒做進標題／沒人搜」與「真正被搜的字不在清單」的落差。

## 影響範圍
- 只多一個回應欄位，不產生 Finding、不影響分數；沒有該標籤的網站清單為空。
- `_analysis` 快取版本升級，舊快取自然失效。

## 驗證方式
- `uv run ruff check backend` 通過；`manage.py test apps.scans.tests_seo_analysis` 59 項通過。
- `npm run lint`（0 error）、`npm run typecheck`、`npx vitest run` 304 項通過。
- 未以真實 Search Console 帳號在正式站驗證畫面（需部署後到 ntubimdbirc 專案的 SEO 分析→搜尋關鍵字確認：應列出 NTUB-BIRC、商業智慧研究中心、北商產業新尖兵課程、臺北商業大學 四筆）。
