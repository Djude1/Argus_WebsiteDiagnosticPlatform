# 新增 GET/PATCH /api/auth/me/ 與 POST /api/auth/change-password/

**日期**：2026-05-26  
**操作者**：Claude

## 變更內容
- `backend/apps/accounts/views.py`：新增 `MeView`（GET/PATCH）與 `ChangePasswordView`（POST）兩個 class
- `backend/apps/accounts/urls.py`：新增 `me/` 與 `change-password/` 兩條路由，同步更新 import

## 原因
使用者請求新增個人資料查詢/更新端點與密碼變更端點，供前端帳號設定頁使用。

## 影響範圍
- `GET /api/auth/me/`：回傳登入使用者的基本資料（id、email、display_name、first_name、last_name、is_staff、date_joined、last_login、auth_provider）
- `PATCH /api/auth/me/`：允許更新 first_name / last_name
- `POST /api/auth/change-password/`：驗證舊密碼後設定新密碼（新密碼須 ≥ 8 字元），Google OAuth 使用者因無可用密碼（`has_usable_password()` 返回 False）呼叫此端點會舊密碼驗證失敗
- 所有端點均需 `IsAuthenticated`，未登入回 401

## 驗證方式
- `python manage.py check`：無任何錯誤
- `python manage.py test apps.accounts -v 2`：14 項測試全部 pass
