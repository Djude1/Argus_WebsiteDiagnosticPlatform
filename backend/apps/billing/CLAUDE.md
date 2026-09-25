# billing 模組規則

Claude Code 進 `backend/apps/billing/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

---

## 唯一入口原則（最重要）

**所有 `CoinWallet` 餘額寫入必須經過 `billing/services.py`。**

禁止直接呼叫：
```python
# 禁止
wallet.balance += 100
wallet.save()

# 禁止
CoinTransaction.objects.create(...)
```

正確做法：
```python
# 正確 — 使用 services.py 的函式
from apps.billing.services import grant_monthly_bonus_if_needed, refund_full_for_scan
```

原因：`services.py` 封裝了 `select_for_update()` + `transaction.atomic()` + 冪等判斷。繞過會導致 race condition（兩個 worker 同時扣款）或重複計費。

---

## services.py 函式一覽

| 函式（實際簽章） | 說明 | 冪等 |
|---|---|---|
| `get_or_create_wallet(user)` | 取得或建立錢包 | ✅ |
| `grant_monthly_bonus_if_needed(user)` | 月贈點 200 coin | ✅ 同月第二次不執行 |
| `estimate_scan_cost(max_pages, categories=None)` | 估算掃描所需 coin（`max_pages × 勾選維度數 × ARGUS_COIN_PER_CATEGORY`；categories 省略＝五維全選，全選價與舊每頁定價相同） | 純計算 |
| `hold_for_scan(user, scan_job)` | 掃描開始前預扣（`max_pages × 維度數 × 每維單價`） | 否 |
| `settle_scan_actual(user, scan_job, actual_pages)` | 掃描完成後結算，依實際頁數 × 同組維度退還差額 | 否 |
| `refund_full_for_scan(user, scan_job, *, reason)` | 取消或失敗時全退 | ✅ 可重複呼叫 |
| `purchase_plan(user, plan)` | 購買方案入帳 | 否 |
| `admin_adjust(*, target_user, delta, admin_actor, note)` | 管理員手動調整 | 否 |
| `grant_fixgen_entitlement(user, scan_job)` | 付費掃描結算後附贈 1 次修正產出額度（淨扣 0 不贈） | ✅ 同掃描只贈一次 |
| `fixgen_entitlement_available(user, scan_job)` | 該掃描的產生額度是否可用（純查詢） | 純查詢 |
| `charge_fixgen_generation(user, scan_job)` | 觸發修正產出前計費：額度內 0 元消耗、額度外扣 `ARGUS_COIN_FIXGEN_GENERATION` 固定點數 | 否 |
| `refund_fixgen_generation(user, scan_job)` | 產生失敗退費：點數退點、額度返還（amount=0） | ✅ 無可退回 None |
| `is_paid_tier(user)` | free/paid 二級自動判定（曾購點數包或完成付費掃描即 paid） | 純查詢 |
| `grant_subscription(user, plan, periods, *, source, admin_actor=None)` | 建立或延長訂閱（periods_remaining 累加；首次 current_period_end=now；admin 操作傳 admin_actor 寫 AdminAuditLog） | 否 |
| `settle_subscription(user)` | 訂閱 lazy 結算：到期期數逐月補發 `monthly_coins`（kind=subscription_grant）；cancelled 只補已開始的當期；期數歸零且過期 → expired | ✅ 交易鎖＋last_grant_period 同期不重發 |
| `cancel_subscription(user)` | status=cancelled＋cancelled_at（冪等；當期權益保留到期滿） | ✅ 重複取消不動 |
| `settle_subscription_safe(user)` | settle 的輕量包裝：失敗只記 log（登入／API 進場觸發用） | — |

---

## 掃描維度計費（2026-09-26）

- 費用＝`頁數 × 勾選維度數 × ARGUS_COIN_PER_CATEGORY`（預設 2；五維全選＝每頁 10 coin，與舊 `ARGUS_COIN_PER_PAGE` 定價等價——該設定已移除，wallet API 改暴露 `coin_per_category`）
- 維度清單事實來源在 `apps/scans.models.ALL_CATEGORIES`；`ScanJob.effective_categories` 過濾未知值、空集合退回全開（舊資料相容）
- hold 與 settle 用**同一組維度**計價：預扣與結算不對稱會導致多退或少退
- 未勾維度＝該維度不掃描、不計分（`tested_categories` 交集，見 scans/CLAUDE.md）

---

## 冪等機制說明

`refund_full_for_scan` 設計為可安全重複呼叫：
- Worker 完成後呼叫一次
- Cancel API 也可能呼叫一次
- 兩者都呼叫是安全的，第二次呼叫會被冪等邏輯擋住

`grant_monthly_bonus_if_needed` 利用 `last_bonus_year` / `last_bonus_month` 欄位判斷是否已執行。

## 金流模式

- `ARGUS_PAYMENT_MODE` 只允許 `disabled`（預設）或 `ecpay_test`。
- `disabled` 時購點 API 回 503，且不得建立訂單或入點。
- `ecpay_test` 只能送往綠界 `payment-stage`；建立訂單時維持 pending，ReturnURL 驗證 CheckMacValue、MerchantID、MerchantTradeNo、TradeAmt 後才呼叫 `complete_purchase_order()` 冪等入點。
- `SimulatePaid=1` 是綠界後台測試 ReturnURL 的模擬通知，不代表消費者付款，必須回 `1|OK` 但禁止入點。
- HashKey / HashIV 只放 `.env`，不得寫進程式、測試 fixture、log 或前端。

## 輕量訂閱（無週期扣款、無新基礎設施）

- Model：`SubscriptionPlan`（方案清單，seed migration 建立內建方案）/ `UserSubscription`（OneToOne；`periods_remaining` 預付期數、`current_period_end` 下次贈點時間、`last_grant_period` 同月冪等）。
- lazy 結算：沒有 celery beat——`settle_subscription` 掛在①登入成功後②`wallet/` 與 `subscription/*` API 進場時（用 `settle_subscription_safe`，失敗只 log）。
- 端點：`GET /api/billing/subscription/plans/`（公開）、`GET /api/billing/subscription/`（自己；無訂閱回 null）、`POST /api/billing/subscription/subscribe/`、`POST /api/billing/subscription/cancel/`。
- `subscribe/` 行為比照 purchase：`ARGUS_PAYMENT_MODE != "ecpay_test"` 回 503 不入點；`ecpay_test` 模擬首月一次付款（不接綠界定期定額），直接 `grant_subscription`＋`settle_subscription` 入帳。
- 月份前進用 `_advance_month`（calendar 安全，1/31 → 2/28），禁止手寫 `month + 1`。
- 後台調整：`POST /api/admin/users/<id>/subscription/`（grant/cancel，寫 `AdminAuditLog(action=subscription_adjust)`）；`GET /api/admin/subscriptions/plans/`（方案唯讀）。

---

## CoinTransaction.kind 枚舉值

欄位名是 `kind`（不是 `type`）；只能使用以下值，禁止自創字串：

| kind | 說明 |
|---|---|
| `monthly_bonus` | 每月贈點（200 coin） |
| `purchase` | 購買入帳 |
| `scan_hold` | 掃描預扣 |
| `scan_refund` | 掃描退款（涵蓋完成結算退差與取消/失敗全退） |
| `admin_adjust` | 管理員手動調整 |
| `rebuild_hold` | 網頁複刻預扣 |
| `rebuild_refund` | 網頁複刻退款 |
| `fixgen_grant` | 修正產出額度贈與（amount=0，付費掃描附贈） |
| `fixgen_charge` | 修正產出扣款（額度內 amount=0、額度外負數固定點數） |
| `fixgen_refund` | 修正產出退款（點數退正數、額度返還 amount=0） |
| `subscription_grant` | 訂閱月贈點（每月 `monthly_coins`，由 settle_subscription 補發） |

---

## signals.py

Billing 事件訂閱只在 `signals.py` 中處理，禁止在 `views.py` 或 `tasks.py` 中直接訂閱 Django signals。

---

## 禁止事項

| 禁止 | 原因 |
|---|---|
| 直接 `.save()` CoinWallet | Race condition 風險 |
| 直接 `.create()` CoinTransaction | 繞過原子交易 |
| 修改已存在的 CoinTransaction | 破壞稽核軌跡 |
| 刪除 CoinWallet / CoinTransaction | 計費資料永久遺失 |
| 在 `views.py` 手動扣款邏輯 | 邏輯應集中在 services.py |
| callback 未驗 CheckMacValue / 訂單編號 / 金額就入點 | 可偽造或錯帳 |
| 對 `SimulatePaid=1` 入點 | 綠界官方明示這只是 ReturnURL 測試通知 |
