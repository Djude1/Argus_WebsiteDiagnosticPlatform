# 修復：連接 Search Console 出現 redirect_uri_mismatch

**日期**：2026-10-04  
**操作者**：Claude

## 症狀
正式站按「連接 Google Search Console」，Google 回 `錯誤 400：redirect_uri_mismatch`，請求詳情為 `redirect_uri=http://argus.clouda.dpdns.org/api/gsc/callback/`；Google 只登記了 `https://…`。

## 原因
`gsc.redirect_uri()` 用 `request.build_absolute_uri()` 組回呼網址；正式環境 cloudflared → Gateway 走 http，Gateway 傳下來的 `X-Forwarded-Proto` 是 `http`，Django 因此組出 `http://`。

## 變更內容
- `apps/scans/seo/gsc.py`：`redirect_uri()` 在 `DEBUG=False` 時把 `http://` 改成 `https://`（`ARGUS_GSC_REDIRECT_URI` 有值時仍以它為準）。帳號層級（`/domains`）與專案層級（SEO 分析頁）的授權與換 token 都走這個函式，兩邊一致。
- `tests_seo_analysis.py`：新增 `SearchConsoleRedirectUriTests`（正式環境強制 https、DEBUG 保留 http、設定值優先）。
- `backend/apps/scans/CLAUDE.md`：補充 https 規則與多網域時保持 `ARGUS_GSC_REDIRECT_URI` 空值。

## 驗證方式
- `ruff check backend`、`manage.py test apps.scans` 通過。
- 正式站待確認：部署後按連接，Google 授權頁不再出現 redirect_uri_mismatch，導回 `/domains?gsc=connected`。

## 已知相關風險（未處理）
密碼重設信的連結同樣用 `build_absolute_uri("/")`（`accounts/views.py`），在正式環境可能是 `http://`；Gateway 若不終止 TLS，應另行確認。
