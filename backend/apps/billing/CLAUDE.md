# billing 模組規則

Claude 操作 `backend/apps/billing/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

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
| `estimate_scan_cost(max_pages)` | 估算掃描所需 coin（`max_pages × coin_per_page`） | 純計算 |
| `hold_for_scan(user, scan_job)` | 掃描開始前預扣（`max_pages × 10` coin） | 否 |
| `settle_scan_actual(user, scan_job, actual_pages)` | 掃描完成後結算，退還差額 | 否 |
| `refund_full_for_scan(user, scan_job, *, reason)` | 取消或失敗時全退 | ✅ 可重複呼叫 |
| `purchase_plan(user, plan)` | 購買方案入帳 | 否 |
| `admin_adjust(*, target_user, delta, admin_actor, note)` | 管理員手動調整 | 否 |

---

## 冪等機制說明

`refund_full_for_scan` 設計為可安全重複呼叫：
- Worker 完成後呼叫一次
- Cancel API 也可能呼叫一次
- 兩者都呼叫是安全的，第二次呼叫會被冪等邏輯擋住

`grant_monthly_bonus_if_needed` 利用 `last_bonus_year` / `last_bonus_month` 欄位判斷是否已執行。

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
