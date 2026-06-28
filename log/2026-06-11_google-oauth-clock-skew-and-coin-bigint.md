# 2026-06-11 修復 Google 登入失敗（學校帳號）

## 變更內容

修兩個根因，都對應使用者回報「Google 登入失敗，請稍後再試。」：

### A. `backend/apps/accounts/views.py`

`GoogleLoginView.post()` 呼叫 `id_token.verify_oauth2_token(...)` 補上 `clock_skew_in_seconds=10`。

### B. `backend/apps/billing/models.py` + `migrations/0005_alter_cointransaction_amount_and_more.py`

`CoinWallet` / `CoinTransaction` 五個欄位由 `PositiveIntegerField` / `IntegerField` 升級為 `PositiveBigIntegerField` / `BigIntegerField`：

| Model | 欄位 | 改前 | 改後 |
|---|---|---|---|
| CoinWallet | `balance` | PositiveIntegerField | PositiveBigIntegerField |
| CoinWallet | `total_purchased_ntd` | PositiveIntegerField | PositiveBigIntegerField |
| CoinWallet | `total_scans_used` | PositiveIntegerField | PositiveBigIntegerField |
| CoinTransaction | `amount` | IntegerField | BigIntegerField |
| CoinTransaction | `balance_after` | PositiveIntegerField | PositiveBigIntegerField |

## 原因

學校帳號 `11246034@ntub.edu.tw` 登入觸發 500，trace 揭露兩層獨立 root cause，後者被前者掩蓋：

1. **時鐘漂移**：本機 host (WSL2 vm) 比 Google UTC 慢約 2 秒（sleep/resume 後 vm 未自動 NTP 同步）→ Google 簽發 ID Token 的 `iat = 1781155999`，container 收到時 `now = 1781155997` → `_verify_iat_and_exp` 預設 `clock_skew_in_seconds=0` 零容忍 → 拋 `InvalidValue: Token used too early` → view 的 `except ValueError` 接住回 400 `"Google ID Token 無效或已過期。"`。
2. **balance 爆 int32**：該 user wallet `balance` 已被刷到 `2,147,483,847`（≈ int32 max），登入時 `grant_monthly_bonus_if_needed` 嘗試 `+200` → PostgreSQL 拋 `psycopg.errors.NumericValueOutOfRange: integer out of range` → 非 ValueError，未被 view 接住 → 500。

一般 Gmail 帳號因 balance 未爆，僅卡 (1)；clock_skew 補上後它先 OK。學校帳號 balance 爆，所以 (1) 過了之後跳到 (2) 才現形。

## 影響範圍

- `/api/auth/google/`：所有 Google 登入請求現在容忍 ±10 秒時鐘漂移。
- `/api/billing/*` 與所有 `CoinWallet` / `CoinTransaction` 讀寫：型別擴大至 int64（≈ 9.2 × 10^18），既有資料不變。
- DB schema：`billing_coinwallet.balance` / `total_purchased_ntd` / `total_scans_used` / `billing_cointransaction.amount` / `balance_after` 五欄改為 bigint，由 `0005_alter_cointransaction_amount_and_more` 自動套用。

## 驗證方式

1. `uv run ruff check backend/apps/accounts backend/apps/billing` → All checks passed
2. `uv run python backend/manage.py check` → 0 issues
3. `uv run python backend/manage.py test apps.accounts apps.billing` → 全綠
4. `docker compose up -d --build web` → 自動 `migrate` 套用 `billing.0005` OK
5. 公網實測：學校帳號 `11246034@ntub.edu.tw` Google 登入成功（先前穩定 500）；一般 Gmail 帳號維持成功。

## 後續

- WSL2 時鐘漂移是 host 端 known issue，建議定期 `w32tm /resync` 或重啟 Docker Desktop；clock_skew=10 是防護網，不是替代品。
- 既有 wallet `balance ≈ 2,147,483,847` 的歷史紀錄保留（為了稽核軌跡），但因型別擴大，後續加點 / 扣點不再爆庫。
