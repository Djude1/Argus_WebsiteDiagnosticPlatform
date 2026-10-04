# 綠界正式金流＋訂閱改為信用卡定期定額

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `config/settings.py`：`ARGUS_PAYMENT_MODE` 新增 `ecpay`（正式扣款）；`ARGUS_PAYMENT_ENABLED`；結帳／定期定額網址依模式自動決定（`ECPAY_CHECKOUT_URL` 有設定必須一致）；正式模式拒絕綠界公開測試商店代號；新增 `ECPAY_PERIOD_RETURN_URL`（未設定＝ReturnURL 同網域的 `/api/billing/ecpay/period-callback/`），三個回呼網址同樣檢查 HTTPS 443、合法網域、200 字元內。
- `billing/ecpay.py`：訂閱定期定額結帳欄位（`PeriodAmount=TotalAmount`、`PeriodType=M`、`Frequency=1`、`ExecTimes=99`、`PeriodReturnURL`）、`ARGUSS` 訂閱編號與 `parse_trade_no` 分流、`cancel_period_order`（CreditCardPeriodAction Cancel，失敗時以 QueryCreditCardPeriodInfo 確認是否已終止）。
- `billing/models.py`：`SubscriptionOrder`（定期定額委託＋發票資料）、`SubscriptionCharge`（每期扣款結果）、`UserSubscription.Source.ECPAY`；migration `0010_subscription_recurring`。
- `billing/services.py`：`activate_subscription_order`、`record_subscription_period_charge`（TotalSuccessTimes 冪等）、`record_subscription_failure`、`stop_recurring_charges`、`cancel_subscription_and_recurring`、`has_active_recurring`；自動續訂中到期給 3 天寬限；購點訂單備註不再寫「測試交易」。
- `billing/views.py`：`subscribe/` 改為建 pending 委託並回綠界結帳表單（不再模擬首月入點），需買受人／發票資料，已有自動扣款回 409；ReturnURL 同時處理購點與訂閱首期；新增 `ecpay/period-callback/`；取消訂閱先停止綠界扣款（失敗 502）。
- `admin_api`：後台取消訂閱同樣先停止扣款；新增 `GET /api/admin/subscription-charges/`；購點訂單 serializer 補載具欄位。
- `accounts/deletion.py`：刪除帳號前先停止綠界扣款（停不了就不刪），訂閱委託的買受人資料一併匿名。
- 前端：`components/billing/BuyerInvoiceFields.jsx`（購點與訂閱共用發票欄位、驗證、送出表單，只允許綠界兩個結帳網址）；購點頁依 `payment_mode` 顯示正式／測試文案；訂閱面板改為填發票資料 → 綠界綁卡付首期 → 返回後輪詢開通，顯示「每月自動扣款」；後台訂單頁新增「訂閱每期扣款」；公開 FAQ、服務條款與隱私權政策更新。
- 設定與文件：`.env.example`、`k8s/01-namespace-config.yaml`（移除 `ECPAY_CHECKOUT_URL`、註解切換正式的順序；模式仍維持 `ecpay_test`）、`k8s/02-secret.example.yaml`、`k8s/README.md`、README、使用說明、ONBOARDING、billing／backend／admin_api／frontend CLAUDE.md、需求書 F-024 與訂閱條目、設計文件。

## 原因
使用者要求訂閱付款機制完整、可正式付款（不要測試），並說明 `.env` 需配置哪些值。原本只能用綠界測試環境，訂閱還是「按下就視為付了首月」。電子發票依使用者決策先人工開立。

## 影響範圍
- K8s ConfigMap 仍是 `ecpay_test`：切正式必須先把 Secret 換成正式商店值，再改模式（順序寫在 k8s/README.md），否則 Django 拒絕啟動。
- 既有 `ecpay_test` 模擬開通的訂閱不受影響（沒有委託，取消只動本地狀態）。
- 付款模式改回 disabled 不會停止已綁定的每月扣款（通知會被拒絕、不入點）。

## 驗證方式
- `manage.py test apps`、`ruff check backend`、`makemigrations --check`；新增 `billing/tests_recurring.py`（表單欄位與簽章、首期／每月扣款冪等、偽造與金額不符拒絕、寬限期、409、取消成功／失敗／已終止、刪帳號先停扣款）與正式模式設定檢查測試。
- 前端 lint、typecheck、`npm test`、build；新增 `SubscriptionPanel.test.tsx`。
- 本機以假的正式商店值（`ARGUS_PAYMENT_MODE=ecpay`）實測：訂閱表單送往 `payment.ecpay.com.tw`，`PeriodAmount=TotalAmount`、`PeriodType=M`、`ExecTimes=99`、`PeriodReturnURL` 正確（請求被攔截，未真的送到綠界）；390px 無水平捲動、無 JS 錯誤。
- **未驗證（需要正式商店後實機確認）**：真實信用卡首期付款、隔月自動扣款通知、綠界取消 API 的實際回應格式。
