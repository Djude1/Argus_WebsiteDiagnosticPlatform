# accounts 模組規則

Claude Code 進 `backend/apps/accounts/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

## 職責
自訂 `User`（繼承 `AbstractUser`，`username = email`）、登入 / 註冊、JWT 簽發、個人資料維護。**所有登入唯一入口**（含管理員）；本 app **不簽發 staff / superuser**（管理員亦以前台 email 登入後進 React `/admin`；staff/superuser 僅由 `manage.py seed_admin` 或 Django shell 設定。django-admin 已移除）。

## 關鍵端點（`/api/auth/`）
| 端點 | View | 說明 |
|---|---|---|
| `google/` | `GoogleLoginView` | 驗證 Google ID Token → `get_or_create` User（`AllowAny`） |
| `register/` | `EmailRegisterView` | email + 密碼（依 Django policy，至少 10 碼） |
| `email-login/` | `EmailLoginView` | `django_authenticate` → JWT |
| `refresh/` / `logout/` | `CookieTokenRefreshView` / `LogoutView` | HttpOnly refresh cookie 輪替與撤銷（CSRF 保護） |
| `me/` | `MeView` | GET 回傳 whitelist 個資（含 `avatar_url`）；PATCH **僅可改 `first_name` / `last_name`**（`IsAuthenticated`） |
| `me/avatar/` | `MeAvatarView` | POST（multipart 欄位 `avatar`）上傳大頭貼、DELETE 移除；`avatar_upload` throttle（預設 20/hour） |
| `change-password/` | `ChangePasswordView` | 僅 email 帳號（Google 帳號無可用密碼） |
| `password-reset/request/` / `confirm/` | Password reset views | 資料庫只保存 HMAC digest；raw token 只寄信且單次使用 |
| `turnstile/` | `TurnstileConfigView` | 公開：`{enabled, site_key}`，前端據此決定是否顯示 Turnstile 元件（不回 secret） |

## 重點
- 認證用 **JWT**（`rest_framework_simplejwt`），**不是 session**。Access token 只存在前端記憶體；refresh token 只放 HttpOnly cookie，禁止寫入 localStorage。
- Refresh 每次使用都原子輪替並撤銷舊 token；登出、變更密碼、完成密碼重設都撤銷 refresh token。
- 每次登入都呼叫 `billing.services.grant_monthly_bonus_if_needed`（本月未領則補 200 coin）。
- 三個實際登入入口（`EmailLoginView` / `GoogleLoginView` / `EmailRegisterView`）成功後都寫一筆 `LoginEvent`（method/password|google|register、IP 用 `config.client_ip.resolve_client_ip`、UA），並觸發 `billing.services.settle_subscription_safe`（訂閱 lazy 結算）；兩者都包 try/except，失敗不影響登入回應。後台查詢走 `GET /api/admin/users/<id>/login-events/`。
- `auth_provider` 由 `has_usable_password()` 推斷（`google` / `email`）。
- 大頭貼（`User.avatar`）：`avatars.process_avatar` 限 JPG／PNG／WebP、≤ 2 MB、≤ 25M 像素，Pillow 解碼後重新編碼成 256×256 PNG（丟棄 EXIF／ICC／polyglot），檔名 `uuid4().hex`；換圖或移除會刪舊檔。檔案由 `config/urls.py` 的 `serve_avatar`（`/media/avatars/<32 hex>.png`，`nosniff`＋sandbox CSP）提供。`/api/admin/me/` 也回 `avatar_url`（前端導覽列頭像）。
- **Cloudflare Turnstile（2026-10-03，`turnstile.py`）**：`register/`（action `signup`）、`email-login/`（`login`）、`password-reset/request/`（`password_reset`）與 `content` 的 `partner-inquiries/`（`contact`）在 view 開頭呼叫 `turnstile_rejection(request, action)`，未通過回 403 `{"code": "turnstile_failed"}`。伺服器端 siteverify（httpx、5 秒逾時、`remoteip` 用 `resolve_client_ip`）必須 `success is True`、`action` 相符、`hostname` 在 `TURNSTILE_HOSTNAMES` 內（設定讀取時由 `settings._bare_hostname` 正規化成純主機名：2026-10-03 正式 ConfigMap 曾誤填成 `https://xn--gst.tw`，而 siteverify 回的是 `xn--gst.tw`，會讓該網域所有驗證失敗）；任何例外都視為未通過（fail closed）。`TURNSTILE_SITE_KEY` 與 `TURNSTILE_SECRET` 都有值才啟用，未設定時完全不檢查（本機、CI）。Cloudflare 測試 secret 不回 action、hostname 固定 example.com，**只在 DEBUG** 時以 `metadata.result_with_testing_key` 放行。系統檢查（`checks.py`，一般 `manage.py check` 就跑，migrate Job／initContainer 都會執行）：W001 只設一半（警告，不擋部署——ConfigMap 先放 site key、再補 Secret 的過渡期）、E002 啟用但 hostname 清單空、E003 正式環境 hostname 含 localhost（兩者會讓所有驗證失敗，直接擋下）。只設一半時驗證是停用的，要看部署 log 的 W001。siteverify 逾時 5 秒。Google 登入不加（已有 Google 自己的驗證）。新增受保護的端點時沿用同一函式並給新的 action，前端用 `shared/TurnstileWidget.jsx`。
- dev-login 後門已移除，勿復活。
- `email-login/` 的狀態碼必須分開：**帳密錯誤回 401**，**欄位缺漏回 400**。
  兩者都回 400 會與 `DisallowedHost`、CSRF 等設定層錯誤同碼，線上排查時無法從
  狀態碼分辨「帳密錯」與「環境壞了」。前端 `api.js` 的 401 攔截器以
  `url.startsWith("/auth/")` 排除認證端點，故 401 不會觸發 refresh 或導向迴圈。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 在 `MeView` 直接 dump user 全部欄位 | 個資外洩（含 password hash 等） | 維持手動 whitelist 欄位 |
| 在 auth 端點賦予 `is_staff` / `is_superuser` | 權限提升漏洞 | staff/superuser 僅能用 `manage.py seed_admin` 或 Django shell 設定 |
| 改用 session 認證、自寫 token 或把 refresh 放 response body/localStorage | 破壞統一 JWT 與 cookie 安全邊界 | 沿用 `_auth_response` 與 HttpOnly cookie 流程 |
| 硬編碼 `GOOGLE_OAUTH_CLIENT_ID` | 機密外洩 | 放 `.env`，由 settings 讀取 |
