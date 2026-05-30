# 新增 Email 帳號註冊與登入端點

**日期**：2026-05-26  
**操作者**：Claude Sonnet 4.6

## 變更內容
- `backend/apps/accounts/views.py`：新增 `EmailRegisterView`（`POST /api/auth/register/`）與 `EmailLoginView`（`POST /api/auth/email-login/`）兩個 View
- `backend/apps/accounts/urls.py`：加入 `register/` 與 `email-login/` 兩條路由，並 import 新 View
- `backend/apps/accounts/tests.py`：末尾加入 `EmailAuthTests` 測試類別（4 個測試方法）

## 原因
Phase 1 Task 1.2：新增 Email 帳號認證端點，讓使用者可使用 email+password 方式建立帳號與登入，回傳 JWT（access + refresh token），補充現有 Google OAuth 登入方式。

## 影響範圍
- 新增兩個公開端點（`AllowAny`），不影響現有 Google OAuth 與 DevLogin 流程
- 新用戶透過 `register/` 建立帳號後同樣會觸發 `grant_monthly_bonus_if_needed`（首月 200 coin 贈點）
- `username=email`（小寫），與 Google OAuth 的命名慣例一致

## 驗證方式
- TDD：先加測試確認 4 項全 FAIL（404），再實作讓測試通過
- `EmailAuthTests` 4 項 pass（`test_register_creates_user`、`test_register_duplicate_email_fails`、`test_email_login_returns_token`、`test_email_login_wrong_password_fails`）
- 全部 `apps.accounts` 測試 14 項全部 pass（含原有 Google/Dev Login 測試）
