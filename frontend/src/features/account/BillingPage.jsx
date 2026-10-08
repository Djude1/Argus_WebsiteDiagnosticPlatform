// 購點頁：依使用者要求恢復為 462848b（Night Watch 改版前）的版本。
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import {
  BuyerInvoiceFields,
  EMPTY_BUYER,
  buyerPayload,
  submitEcpayForm,
  validateBuyer,
} from "../../components/billing/BuyerInvoiceFields";
import { CoinHistory } from "../../components/billing/CoinHistory";
import { SubscriptionPanel } from "./SubscriptionPanel";

// ============================================================
// Billing 頁（購點方案＋月訂閱；綠界測試或正式環境依後端 payment_mode）
// ============================================================

// ----- BillingPage 3 步驟 wizard -----

const WIZARD_STEPS = [
  { id: 1, label: "選擇商品" },
  { id: 2, label: "填寫資料" },
  { id: 3, label: "確認訂購" },
];

function WizardStepper({ current }) {
  return (
    <ol className="wizard-stepper" aria-label="購買流程">
      {WIZARD_STEPS.map((step) => {
        const state = step.id < current ? "done" : step.id === current ? "active" : "pending";
        return (
          <li
            key={step.id}
            className={`wizard-step ${state}`}
            aria-current={state === "active" ? "step" : undefined}
          >
            <span className="wizard-step-circle" aria-hidden="true">
              {state === "done" ? "✓" : step.id}
            </span>
            <span className="wizard-step-copy">
              <span className="wizard-step-kicker">步驟 {step.id}</span>
              <span className="wizard-step-label">{step.label}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function BillingPage() {
  const [plans, setPlans] = useState([]);
  const [paymentMode, setPaymentMode] = useState("disabled");
  const [step, setStep] = useState(1);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const [completedOrder, setCompletedOrder] = useState(null);
  const wallet = useArgusStore((s) => s.wallet);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);
  const me = useArgusStore((s) => s.me);
  const fetchMe = useArgusStore((s) => s.fetchMe);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [buyer, setBuyer] = useState(EMPTY_BUYER);
  // ecpay＝正式扣款、ecpay_test＝綠界測試環境、disabled＝暫停
  const live = paymentMode === "ecpay";
  const enabled = paymentMode === "ecpay" || paymentMode === "ecpay_test";

  useEffect(() => {
    api.get("/billing/plans/").then((r) => {
      setPlans(r.data.plans || []);
      setPaymentMode(r.data.purchase_enabled ? r.data.payment_mode : "disabled");
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!wallet) fetchWallet();
    if (!me) fetchMe();
  }, [wallet, fetchWallet, me, fetchMe]);

  // 初次拉到 me 時自動填入 email 作為預設
  useEffect(() => {
    if (!me) return;
    setBuyer((prev) => ({
      ...prev,
      buyer_email: prev.buyer_email || me.email || "",
    }));
  }, [me]);

  useEffect(() => {
    if (searchParams.get("payment_return") !== "1") return undefined;
    const orderId = Number(searchParams.get("order_id"));
    setSearchParams({}, { replace: true });
    if (!Number.isInteger(orderId) || orderId < 1) {
      setErrors({ detail: "付款返回資訊不完整，請到訂單紀錄確認狀態。" });
      return undefined;
    }
    let cancelled = false;
    Promise.all([api.get("/billing/orders/"), fetchWallet()])
      .then(([ordersResponse]) => {
        if (cancelled) return;
        const order = (ordersResponse.data.orders || []).find((item) => item.id === orderId);
        if (order?.status === "paid") {
          setCompletedOrder(order);
        } else {
          setErrors({ detail: "付款結果尚未完成同步，請稍後重新整理訂單頁。" });
        }
      })
      .catch(() => {
        if (!cancelled) setErrors({ detail: "無法讀取付款結果，請稍後再試。" });
      });
    return () => {
      cancelled = true;
    };
  }, [fetchWallet, searchParams, setSearchParams]);

  // 從 /purchase 跳來時帶 ?plan=advanced：plans 載完後自動選好並進 step 2
  useEffect(() => {
    if (!enabled || selectedPlan || plans.length === 0) return;
    const target = searchParams.get("plan");
    if (!target) return;
    const match = plans.find((p) => p.code === target);
    if (match) {
      setSelectedPlan(match);
      setStep(2);
      // 清掉 URL 上的 plan，避免使用者後續回到 step 1 再選又被自動覆蓋
      setSearchParams({}, { replace: true });
    }
  }, [enabled, plans, searchParams, selectedPlan, setSearchParams]);

  function pickPlan(plan) {
    if (!enabled) return;
    setSelectedPlan(plan);
    setStep(2);
    setErrors({});
  }

  function goToConfirm() {
    const errs = validateBuyer(buyer, { live });
    setErrors(errs);
    if (Object.keys(errs).length === 0) {
      setStep(3);
    }
  }

  async function submitOrder() {
    setSubmitting(true);
    setErrors({});
    try {
      const response = await api.post("/billing/purchase/", {
        plan_code: selectedPlan.code,
        ...buyerPayload(buyer),
      });
      submitEcpayForm(response.data.payment);
    } catch (err) {
      const data = err?.response?.data || {};
      const flat = {};
      for (const [k, v] of Object.entries(data)) {
        flat[k] = Array.isArray(v) ? v[0] : String(v);
      }
      setErrors(flat);
      if (data.buyer_name || data.buyer_email || data.company_name || data.tax_id || data.agree_terms) {
        setStep(2);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function startNewPurchase() {
    setSelectedPlan(null);
    setStep(1);
    setCompletedOrder(null);
    setErrors({});
    setBuyer((b) => ({ ...b, agree_terms: false }));
  }

  if (completedOrder) {
    return (
      <section className="panel space-y-4">
        <div className="wizard-success">
          <div className="wizard-success-emoji" aria-hidden="true">🎉</div>
          <h2 className="wizard-success-title">訂購完成</h2>
          <p className="wizard-success-sub">已成功購買 {completedOrder.plan_name}</p>
          <dl className="wizard-success-dl">
            <dt>訂單編號</dt><dd>#{completedOrder.id}</dd>
            <dt>方案</dt><dd>{completedOrder.plan_name}</dd>
            <dt>{live ? "付款金額" : "測試金額"}</dt><dd>NT$ {completedOrder.price_ntd.toLocaleString()}</dd>
            <dt>入帳點數</dt><dd>+{completedOrder.coin_amount.toLocaleString()} coin</dd>
            <dt>當前餘額</dt><dd className="hl-balance">{wallet?.balance?.toLocaleString()} coin</dd>
            <dt>憑證偏好</dt><dd>{completedOrder.invoice_type_label}{completedOrder.invoice_type === "company" ? `（${completedOrder.company_name} / ${completedOrder.tax_id}）` : ""}</dd>
            {completedOrder.invoice_type === "personal" && completedOrder.carrier_type !== "cloud" && (
              <>
                <dt>載具</dt>
                <dd>{completedOrder.carrier_type_label}：{completedOrder.carrier_id}</dd>
              </>
            )}
            <dt>收據寄送</dt><dd>{completedOrder.buyer_email}</dd>
          </dl>
          <div className="wizard-success-actions">
            <button className="primary-button" type="button" onClick={startNewPurchase}>
              再買一次
            </button>
            <button className="secondary-button" type="button" onClick={() => navigate("/scans")}>
              開始掃描
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="billing-page">
    <SubscriptionPanel purchasePlans={plans} />
    <section className="panel billing-checkout">
      <header className="billing-checkout-header">
        <div className="billing-checkout-heading">
          <p className="billing-checkout-eyebrow">ARGUS ONE-TIME CHECKOUT</p>
          <h2 className="billing-checkout-title">單次購買點數</h2>
          <p className="billing-checkout-subtitle">
            單次加值、立即入點；掃描按維度計費（每頁每維度 {wallet?.coin_per_category ?? 2} coin），依序完成方案、資料與訂單確認。
          </p>
        </div>
        <div className="billing-wallet-summary" aria-label={`目前餘額 ${wallet?.balance?.toLocaleString() ?? "載入中"} coin`}>
          <span>目前可用</span>
          <strong>{wallet?.balance?.toLocaleString() ?? "—"}</strong>
          <span>coin</span>
        </div>
      </header>

      {live ? (
        <div className="billing-environment-notice tone-live" role="status">
          <span className="billing-environment-chip">ECPAY</span>
          <span>
            <strong>綠界安全付款</strong>・信用卡付款由綠界科技處理，Argus 不會取得卡號；付款驗證成功後立即入點，電子發票寄至通知信箱。
          </span>
        </div>
      ) : paymentMode === "ecpay_test" ? (
        <div className="billing-environment-notice tone-test" role="status">
          <span className="billing-environment-chip">STAGE</span>
          <span>
            <strong>安全測試模式</strong>・不會實際扣款，也不開立正式電子發票；付款回呼驗證成功後才會入點。
          </span>
        </div>
      ) : (
        <div className="billing-environment-notice tone-paused" role="status">
          <span className="billing-environment-chip">PAUSED</span>
          <span><strong>購點服務暫停</strong>・目前不接受訂單，也不會直接入點。</span>
        </div>
      )}

      <WizardStepper current={step} />

      {step === 1 && (
        <div className="billing-plan-grid billing-step-content">
          {plans.map((plan) => {
            const isRecommended = plan.code === "advanced";
            return (
              <div
                key={plan.code}
                className={`billing-plan-card ${isRecommended ? "is-recommended" : ""}`}
              >
                {plan.badge && <span className="billing-plan-badge">{plan.badge}</span>}
                {isRecommended && <span className="billing-plan-recommend">★ 推薦</span>}
                <h3 className="billing-plan-name">{plan.name}</h3>
                <p className="billing-plan-coin">
                  {plan.coin_amount.toLocaleString()} <span>coin</span>
                </p>
                <p className="billing-plan-price">NT$ {plan.price_ntd.toLocaleString()}</p>
                <p className="billing-plan-rate">{plan.coin_per_ntd?.toFixed(2)} coin / NT$</p>
                {plan.description && <p className="billing-plan-desc">{plan.description}</p>}
                <button
                  className="billing-plan-button"
                  type="button"
                  onClick={() => pickPlan(plan)}
                  disabled={!enabled}
                >
                  {enabled ? "選擇此方案 →" : "目前未開放"}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {step === 2 && selectedPlan && (
        <form
          className="wizard-checkout-grid"
          onSubmit={(event) => {
            event.preventDefault();
            goToConfirm();
          }}
          noValidate
        >
          <div className="wizard-form-panel">
            <div className="wizard-form-intro">
              <p className="wizard-form-kicker">購買資料</p>
              <h3>填寫聯絡與憑證偏好</h3>
              <p>所有必填欄位皆以「必填」標示；送出前還會有一次訂單確認。</p>
            </div>

            <BuyerInvoiceFields buyer={buyer} setBuyer={setBuyer} errors={errors} live={live} />

            <div className={`wizard-acknowledgement ${errors.agree_terms ? "is-error" : ""}`}>
              <label className="wizard-checkbox">
                <input
                  type="checkbox"
                  checked={buyer.agree_terms}
                  aria-invalid={Boolean(errors.agree_terms)}
                  aria-describedby={errors.agree_terms ? "agree_terms_error" : undefined}
                  onChange={(e) => setBuyer({ ...buyer, agree_terms: e.target.checked })}
                />
                {live ? (
                  <span>
                    <strong>我確認資料正確，並同意<a href="/terms" target="_blank" rel="noreferrer">服務條款</a></strong>
                    <small>將以信用卡實際付款；點數在綠界付款通知驗證成功後入帳。</small>
                  </span>
                ) : (
                  <span>
                    <strong>我確認資料正確並了解測試流程</strong>
                    <small>不會實際扣款、不開立正式電子發票；點數只在付款回呼驗證成功後入帳。</small>
                  </span>
                )}
              </label>
              {errors.agree_terms && <p id="agree_terms_error" className="wizard-field-error" role="alert">{errors.agree_terms}</p>}
            </div>

            <div className="wizard-nav">
              <button className="secondary-button" type="button" onClick={() => setStep(1)}>
                ← 返回選擇方案
              </button>
              <button className="primary-button" type="submit">
                檢查並確認訂單 →
              </button>
            </div>
          </div>

          <aside className="wizard-order-summary" aria-label="訂單摘要">
            <div className="wizard-order-summary-head">
              <span>訂單摘要</span>
              <span className="wizard-order-stage">{live ? "ECPAY" : "STAGE"}</span>
            </div>
            <div className="wizard-order-plan">
              <span>{selectedPlan.name}</span>
              <strong>{selectedPlan.coin_amount.toLocaleString()} <small>coin</small></strong>
            </div>
            <dl className="wizard-order-details">
              <div><dt>方案價格</dt><dd>NT$ {selectedPlan.price_ntd.toLocaleString()}</dd></div>
              <div><dt>目前餘額</dt><dd>{wallet?.balance?.toLocaleString() ?? "—"} coin</dd></div>
              <div><dt>{live ? "入帳後" : "測試入帳後"}</dt><dd>{typeof wallet?.balance === "number" ? (wallet.balance + selectedPlan.coin_amount).toLocaleString() : "—"} coin</dd></div>
            </dl>
            <div className="wizard-order-total">
              <span>{live ? "應付金額" : "測試金額"}</span>
              <strong>NT$ {selectedPlan.price_ntd.toLocaleString()}</strong>
            </div>
            <ul className="wizard-order-assurances">
              <li>{live ? "信用卡由綠界科技處理，Argus 不經手卡號" : "不會產生真實扣款"}</li>
              <li>簽章、訂單與金額驗證後才入點</li>
              <li>{live ? "付款結果與電子發票寄至通知信箱" : "付款結果與收據寄至通知信箱"}</li>
            </ul>
          </aside>
        </form>
      )}

      {step === 3 && selectedPlan && (
        <div className="wizard-confirm billing-step-content">
          <h3 className="wizard-confirm-title">請確認以下訂單資訊</h3>

          <div className="wizard-confirm-card">
            <h4>方案</h4>
            <div className="wizard-confirm-plan">
              <div>
                <div className="wizard-confirm-plan-name">{selectedPlan.name}</div>
                <div className="wizard-confirm-plan-coin">{selectedPlan.coin_amount.toLocaleString()} coin</div>
              </div>
              <div className="wizard-confirm-plan-price">NT$ {selectedPlan.price_ntd.toLocaleString()}</div>
            </div>
          </div>

          <div className="wizard-confirm-card">
            <h4>購買資料</h4>
            <dl className="wizard-confirm-dl">
              <dt>姓名</dt><dd>{buyer.buyer_name}</dd>
              <dt>通知信箱</dt><dd>{buyer.buyer_email}</dd>
              <dt>憑證偏好</dt>
              <dd>
                {buyer.invoice_type === "company"
                  ? `公司購買（${buyer.company_name} / 統編 ${buyer.tax_id}）`
                  : "個人購買"}
              </dd>
              {buyer.invoice_type === "personal" && (
                <>
                  <dt>載具</dt>
                  <dd>
                    {buyer.carrier_type === "cloud" && "不使用載具（收據寄至通知信箱）"}
                    {buyer.carrier_type === "mobile_barcode" && `手機條碼 ${buyer.carrier_id}`}
                    {buyer.carrier_type === "citizen_digital" && `自然人憑證 ${buyer.carrier_id}`}
                  </dd>
                </>
              )}
            </dl>
          </div>

          <div className="wizard-confirm-total">
            <span>{live ? "應付金額" : "測試金額"}</span>
            <span className="wizard-confirm-total-value">NT$ {selectedPlan.price_ntd.toLocaleString()}</span>
          </div>
          {(() => {
            // 以最便宜方案（sort_order 最小）的單位單價為基準，算「比 N 次最便宜方案省多少」
            const baseline = [...plans].sort((a, b) => a.price_ntd - b.price_ntd)[0];
            if (!baseline || baseline.code === selectedPlan.code) return null;
            const baselineRate = baseline.coin_amount / baseline.price_ntd;
            const fairPrice = Math.round(selectedPlan.coin_amount / baselineRate);
            const saved = fairPrice - selectedPlan.price_ntd;
            if (saved <= 0) return null;
            const pct = Math.round((saved / fairPrice) * 100);
            return (
              <p className="wizard-confirm-saved">
                相比同等 coin 數量買{baseline.name}，這個方案省下 NT$ {saved.toLocaleString()}（約 {pct}%）。
              </p>
            );
          })()}

          {Object.keys(errors).length > 0 && (
            <div className="billing-feedback tone-bad">
              {Object.values(errors).join("、")}
            </div>
          )}

          <div className="wizard-nav">
            <button className="secondary-button" type="button" onClick={() => setStep(2)} disabled={submitting}>
              ← 修改資料
            </button>
            <button className="primary-button" type="button" onClick={submitOrder} disabled={submitting}>
              {live
                ? (submitting ? "前往綠界付款…" : "前往綠界付款")
                : (submitting ? "前往綠界 Stage…" : "前往綠界 Stage")}
            </button>
          </div>
        </div>
      )}

    </section>
    <CoinHistory transactions={wallet?.recent_transactions} />
    </div>
  );
}

export { BillingPage };
