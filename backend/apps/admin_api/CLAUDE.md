# admin_api 模組規則

Claude Code 進 `backend/apps/admin_api/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

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
- `views.py`：`overview`、`users`、`users/<id>`、`users/<id>/adjust-coin`、`users/<id>/login-events`（最近 50 筆登入事件）、`users/<id>/subscription`（grant/cancel 訂閱）、`subscriptions/plans`（訂閱方案唯讀）、`transactions`、`reviews`、`reviews/<id>/reply`、`scans`、`scans/<id>`、`orders`、`dashboard`、`audit-log`、`announcements/*`
- `cms_views.py`：`cms/(features|team|releases|plans)` 寫入端點（ModelViewSet）
- `models.py`：`AdminAuditLog`（action：`coin_adjust` / `subscription_adjust` / `review_reply` / `review_delete` / `user_toggle_staff` / `other`；`log_admin_action()` 集中寫入、**失敗不擋業務**）、`Announcement`（常駐/臨時公告）
- `serializers.py`：輸出欄位 **whitelist**

## 重點
- 調點數一律走 `billing.services.admin_adjust`，**禁止**直接改 `CoinWallet`。
- 訂閱調整一律走 `billing.services.grant_subscription` / `cancel_subscription` / `settle_subscription`（grant 的稽核在 services 內寫、cancel 在 view 寫，各恰好一筆 `subscription_adjust`）。
- 每筆後台敏感操作都呼叫 `log_admin_action` 留痕。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 刪除 / 修改 `AdminAuditLog` | 破壞合規稽核軌跡 | 僅可查詢 |
| 直接 `CoinWallet` / `CoinTransaction` `.save()` | 繞過冪等與原子交易 | `billing.services.admin_adjust` |
| 在 `views` 直接 render 個資欄位 | 個資外洩 | 透過 serializer whitelist |
| 敏感操作不寫 audit | 合規破口 | 呼叫 `log_admin_action` |

## 評論檢舉治理

- `AdminReviewSerializer` 必須將使用者評論與官方回覆的檢舉數分開輸出，前端不得合併成無法辨識目標的單一數字。
- `moderate_review` 只處理 `response__isnull=True` 的父評論檢舉；隱藏或重新公開評論不得連帶結案官方回覆檢舉。
- `reported=true` 篩選仍需涵蓋任一目標有待審檢舉的評論，避免官方回覆檢舉從治理清單消失。
