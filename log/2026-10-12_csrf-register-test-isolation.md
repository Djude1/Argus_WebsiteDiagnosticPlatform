# 註冊端點補 CSRF、測試不受本機 Turnstile 設定影響

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
- `accounts/views.py`：`EmailRegisterView`（`register/`）、`GoogleRegisterStartView`（`register/google/`）加 `csrf_protect`
- 前端 `AuthPages.jsx`：兩個註冊呼叫前先 `ensureCsrfCookie()`
- `config/settings.py`：`RUNNING_TESTS` 時清空 `TURNSTILE_SITE_KEY`／`TURNSTILE_SECRET`
- 測試 `LoginCsrfTests.test_register_without_csrf_token_is_rejected`
- 文件：backend／accounts／frontend CLAUDE.md

## 原因
Codex 回報：
1. 帳號測試 51 項中 7 失敗 2 錯誤（回 403）
2. 註冊登入端點仍缺 CSRF 保護

查證：
- 第 1 點不是 CSRF 造成。設了 Turnstile 金鑰時，登入被 siteverify 擋成 403。CSRF 改動之前的 commit（4ecc6cb）在同樣設定下也是 13 失敗 2 錯誤；沒設金鑰時全部通過。
- 第 2 點屬實：`register/` 完成即發 refresh cookie，同樣有 login CSRF 風險。

## 影響範圍
- 註冊兩個端點需帶 CSRF token（前端已處理）
- 只影響 `manage.py test`；正式環境與 runserver 的 Turnstile 不受影響

## 驗證方式
- `manage.py test apps.accounts apps.content`：沒設與有設 Turnstile 金鑰各跑一次，80 項全部通過
- 設 Turnstile 金鑰跑 `manage.py test apps`：1919 項 OK（skipped 10）；`ruff check backend`、`manage.py check` 通過
- 前端 lint（0 error）、typecheck、`npm test` 286 項通過
