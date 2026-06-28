# admin_api 模組規則

Claude 操作 `backend/apps/admin_api/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

## 職責
React `/admin/*` 後台用的 REST API + `AdminAuditLog` 稽核。端點**刻意扁平、隱藏內部 model**（AgentSession / Page / Finding 等不外露）。

## 權限（超管 / 一般管理員分權）
登入唯一入口為前台 email / Google（`accounts`）；`is_staff` 才能進 React `/admin`，`is_superuser` 為超級管理員。授予 staff / superuser 只能用 `manage.py seed_admin`（或 shell），**auth 端點一律不簽發**（防權限提升）。

| 層級 | 可用功能 | 權限類別 |
|---|---|---|
| 一般管理員（is_staff） | 總覽 / 儀表板 / 使用者（檢視＋調點） / 交易 / 評論（回覆） / 掃描 / 訂單 / CMS（features·team·releases·plans） | `IsAdminUser` |
| 超級管理員（is_superuser） | 上述全部 ＋ 操作日誌（audit-log） ＋ 公告管理（announcements） | `IsSuperuser` |

前端 `AdminLayout` 依 `me.is_superuser` 顯示「操作日誌📜 / 公告管理📢」，與後端 `IsSuperuser` 一致。（django-admin 已移除，不再有第二後台。）

## 關鍵檔案 / 端點（`/api/admin/`）
- `views.py`：`overview`、`users`、`users/<id>`、`users/<id>/adjust-coin`、`transactions`、`reviews`、`reviews/<id>/reply`、`scans`、`scans/<id>`、`orders`、`dashboard`、`audit-log`、`announcements/*`
- `cms_views.py`：`cms/(features|team|releases|plans)` 寫入端點（ModelViewSet）
- `models.py`：`AdminAuditLog`（action：`coin_adjust` / `review_reply` / `review_delete` / `user_toggle_staff` / `other`；`log_admin_action()` 集中寫入、**失敗不擋業務**）、`Announcement`（常駐/臨時公告）
- `serializers.py`：輸出欄位 **whitelist**

## 重點
- 調點數一律走 `billing.services.admin_adjust`，**禁止**直接改 `CoinWallet`。
- 每筆後台敏感操作都呼叫 `log_admin_action` 留痕。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 刪除 / 修改 `AdminAuditLog` | 破壞合規稽核軌跡 | 僅可查詢 |
| 直接 `CoinWallet` / `CoinTransaction` `.save()` | 繞過冪等與原子交易 | `billing.services.admin_adjust` |
| 在 `views` 直接 render 個資欄位 | 個資外洩 | 透過 serializer whitelist |
| 敏感操作不寫 audit | 合規破口 | 呼叫 `log_admin_action` |
