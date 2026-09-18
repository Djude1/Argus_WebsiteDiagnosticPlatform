# LoginEvent 登入事件記錄＋輕量訂閱制 backend

**日期**：2026-09-19
**操作者**：ZCode（subagent，主 session 統一 commit）

## 變更內容

### 任務 A：LoginEvent（登入成功事件記錄）
- `backend/apps/accounts/models.py`：新增 `LoginEvent`（user FK related_name="login_events"、method=password/google/register、ip_address、user_agent、created_at；Meta ordering=-created_at）。
- `backend/apps/accounts/views.py`：新增 `_record_login_event()` helper（try/except 包住，失敗只 log）；三個實際登入入口（`EmailLoginView`、`GoogleLoginView`、`EmailRegisterView`＝註冊即自動登入）成功後各寫一筆，IP 沿用 `config.client_ip.resolve_client_ip`（與 PasswordResetRequestView 同慣例）。
- `backend/apps/admin_api/`：新增 `GET /api/admin/users/<id>/login-events/`（IsAdminUser、最近 50 筆、serializer whitelist：method/method_label/ip_address/user_agent/created_at）。
- migration：`accounts/migrations/0005_loginevent.py`。

### 任務 B：輕量訂閱（無週期扣款、無新基礎設施、lazy 結算）
- `backend/apps/billing/models.py`：新增 `SubscriptionPlan`（code/name/monthly_price_ntd/monthly_coins/features(JSON)/badge/sort_order/is_active；clean() 驗證金額>0）與 `UserSubscription`（user OneToOne related_name="subscription"、plan PROTECT、status=active/cancelled/expired、periods_remaining、current_period_end=下次贈點時間、last_grant_period="YYYY-MM" 冪等、source=admin_grant/ecpay_test、cancelled_at）；`CoinTransaction.Kind` 新增 `subscription_grant`。
- `backend/apps/billing/services.py`（維持唯一寫入入口）：
  - `_advance_month()`：calendar 安全月份前進（1/31 → 2/28）。
  - `grant_subscription(user, plan, periods, *, source, admin_actor=None)`：建立/延長訂閱；admin_actor 供稽核（services 內寫 AdminAuditLog，比照 admin_adjust）。
  - `settle_subscription(user)`：lazy 結算——active 到期逐月補發 monthly_coins（select_for_update＋last_grant_period 冪等）；cancelled 只補「取消時已開始」的當期；期數歸零且過期 → expired。
  - `cancel_subscription(user)`：status=cancelled＋cancelled_at（冪等）。
  - `settle_subscription_safe(user)`：失敗只 log 的輕量包裝（登入／API 進場觸發用）。
- 觸發點：①三個登入成功後緊跟 LoginEvent；②`GET wallet/` 與 `subscription/*` API 進場。
- `backend/apps/billing/serializers.py`/`views.py`/`urls.py`：`GET /api/billing/subscription/plans/`（公開）、`GET /api/billing/subscription/`（無訂閱回 null）、`POST /api/billing/subscription/subscribe/`（disabled → 503 文案比照 purchase；ecpay_test → 首月一次付款模擬直接入帳）、`POST /api/billing/subscription/cancel/`（無訂閱 404）。
- `backend/apps/admin_api/`：`POST /api/admin/users/<id>/subscription/`（action=grant|cancel；走 log_admin_action，`AdminAuditLog.Action` 新增 `subscription_adjust`）、`GET /api/admin/subscriptions/plans/`（方案唯讀，本 wave 不做 CRUD）。
- migration：`billing/migrations/0008_subscriptionplan_alter_cointransaction_kind_and_more.py`（schema）＋ `0009_seed_subscription_plans.py`（seed sub-lite/sub-pro/sub-team 三個內建方案）。
- 測試：`accounts/tests.py` 新增 LoginEventTests（4 項）；`billing/tests_subscription.py` 新檔（23 項：冪等、期數耗盡 expired、cancel 語意、grant 延長、subscribe 503/ecpay_test、wallet lazy 結算、_advance_month 日曆安全）；`admin_api/tests.py` 新增 UserLoginEventsTests（3 項）＋AdminSubscriptionTests（6 項）。
- 文件同步：`backend/CLAUDE.md`、`accounts/CLAUDE.md`、`billing/CLAUDE.md`、`admin_api/CLAUDE.md`（路由地圖、model 速查、services 一覽、kind/action 枚舉、端點清單）。

## 原因
- 後台需要登入事件（IP/UA/時間）做資安檢視（異常 IP 頻繁登入）。
- 輕量訂閱制：無週期扣款、無 celery beat，以預付期數＋lazy 結算提供月繳方案；ecpay_test 模擬首月付款。

## 影響範圍
- 三個登入入口每次成功多一筆 LoginEvent INSERT 與一次訂閱查詢（皆失敗不擋登入）。
- `GET /api/billing/wallet/` 進場多一次 lazy 結算（無訂閱時僅一次 SELECT）。
- `CoinTransaction.kind` 新值 `subscription_grant`（舊資料不受影響）。
- `AdminAuditLog.Action` 新值 `subscription_adjust`（TextChoices 加選項，既有 code 相容）。
- 需 `makemigrations` 已產出、部署時需 `migrate`。

## 驗證方式
- `uv run python backend/manage.py check` → 0 issues。
- `uv run ruff check backend/apps/accounts backend/apps/billing backend/apps/admin_api` → All checks passed。
- `uv run python backend/manage.py test apps.accounts apps.billing apps.admin_api` → 147 tests OK（accounts 23／billing 76／admin_api 48）。
