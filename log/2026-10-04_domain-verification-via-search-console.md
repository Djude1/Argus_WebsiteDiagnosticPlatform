# 網域所有權驗證改以 Google Search Console 為主

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `scans/models.py`：`VerifiedDomain.Method` 新增 `search_console`（migration `0023_verifieddomain_search_console`，只改 choices；檔案維持 CRLF）。
- `scans/seo/gsc.py`：`property_covers_domain`（網域資源涵蓋子網域、網址前置字元資源只證明該主機）、`property_domain`。
- `scans/domain_verification.py`：`verify_search_console(user, domain)`——讀使用者所有 Search Console 連線的資源清單，涵蓋該網域且權限為 `siteOwner` 才通過；`run_verification` 支援 `search_console`；`sync_search_console_ownership(connection, project)` 在連接時自動驗證涵蓋該專案網站的擁有者資源（管理員否決的網域不動）。
- `scans/seo_views.py`：GSC OAuth callback 成功後自動驗證，失敗只 log、不影響連接，導回帶 `verified=<網域>`。
- 前端：`/domains` 預設「Search Console（建議）」並連到對應網站專案的 SEO 分析頁連接；DNS／meta／驗證檔保留為備用；SEO 分析頁導回時提示已自動完成網域驗證。
- 隱私權政策：說明 Search Console 資源清單與權限也用於網域所有權驗證。
- 文件：scans／backend／frontend CLAUDE.md、需求書 F-036。

## 原因
使用者要求：Argus 已接 Google Search Console，網域驗證直接交給 Search Console。決策（使用者選擇）：Search Console 為主，舊三種方法保留備用。

## 影響範圍
- 只有 Search Console「擁有者」權限算數，使用者／受限權限不算（避免被加為使用者的人取得主動測試權限）。
- 既有已驗證網域不受影響；TTL 仍為 90 天。
- 主動測試的雙重閘門（宣告式授權＋網域驗證）不變。

## 驗證方式
- `manage.py test apps`、`ruff check backend`、`makemigrations --check`；`tests_seo_analysis.py` 新增 `SearchConsoleDomainVerificationTests`（涵蓋規則、擁有者通過、使用者權限不通過、未連接提示、連接自動驗證且不動否決紀錄與他站資源、Google 錯誤不影響連接）。
- 前端 lint、typecheck、`npm test`、build；新增 `DomainVerifyPage.test.tsx`。
- 未實機驗證：真實 Google 帳號連接後的自動驗證（需正式環境的 OAuth 用戶端）。
