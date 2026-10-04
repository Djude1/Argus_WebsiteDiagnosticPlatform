# Google 授權註冊＋用戶名與密碼、用戶名登入、自行刪除帳號

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `accounts/models.py`：`User` 新增 `handle`（用戶名，小寫唯一，可為空）、`deleted_at`；`needs_setup` 屬性。migration `0007_user_handle_and_deleted_at`。
- 新增 `accounts/signup.py`：Google ID Token 驗證（必須 email_verified）、簽章註冊憑證（salt `argus-google-signup`、15 分鐘）、用戶名規則與保留字、Email 或用戶名找帳號、建議用戶名。
- 新增 `accounts/deletion.py`：`delete_account()`——撤銷 GSC 授權、刪除專案／掃描／網域驗證／MCP／評論／登入紀錄／重設 token、匿名化購點訂單買受人資料、refresh token 全部加入黑名單、User 列匿名停用；檔案（只限 MEDIA_ROOT）在 commit 後刪。
- `accounts/views.py`／`urls.py`：
  - `POST register/google/`（註冊第一步）；`register/` 改為必須帶 `signup_token`＋`handle`＋`password`；`google/` 未註冊回 409＋`signup_token`，不再自動建帳號。
  - `email-login/` 接受 Email 或用戶名。
  - `POST me/setup/`（舊帳號補設）、`POST me/delete/`（自行刪除，密碼＋輸入「刪除帳號」，staff 403）。
  - `me/` 回 `handle`、`has_password`、`needs_setup`。
  - 註冊不再走 Turnstile（`signup` action 移除）。
- 前端：登入頁分頁改「登入／註冊」，註冊兩步驟（Google 授權 → 用戶名＋密碼＋條款）；`/account/setup` 補設頁與 `RequireAuth` 閘門；store `profile`／`fetchProfile`；設定頁顯示用戶名與「刪除帳號」區塊。
- 隱私權政策與服務條款更新註冊方式與自行刪除帳號說明（生效日 2026-10-04）。
- 文件：`backend/CLAUDE.md`、`backend/apps/accounts/CLAUDE.md`、`frontend/CLAUDE.md`、需求書 F-001。

## 原因
使用者要求：可完全刪除帳號；登入頁「新帳號」改為「註冊」；註冊一律以 Google 授權並設定用戶名與密碼。決策：個資全刪、帳務匿名保留；用戶名可用於登入；既有帳號下次登入時補設。

## 影響範圍
- 正式環境必須設定 `GOOGLE_OAUTH_CLIENT_ID` 才能註冊（未設定時註冊分頁顯示無法註冊，既有帳號仍可帳密登入）。
- 既有帳號（含原本只用 Google 登入、沒有密碼的帳號）登入後會先被導到 `/account/setup`。
- `CoinTransaction`、`AdminAuditLog` 不刪不改；掃描刪除時交易的 `scan_job`／`site_rebuild` 依既有 `SET_NULL` 設計變為空值。
- 管理員帳號不能自行刪除。

## 驗證方式
- `uv run python backend/manage.py test apps`、`ruff check backend`、`makemigrations --check`、`manage.py check`。
- 前端 `npm run lint`、`npm run typecheck`、`npm test`、build。
- 本機瀏覽器：舊帳號被導到補設頁並回到原頁、用戶名登入、從設定頁刪除帳號後落在 `/login?deleted=1`、資料已匿名；390px 無水平捲動。
