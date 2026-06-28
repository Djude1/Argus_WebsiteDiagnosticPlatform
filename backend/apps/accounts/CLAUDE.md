# accounts 模組規則

Claude 操作 `backend/apps/accounts/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

## 職責
自訂 `User`（繼承 `AbstractUser`，`username = email`）、登入 / 註冊、JWT 簽發、個人資料維護。**所有登入唯一入口**（含管理員）；本 app **不簽發 staff / superuser**（管理員亦以前台 email 登入後進 React `/admin`；staff/superuser 僅由 `manage.py seed_admin` 或 Django shell 設定。django-admin 已移除）。

## 關鍵端點（`/api/auth/`）
| 端點 | View | 說明 |
|---|---|---|
| `google/` | `GoogleLoginView` | 驗證 Google ID Token → `get_or_create` User（`AllowAny`） |
| `register/` | `EmailRegisterView` | email + 密碼（≥8 碼） |
| `email-login/` | `EmailLoginView` | `django_authenticate` → JWT |
| `me/` | `MeView` | GET 回傳 whitelist 個資；PATCH **僅可改 `first_name` / `last_name`**（`IsAuthenticated`） |
| `change-password/` | `ChangePasswordView` | 僅 email 帳號（Google 帳號無可用密碼） |

## 重點
- 認證用 **JWT**（`rest_framework_simplejwt`），**不是 session**。
- 每次登入都呼叫 `billing.services.grant_monthly_bonus_if_needed`（本月未領則補 200 coin）。
- `auth_provider` 由 `has_usable_password()` 推斷（`google` / `email`）。
- dev-login 後門已移除，勿復活。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 在 `MeView` 直接 dump user 全部欄位 | 個資外洩（含 password hash 等） | 維持手動 whitelist 欄位 |
| 在 auth 端點賦予 `is_staff` / `is_superuser` | 權限提升漏洞 | staff/superuser 僅能用 `manage.py seed_admin` 或 Django shell 設定 |
| 改用 session 認證或自寫 token | 破壞統一 JWT 流程 | 沿用 `RefreshToken.for_user` |
| 硬編碼 `GOOGLE_OAUTH_CLIENT_ID` | 機密外洩 | 放 `.env`，由 settings 讀取 |
