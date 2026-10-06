# Search Console：網域驗證連一次，SEO 分析自動連好並選好資源

**日期**：2026-10-06  
**操作者**：Claude

## 變更內容
- `backend/apps/scans/seo_views.py`：
  - 新增 `_ensure_project_connection`（取代 `_adopt_account_connection`）、`pick_property`、`link_user_projects`。
  - SEO 分析資料端點 `GET /api/projects/<id>/seo/` 也會沿用授權並自動選資源。
  - 網域驗證頁 OAuth callback 立刻連好使用者所有網站專案，並修復授權已失效的專案連線。
  - 專案自己的 OAuth callback 連好後也自動選資源。
  - 「更換資源」後 24 小時內不自動選回。
- `frontend/src/features/projects/ProjectSeoPage.jsx`：OAuth 導回提示改為顯示自動選到的資源。
- `backend/apps/scans/tests_seo_analysis.py`：新增兩個情境測試。
- `backend/apps/scans/CLAUDE.md`：同步規則。

## 原因
使用者回報上一版沒有生效，兩個原因：
1. SEO 分析頁讀的是 `GET seo/` 回傳的 `gsc` 狀態，上一版只在 `GET gsc/` 沿用授權。
2. 只有「新建立的連線且剛好一個相符資源」才自動選。網域資源與網址前置字元資源同時相符時，不會自動選。已經連過但沒選資源的專案也不會被處理。

## 影響範圍
- 只影響 Search Console 連線與資源選擇，不動 OAuth 安全機制（state＋nonce、加密 token）。
- 自動選資源會呼叫一次 Google `sites.list`；選不到時快取 10 分鐘，不會每次載入都打 API。

## 驗證方式
- `tests_seo_analysis` 51 項通過，含：
  - 網域驗證頁連接後，既有專案已連好並選好 `sc-domain:`，`GET seo/` 不再呼叫 Google。
  - 已連接但沒選資源的專案載入 SEO 頁即自動選網域資源。
  - 更換資源後不被自動選回。
- `ruff`、前端 lint 與 SEO 頁測試通過。
- 需在正式環境以真實 Google 帳號確認。
