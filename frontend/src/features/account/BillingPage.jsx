// 購點頁：依使用者要求恢復為 462848b（Night Watch 改版前）的版本。
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { useArgusStore } from "../../store";
import { SubscriptionPanel } from "./SubscriptionPanel";

// ============================================================
// Billing 頁（4 個方案 + 綠界測試環境）
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

function submitEcpayTestForm(payment) {
  if (
    payment?.action !== "https://payment-stage.ecpay.com.tw/Cashier/AioCheckOut/V5" ||
    !payment?.fields
  ) {
    throw new Error("綠界測試付款設定不正確。");
  }
  const form = document.createElement("form");
  form.method = "POST";
  form.action = payment.action;
  for (const [name, value] of Object.entries(payment.fields)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = String(value);
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
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

  const [buyer, setBuyer] = useState({
    buyer_name: "",
    buyer_email: "",
    invoice_type: "personal",
    company_name: "",
    tax_id: "",
    carrier_type: "cloud",
    carrier_id: "",
    agree_terms: false,
  });

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
    if (paymentMode !== "ecpay_test" || selectedPlan || plans.length === 0) return;
    const target = searchParams.get("plan");
    if (!target) return;
    const match = plans.find((p) => p.code === target);
    if (match) {
      setSelectedPlan(match);
      setStep(2);
      // 清掉 URL 上的 plan，避免使用者後續回到 step 1 再選又被自動覆蓋
      setSearchParams({}, { replace: true });
    }
  }, [paymentMode, plans, searchParams, selectedPlan, setSearchParams]);

  function pickPlan(plan) {
    if (paymentMode !== "ecpay_test") return;
    setSelectedPlan(plan);
    setStep(2);
    setErrors({});
  }

  function validateStep2() {
    const errs = {};
    if (!buyer.buyer_name.trim()) errs.buyer_name = "請填寫姓名";
    if (!buyer.buyer_email.trim()) errs.buyer_email = "請填寫 email";
    else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(buyer.buyer_email)) {
      errs.buyer_email = "email 格式不正確";
    }
    if (buyer.invoice_type === "company") {
      if (!buyer.company_name.trim()) errs.company_name = "公司購買須填寫公司抬頭";
      if (!/^\d{8}$/.test(buyer.tax_id)) errs.tax_id = "統一編號需為 8 碼數字";
    } else {
      // 個人發票：驗證載具
      if (buyer.carrier_type === "mobile_barcode") {
        if (!/^\/[0-9A-Z+\-.]{7}$/.test(buyer.carrier_id.trim().toUpperCase())) {
          errs.carrier_id = "手機條碼格式錯誤（首碼 / + 7 碼英數，例 /AB12CDE）";
        }
      } else if (buyer.carrier_type === "citizen_digital") {
        if (!/^[A-Z]{2}\d{14}$/.test(buyer.carrier_id.trim().toUpperCase())) {
          errs.carrier_id = "自然人憑證格式錯誤（2 碼英文 + 14 碼數字）";
        }
      }
    }
    if (!buyer.agree_terms) errs.agree_terms = "請確認測試購買說明";
    return errs;
  }

  function goToConfirm() {
    const errs = validateStep2();
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
        buyer_name: buyer.buyer_name.trim(),
        buyer_email: buyer.buyer_email.trim(),
        invoice_type: buyer.invoice_type,
        company_name: buyer.invoice_type === "company" ? buyer.company_name.trim() : "",
        tax_id: buyer.invoice_type === "company" ? buyer.tax_id.trim() : "",
        carrier_type:
          buyer.invoice_type === "company" ? "cloud" : buyer.carrier_type,
        carrier_id:
          buyer.invoice_type === "company" ? "" :
          (buyer.carrier_type === "cloud" ? "" : buyer.carrier_id.trim().toUpperCase()),
        agree_terms: buyer.agree_terms,
      });
      submitEcpayTestForm(response.data.payment);
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
            <dt>測試金額</dt><dd>NT$ {completedOrder.price_ntd.toLocaleString()}</dd>
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

      {paymentMode === "ecpay_test" ? (
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
                  disabled={paymentMode !== "ecpay_test"}
                >
                  {paymentMode === "ecpay_test" ? "選擇此方案 →" : "目前未開放"}
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

            <fieldset className="billing-form-section">
              <legend className="billing-form-legend">
                <span className="billing-form-index">1</span>
                <span>聯絡資料</span>
              </legend>
              <p className="billing-form-description">用於辨識訂單並寄送測試購買收據。</p>
              <div className="billing-field-grid">
                <div className="wizard-field">
                  <label htmlFor="buyer_name">姓名 <span>必填</span></label>
                  <input
                    id="buyer_name"
                    className={`input ${errors.buyer_name ? "is-error" : ""}`}
                    autoComplete="name"
                    placeholder="例如：王小明"
                    value={buyer.buyer_name}
                    aria-invalid={Boolean(errors.buyer_name)}
                    aria-describedby={errors.buyer_name ? "buyer_name_error" : undefined}
                    onChange={(e) => setBuyer({ ...buyer, buyer_name: e.target.value })}
                  />
                  {errors.buyer_name && <p id="buyer_name_error" className="wizard-field-error" role="alert">{errors.buyer_name}</p>}
                </div>

                <div className="wizard-field">
                  <label htmlFor="buyer_email">收據通知信箱 <span>必填</span></label>
                  <input
                    id="buyer_email"
                    className={`input ${errors.buyer_email ? "is-error" : ""}`}
                    type="email"
                    autoComplete="email"
                    inputMode="email"
                    placeholder="you@example.com"
                    value={buyer.buyer_email}
                    aria-invalid={Boolean(errors.buyer_email)}
                    aria-describedby={errors.buyer_email ? "buyer_email_error" : "buyer_email_hint"}
                    onChange={(e) => setBuyer({ ...buyer, buyer_email: e.target.value })}
                  />
                  <p id="buyer_email_hint" className="wizard-field-hint">付款結果與測試收據會寄到這個信箱。</p>
                  {errors.buyer_email && <p id="buyer_email_error" className="wizard-field-error" role="alert">{errors.buyer_email}</p>}
                </div>
              </div>
            </fieldset>

            <fieldset className="billing-form-section">
              <legend className="billing-form-legend">
                <span className="billing-form-index">2</span>
                <span>收據與發票偏好</span>
              </legend>
              <p className="billing-form-description">
                此欄位只記錄測試訂單偏好；Stage 環境不會開立正式電子發票。
              </p>

              <div className="billing-choice-grid" role="group" aria-label="購買身分">
                <label className="billing-choice-card">
                  <input
                    type="radio"
                    name="invoice_type"
                    checked={buyer.invoice_type === "personal"}
                    onChange={() => setBuyer({ ...buyer, invoice_type: "personal", carrier_type: "cloud", carrier_id: "" })}
                  />
                  <span className="billing-choice-copy">
                    <strong>個人購買</strong>
                    <small>可選擇是否記錄載具</small>
                  </span>
                </label>
                <label className="billing-choice-card">
                  <input
                    type="radio"
                    name="invoice_type"
                    checked={buyer.invoice_type === "company"}
                    onChange={() => setBuyer({ ...buyer, invoice_type: "company", carrier_type: "cloud", carrier_id: "" })}
                  />
                  <span className="billing-choice-copy">
                    <strong>公司購買</strong>
                    <small>需填寫公司抬頭與統編</small>
                  </span>
                </label>
              </div>

              {buyer.invoice_type === "personal" && (
                <div className="billing-form-subsection" role="group" aria-labelledby="carrier_preference_label">
                  <div className="billing-subsection-heading" id="carrier_preference_label">載具偏好</div>
                  <div className="billing-carrier-grid">
                    <label className="billing-choice-card is-compact">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "cloud"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "cloud", carrier_id: "" })}
                      />
                      <span className="billing-choice-copy">
                        <strong>不使用載具</strong>
                        <small>收據寄送至通知信箱</small>
                      </span>
                    </label>
                    <label className="billing-choice-card is-compact">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "mobile_barcode"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "mobile_barcode", carrier_id: "" })}
                      />
                      <span className="billing-choice-copy">
                        <strong>手機條碼</strong>
                        <small>／開頭加 7 碼英數</small>
                      </span>
                    </label>
                    <label className="billing-choice-card is-compact">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "citizen_digital"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "citizen_digital", carrier_id: "" })}
                      />
                      <span className="billing-choice-copy">
                        <strong>自然人憑證</strong>
                        <small>2 碼英文加 14 碼數字</small>
                      </span>
                    </label>
                  </div>
                  {buyer.carrier_type !== "cloud" && (
                    <div className="wizard-field billing-conditional-field">
                      <label htmlFor="carrier_id">
                        {buyer.carrier_type === "mobile_barcode" ? "手機條碼" : "自然人憑證條碼"} <span>必填</span>
                      </label>
                      <input
                        id="carrier_id"
                        className={`input ${errors.carrier_id ? "is-error" : ""}`}
                        type="text"
                        autoCapitalize="characters"
                        spellCheck={false}
                        placeholder={buyer.carrier_type === "mobile_barcode" ? "/AB12CDE" : "AB12345678901234"}
                        value={buyer.carrier_id}
                        aria-invalid={Boolean(errors.carrier_id)}
                        aria-describedby={errors.carrier_id ? "carrier_id_error" : undefined}
                        onChange={(e) => setBuyer({ ...buyer, carrier_id: e.target.value.toUpperCase() })}
                      />
                      {errors.carrier_id && <p id="carrier_id_error" className="wizard-field-error" role="alert">{errors.carrier_id}</p>}
                    </div>
                  )}
                </div>
              )}

              {buyer.invoice_type === "company" && (
                <div className="billing-form-subsection billing-company-section">
                  <div className="billing-field-grid">
                    <div className="wizard-field">
                      <label htmlFor="company_name">公司抬頭 <span>必填</span></label>
                      <input
                        id="company_name"
                        className={`input ${errors.company_name ? "is-error" : ""}`}
                        type="text"
                        autoComplete="organization"
                        placeholder="例如：Argus 科技股份有限公司"
                        value={buyer.company_name || ""}
                        aria-invalid={Boolean(errors.company_name)}
                        aria-describedby={errors.company_name ? "company_name_error" : undefined}
                        onChange={(e) => setBuyer({ ...buyer, company_name: e.target.value })}
                      />
                      {errors.company_name && <p id="company_name_error" className="wizard-field-error" role="alert">{errors.company_name}</p>}
                    </div>
                    <div className="wizard-field">
                      <label htmlFor="tax_id">統一編號 <span>必填・8 碼</span></label>
                      <input
                        id="tax_id"
                        className={`input ${errors.tax_id ? "is-error" : ""}`}
                        type="text"
                        inputMode="numeric"
                        autoComplete="off"
                        placeholder="12345678"
                        value={buyer.tax_id || ""}
                        aria-invalid={Boolean(errors.tax_id)}
                        aria-describedby={errors.tax_id ? "tax_id_error" : undefined}
                        onChange={(e) => setBuyer({ ...buyer, tax_id: e.target.value.replace(/\D/g, "") })}
                        maxLength={8}
                      />
                      {errors.tax_id && <p id="tax_id_error" className="wizard-field-error" role="alert">{errors.tax_id}</p>}
                    </div>
                  </div>
                </div>
              )}
            </fieldset>

            <div className={`wizard-acknowledgement ${errors.agree_terms ? "is-error" : ""}`}>
              <label className="wizard-checkbox">
                <input
                  type="checkbox"
                  checked={buyer.agree_terms}
                  aria-invalid={Boolean(errors.agree_terms)}
                  aria-describedby={errors.agree_terms ? "agree_terms_error" : undefined}
                  onChange={(e) => setBuyer({ ...buyer, agree_terms: e.target.checked })}
                />
                <span>
                  <strong>我確認資料正確並了解測試流程</strong>
                  <small>不會實際扣款、不開立正式電子發票；點數只在付款回呼驗證成功後入帳。</small>
                </span>
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
              <span className="wizard-order-stage">STAGE</span>
            </div>
            <div className="wizard-order-plan">
              <span>{selectedPlan.name}</span>
              <strong>{selectedPlan.coin_amount.toLocaleString()} <small>coin</small></strong>
            </div>
            <dl className="wizard-order-details">
              <div><dt>方案價格</dt><dd>NT$ {selectedPlan.price_ntd.toLocaleString()}</dd></div>
              <div><dt>目前餘額</dt><dd>{wallet?.balance?.toLocaleString() ?? "—"} coin</dd></div>
              <div><dt>測試入帳後</dt><dd>{typeof wallet?.balance === "number" ? (wallet.balance + selectedPlan.coin_amount).toLocaleString() : "—"} coin</dd></div>
            </dl>
            <div className="wizard-order-total">
              <span>測試金額</span>
              <strong>NT$ {selectedPlan.price_ntd.toLocaleString()}</strong>
            </div>
            <ul className="wizard-order-assurances">
              <li>不會產生真實扣款</li>
              <li>簽章、訂單與金額驗證後才入點</li>
              <li>付款結果與收據寄至通知信箱</li>
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
            <span>測試金額</span>
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
              {submitting ? "前往綠界 Stage…" : "前往綠界 Stage"}
            </button>
          </div>
        </div>
      )}

    </section>
    </div>
  );
}

export { BillingPage };
