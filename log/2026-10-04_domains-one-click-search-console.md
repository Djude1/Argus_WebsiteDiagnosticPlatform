# 網域驗證頁一鍵連接 Search Console＋頁面改版

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `SearchConsoleConnection.project` 改為可為空（帳號層級連線，每人最多一筆；migration `0024_search_console_account_level`，models.py 維持 CRLF）。
- `seo/gsc.build_authorization(request, project=None)`：帳號層級 state 的 `p` 為 null；callback 走 `_account_callback`，導回 `/domains?gsc=connected&verified=<數量>`（Google 讀取失敗時 `synced=0`，連接仍成功）。
- `domain_verification.sync_owned_domains`：Search Console 裡是擁有者的網站全部匯入為已驗證網域，並驗證清單中被涵蓋、尚未生效的網域（管理員否決的不動）。
- 新端點：`GET/DELETE /api/domains/gsc/`、`POST /api/domains/gsc/connect/`、`POST /api/domains/gsc/sync/`（`scans/urls.py` 排在 router 前；CRLF）；`GET /api/domains/<id>/` 另附自己的 token 與備用方法說明（`views.py`，CRLF）。
- 刪除帳號：撤銷並刪除使用者全部 Search Console 連線（原本只處理專案的）。
- 前端 `/domains` 改版：Search Console 一鍵驗證卡（未連接／已連接／重新同步／中斷）、導回結果提示、網域統計、待處理排前、每列「用 Search Console 驗證／續期」、「其他驗證方式」展開 DNS／meta／驗證檔、「手動新增網域」收合；樣式 `legacy-member/61-domain-verify.css`。
- 隱私權政策：連接位置與授權憑證保存期限補上網域驗證頁。
- 文件：frontend／backend／scans CLAUDE.md、需求書 F-036。

## 原因
使用者回報：驗證失敗訊息叫人到另一個專案頁連接 Search Console，很反直覺，希望在 /domains 直接點擊連接（或註冊時就接好），並覺得頁面簡陋。註冊時就要求 Search Console 權限未採用：會讓每位新使用者在註冊時看到敏感權限同意畫面（OAuth 同意畫面尚未通過 Google 審核時還會出現「未經驗證的應用程式」警告），且多數使用者沒有 Search Console。

## 影響範圍
- 專案層級連線（SEO 分析頁）行為不變；兩種連線都能用來驗證網域。
- 主動測試的雙重閘門不變，只認 Search Console「擁有者」權限。

## 驗證方式
- `manage.py test apps`、`ruff check backend`、`makemigrations --check`；新增 `AccountLevelSearchConsoleTests`、`DomainDetailInstructionsTests`。
- 前端 lint、typecheck、`npm test`、build；`DomainVerifyPage.test.tsx` 改寫（一鍵連接、Search Console 驗證、導回提示、其他驗證方式）。
- 本機瀏覽器：日／夜主題、已連接狀態、展開備用方法、點「連接」會導向 Google 授權網址（攔截）、390px 無水平捲動、無 JS 錯誤。
- 未實機驗證：真實 Google 帳號授權後的匯入（需要正式 OAuth 用戶端與 redirect URI）。
