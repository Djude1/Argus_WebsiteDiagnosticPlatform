# 掃描中截圖閃動、Search Console 只有專案連線時無法中斷、示範專案分數變化

**日期**：2026-10-09  
**操作者**：Claude

## 變更內容
- `frontend/src/features/scans/ScanExperience.jsx`（`ScreenshotCanvas`）：重抓截圖的依賴從 `targetPage` 物件改成 `targetPage?.id`。
- `backend/apps/scans/seo_views.py`（`_account_status`、`domains_gsc`）：沒有帳號層級連線、只有網站專案連線時，`needs_reconnect` 改看專案連線（全部授權失效才是 true，`error` 帶失效原因）；DELETE 在沒有帳號層級連線時中斷全部專案連線（共用同一授權時只在最後一筆撤銷 Google 授權）。
- `frontend/src/features/domains/DomainVerifyPage.jsx`：有任何 Search Console 連線就顯示「中斷連線」（含授權失效狀態），確認文字在只有專案連線時說明會一併中斷各網站專案 SEO 分析的連線。
- `backend/apps/scans/demo/seed.py`：建立示範掃描時寫入目前的 `SCORING_VERSION`／`RULESET_VERSION`。
- 新增 migration `scans/0032_demo_scan_versions.py`：既有示範專案、版本仍為空的掃描補上同一組版本（只改示範專案）。
- 測試：`tests_seo_analysis.py`（只有專案連線且失效 → 提示重新連接、可中斷）、`tests_demo_project.py`（示範專案 `score_comparable`）、`DomainVerifyPage.test.tsx`（兩種狀態都有中斷連線）。
- 文件：`backend/apps/scans/CLAUDE.md`、`frontend/CLAUDE.md`、`backend/apps/scans/demo/README.md`。

## 原因
- 使用者回報掃描進行到 SEO、AEO、GEO… 階段時，下方截圖一直閃。截圖在爬取階段就和頁面一起存好，但掃描中每 2 秒更新一次頁面清單，每次都是新物件，元件因此清空截圖、重新下載。
- 使用者回報某帳號按「重新同步網站」跳出「Search Console 授權已失效，請重新連接」，頁面卻顯示已連接、也沒有中斷連線（其他帳號有）。該帳號只有從 SEO 分析頁建立的網站專案連線，網域驗證頁原本只看帳號層級連線。
- 示範專案的掃描是匯出資料建立的，沒有評分版本，總覽寫「評分規則已更新，無法直接比較」。

## 影響範圍
- 掃描詳情：同一頁的截圖不再因輪詢重抓；切換頁面或改看行動版截圖照常重抓。
- 網域驗證頁：只有網站專案連線的帳號，授權失效時會看到重新連接；按中斷連線會中斷各專案 SEO 分析的 Search Console 連線（有帳號層級連線的帳號行為不變）。
- migration 0032 只更新 `project.is_demo=True` 且 `scoring_version=""` 的掃描，正式部署時由 PreSync migrate 套用。

## 驗證方式
- `manage.py test apps.scans.tests_seo_analysis`（53 項）、`apps.scans.tests_demo_project`（20 項）：通過。
- 前端 `vitest`（domains、scans）、`eslint`、`ruff`：通過。
- 本機測試資料庫實際套用 0032：三筆示範掃描補上版本，`project_overview` 的 `score_comparable` 變為 True。
