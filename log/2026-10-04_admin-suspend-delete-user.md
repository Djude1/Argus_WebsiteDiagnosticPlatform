# 管理員可自行刪除帳號；後台停用（封號）與刪除使用者

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `accounts/deletion.py`：移除「staff／superuser 不能刪除」限制，改為只擋最後一位啟用中的 superuser；刪除時一併清除 `is_staff`／`is_superuser`。
- `accounts/views.py`：`DeleteAccountView` 不再擋管理員，`PermissionError` 回 403；新增 `_suspended_response()`（403 `account_suspended`），密碼登入（密碼正確時）、Google 登入、Google 註冊第一步遇到停用帳號回 403。`signup.find_login_user` 新增 `suspended=True` 參數。
- `admin_api`：新增 `POST users/<id>/suspend/`（停用／恢復，停用時撤銷 refresh token）與 `POST users/<id>/delete/`（需 `confirm="刪除帳號"`，呼叫 `delete_account`）；共用 `_manage_target_error`（不能對自己、superuser、已刪除帳號；對象是 staff 時只有 superuser 可以）。`AdminAuditLog.Action` 新增 `user_suspend`、`user_delete`（migration 0007，只改 choices）；刪除的稽核只記「使用者 #id」。使用者列表／詳情 serializer 輸出 `is_active`、`deleted_at`。
- 前端：設定頁管理員也顯示刪除表單（提示會失去管理權限）；後台使用者詳情新增「帳號狀態」區塊（原因、停用／恢復、輸入「刪除帳號」後刪除），列表與詳情顯示「已停用／已刪除」標籤；操作日誌動作標籤補 2 種。重新產生 `openapi.json`／`apiTypes.ts`。
- 文件：accounts／admin_api／frontend CLAUDE.md、需求書 F-001／F-027。

## 原因
使用者回報設定頁顯示「管理員帳號不能自行刪除」，要求用戶都能自己決定刪除帳號；並要求管理後台可以對用戶封號或刪除。

## 影響範圍
- 停用帳號資料全部保留，可恢復；刪除與使用者自行刪除規則相同（個資全刪、`CoinTransaction`／`AdminAuditLog` 不動）。
- 最後一位超級管理員無法刪除自己，需先用 `seed_admin` 指定另一位。

## 驗證方式
- `manage.py test apps`、`ruff check backend`、`makemigrations --check`。
- 前端 lint、typecheck、`npm test`（197 項）、build。
- 本機瀏覽器：一般管理員停用使用者 → 該使用者重新整理被登出、登入顯示「此帳號已被停用」；刪除另一使用者 → 列表顯示「已刪除」；管理員的設定頁顯示刪除表單；無 JS 錯誤。
