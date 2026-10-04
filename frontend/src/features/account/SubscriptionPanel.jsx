// 月訂閱區塊：依使用者要求恢復為 462848b（Night Watch 改版前）的版本。
// 2026-10-04 起為綠界信用卡定期定額：填買受人／發票資料 → 綠界綁卡並付首期 → 每月自動扣款。
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  cancelSubscription,
  fetchMySubscription,
  fetchSubscriptionPlans,
  subscribePlan,
} from "../../api";
import {
  BuyerInvoiceFields,
  EMPTY_BUYER,
  buyerPayload,
  submitEcpayForm,
  validateBuyer,
} from "../../components/billing/BuyerInvoiceFields";
import { useArgusStore } from "../../store";
import { apiErrorMessage, useConfirmDialogs } from "../../shared/AppShared.jsx";

// 訂閱狀態 → 賣點語氣（active=綠、cancelled=amber、expired=灰）
const SUB_STATUS_TONE = {
  active: "good",
  cancelled: "warn",
  expired: "neutral",
};

function formatChineseDate(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString("zh-Hant", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  });
}

function SubscriptionPanel({ purchasePlans }) {
  // subState：undefined=載入中、null=無訂閱、物件=目前訂閱
  const [subPlans, setSubPlans] = useState([]);
  const [subscribeEnabled, setSubscribeEnabled] = useState(false);
  const [paymentMode, setPaymentMode] = useState("disabled");
  const [checkoutPlan, setCheckoutPlan] = useState(null);
  const [buyer, setBuyer] = useState(EMPTY_BUYER);
  const [errors, setErrors] = useState({});
  const me = useArgusStore((s) => s.me);
  const [searchParams, setSearchParams] = useSearchParams();
  const live = paymentMode === "ecpay";
  const [subState, setSubState] = useState(undefined);
  const [subLoaded, setSubLoaded] = useState(false);
  const [subError, setSubError] = useState("");
  const [subBusy, setSubBusy] = useState(false);
  const [subFeedback, setSubFeedback] = useState(null);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);
  const { confirmDialog, dialogHost } = useConfirmDialogs();

  useEffect(() => {
    let cancelled = false;
    fetchSubscriptionPlans()
      .then((data) => {
        if (cancelled) return;
        setSubPlans(data.plans || []);
        setSubscribeEnabled(Boolean(data.subscribe_enabled));
        setPaymentMode(data.subscribe_enabled ? data.payment_mode : "disabled");
      })
      .catch(() => {
        if (!cancelled) setSubError("無法載入訂閱方案。");
      });
    fetchMySubscription()
      .then((data) => {
        if (cancelled) return;
        setSubState(data.subscription || null);
        setSubLoaded(true);
      })
      .catch(() => {
        if (!cancelled) {
          setSubError("無法載入訂閱狀態。");
          setSubLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 單次購點的最佳換算率（coin / NT$），作為訂閱方案的比較基準
  const bestPurchaseRate = purchasePlans.length
    ? Math.max(...purchasePlans.map((p) => p.coin_per_ntd || 0))
    : null;

  const subscribedPlan = subState
    ? subPlans.find((p) => p.code === subState.plan_code)
    : null;
  const isActive = subState?.status === "active";
  // 無訂閱、或已取消／到期（可重新訂閱）時顯示方案卡片
  const showPlanGrid = subLoaded && (!subState || !isActive);

  useEffect(() => {
    if (!me?.email) return;
    setBuyer((prev) => ({ ...prev, buyer_email: prev.buyer_email || me.email }));
  }, [me]);

  // 從綠界付款頁回來（?subscription_return=1）：開通靠綠界的伺服器通知，可能晚幾秒，輪詢幾次
  useEffect(() => {
    if (searchParams.get("subscription_return") !== "1") return undefined;
    setSearchParams({}, { replace: true });
    setSubFeedback({ tone: "good", text: "付款處理中，完成後會自動開通訂閱…" });
    let cancelled = false;
    let tries = 0;
    async function poll() {
      tries += 1;
      try {
        const data = await fetchMySubscription();
        if (cancelled) return;
        if (data.subscription?.status === "active" && data.subscription?.auto_renew) {
          setSubState(data.subscription);
          setSubFeedback({ tone: "good", text: `已開通「${data.subscription.plan_name}」，首月點數已入帳。` });
          fetchWallet();
          return;
        }
      } catch {
        // 下一輪再試
      }
      if (tries < 6) {
        setTimeout(poll, 2000);
      } else if (!cancelled) {
        setSubFeedback({ tone: "bad", text: "尚未收到付款成功通知；若已完成付款，請稍後重新整理此頁。" });
      }
    }
    poll();
    return () => {
      cancelled = true;
    };
  }, [fetchWallet, searchParams, setSearchParams]);

  function startCheckout(plan) {
    setCheckoutPlan(plan);
    setErrors({});
    setSubFeedback(null);
  }

  async function handleSubscribe(event) {
    event.preventDefault();
    const errs = validateBuyer(buyer, { live });
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    setSubBusy(true);
    setSubFeedback(null);
    try {
      const data = await subscribePlan(checkoutPlan.code, buyerPayload(buyer));
      submitEcpayForm(data.payment);
    } catch (err) {
      const data = err?.response?.data || {};
      const flat = {};
      for (const [key, value] of Object.entries(data)) {
        if (key !== "detail") flat[key] = Array.isArray(value) ? value[0] : String(value);
      }
      setErrors(flat);
      // 503（付費關閉）、409（已有自動扣款）等後端 detail 以繁中文案顯示
      setSubFeedback({ tone: "bad", text: apiErrorMessage(err, "訂閱失敗，請稍後再試。") });
      setSubBusy(false);
    }
  }

  async function handleCancel() {
    const ok = await confirmDialog(
      subState?.auto_renew
        ? "確定要取消訂閱嗎？綠界會停止之後的每月扣款；當期已付款權益保留到期滿為止。"
        : "確定要取消訂閱嗎？當期已付款權益會保留到期滿為止，之後不再每月發點。",
      { danger: true },
    );
    if (!ok) return;
    setSubBusy(true);
    setSubFeedback(null);
    try {
      const data = await cancelSubscription();
      setSubState(data.subscription);
      setSubFeedback({ tone: "good", text: "已取消訂閱；本期權益仍保留到期滿。" });
      // 取消前 lazy 結算可能補發點數，重抓餘額保持一致
      fetchWallet();
    } catch (err) {
      setSubFeedback({
        tone: "bad",
        text: apiErrorMessage(err, "取消訂閱失敗，請稍後再試。"),
      });
    } finally {
      setSubBusy(false);
    }
  }

  return (
    <section className="panel billing-checkout billing-sub" aria-label="月訂閱方案">
      <header className="billing-checkout-header">
        <div className="billing-checkout-heading">
          <p className="billing-checkout-eyebrow">ARGUS MONTHLY SUBSCRIPTION</p>
          <h2 className="billing-checkout-title">月訂閱方案</h2>
          <p className="billing-checkout-subtitle">
            信用卡每月自動扣款、每月發放點數，換算單點成本更低；隨時可取消，當期權益保留到期滿。適合持續巡檢的網站。
          </p>
        </div>
        <div className="billing-wallet-summary" aria-label="目前訂閱狀態">
          <span>目前方案</span>
          <strong>{subState ? subState.plan_name : "—"}</strong>
          <span>{subState ? subState.status_label : "尚未訂閱"}</span>
        </div>
      </header>

      {live ? (
        <div className="billing-environment-notice tone-live" role="status">
          <span className="billing-environment-chip">ECPAY</span>
          <span>
            <strong>綠界信用卡定期定額</strong>・首期立即扣款並發點，之後每月同一天自動扣款；取消後停止扣款。電子發票每期寄至通知信箱。
          </span>
        </div>
      ) : subscribeEnabled ? (
        <div className="billing-environment-notice tone-test" role="status">
          <span className="billing-environment-chip">STAGE</span>
          <span>
            <strong>綠界測試環境</strong>・使用測試信用卡走完整定期定額流程，不會實際扣款。
          </span>
        </div>
      ) : (
        <div className="billing-environment-notice tone-paused" role="status">
          <span className="billing-environment-chip">PAUSED</span>
          <span><strong>訂閱服務暫停</strong>・目前不受理訂閱，也不會直接入點。</span>
        </div>
      )}

      <div className="billing-step-content billing-sub-body">
        {subFeedback && (
          <div
            className={`billing-feedback ${subFeedback.tone === "good" ? "tone-good" : "tone-bad"}`}
            role="status"
          >
            {subFeedback.text}
          </div>
        )}
        {subError && <div className="billing-feedback tone-bad" role="alert">{subError}</div>}
        {!subLoaded && <p className="hint-text">載入訂閱資訊中...</p>}

        {subState && (
          <div className="billing-sub-status">
            <div className="billing-sub-status-head">
              <h3 className="billing-sub-status-name">{subState.plan_name}</h3>
              <span
                className={`billing-sub-status-badge tone-${SUB_STATUS_TONE[subState.status] || "neutral"}`}
              >
                {subState.status_label}
              </span>
            </div>
            <dl className="billing-sub-dl">
              <div>
                <dt>每月贈點</dt>
                <dd>{subscribedPlan ? `${subscribedPlan.monthly_coins.toLocaleString()} coin` : "—"}</dd>
              </div>
              <div>
                <dt>月費</dt>
                <dd>{subscribedPlan ? `NT$ ${subscribedPlan.monthly_price_ntd.toLocaleString()}` : "—"}</dd>
              </div>
              <div>
                <dt>每月自動扣款</dt>
                <dd>{subState.auto_renew ? "是（綠界信用卡）" : "否"}</dd>
              </div>
              <div>
                <dt>{isActive ? "下次贈點日" : "權益到期日"}</dt>
                <dd>{formatChineseDate(subState.current_period_end)}</dd>
              </div>
              <div>
                <dt>開始日</dt>
                <dd>{formatChineseDate(subState.started_at)}</dd>
              </div>
              {subState.cancelled_at && (
                <div>
                  <dt>取消時間</dt>
                  <dd>{formatChineseDate(subState.cancelled_at)}</dd>
                </div>
              )}
            </dl>
            <div className="billing-sub-actions">
              {isActive ? (
                <button
                  className="billing-sub-cancel-btn"
                  type="button"
                  onClick={handleCancel}
                  disabled={subBusy}
                >
                  {subBusy ? "處理中…" : "取消訂閱"}
                </button>
              ) : (
                <p className="billing-sub-renew-hint">
                  本期到期後不再續訂；可從下方方案重新訂閱延續權益。
                </p>
              )}
            </div>
          </div>
        )}

        {showPlanGrid && subPlans.length > 0 && (
          <div className="billing-sub-grid">
            {subPlans.map((plan) => {
              const isRecommended = plan.code === "sub-pro";
              const rate = plan.monthly_price_ntd > 0
                ? plan.monthly_coins / plan.monthly_price_ntd
                : 0;
              const vsPurchase = bestPurchaseRate && rate > bestPurchaseRate
                ? Math.round(((rate - bestPurchaseRate) / bestPurchaseRate) * 100)
                : null;
              return (
                <div
                  key={plan.code}
                  className={`billing-plan-card ${isRecommended ? "is-recommended" : ""}`}
                >
                  {plan.badge && <span className="billing-plan-badge">{plan.badge}</span>}
                  {isRecommended && <span className="billing-plan-recommend">★ 推薦</span>}
                  <h3 className="billing-plan-name">{plan.name}</h3>
                  <p className="billing-plan-coin">
                    {plan.monthly_coins.toLocaleString()} <span>coin / 月</span>
                  </p>
                  <p className="billing-plan-price">NT$ {plan.monthly_price_ntd.toLocaleString()} / 月</p>
                  <p className="billing-plan-rate">
                    {rate.toFixed(2)} coin / NT$
                    {vsPurchase ? ` · 比單次購點最划算方案再多 ${vsPurchase}% 點` : ""}
                  </p>
                  {plan.features?.length > 0 && (
                    <ul className="billing-plan-features">
                      {plan.features.map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                  )}
                  <button
                    className="billing-plan-button"
                    type="button"
                    onClick={() => startCheckout(plan)}
                    disabled={!subscribeEnabled || subBusy}
                    aria-pressed={checkoutPlan?.code === plan.code}
                  >
                    {subscribeEnabled ? (checkoutPlan?.code === plan.code ? "填寫資料中 ↓" : "訂閱此方案") : "目前未開放"}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {showPlanGrid && checkoutPlan && (
          <form className="billing-sub-checkout" onSubmit={handleSubscribe} noValidate aria-label="訂閱付款資料">
            <h3 className="billing-sub-status-name">
              訂閱「{checkoutPlan.name}」・每月 NT$ {checkoutPlan.monthly_price_ntd.toLocaleString()}
            </h3>
            <BuyerInvoiceFields buyer={buyer} setBuyer={setBuyer} errors={errors} live={live} />
            <div className={`wizard-acknowledgement ${errors.agree_terms ? "is-error" : ""}`}>
              <label className="wizard-checkbox">
                <input
                  type="checkbox"
                  checked={buyer.agree_terms}
                  aria-invalid={Boolean(errors.agree_terms)}
                  onChange={(e) => setBuyer({ ...buyer, agree_terms: e.target.checked })}
                />
                <span>
                  <strong>
                    我同意每月自動扣款 NT$ {checkoutPlan.monthly_price_ntd.toLocaleString()}，並同意<a href="/terms" target="_blank" rel="noreferrer">服務條款</a>
                  </strong>
                  <small>
                    {live
                      ? "首期立即以信用卡扣款，之後每月同一天由綠界自動扣款；可隨時在此取消，取消後不再扣款。"
                      : "綠界測試環境：請用綠界提供的測試信用卡，不會實際扣款。"}
                  </small>
                </span>
              </label>
              {errors.agree_terms && <p className="wizard-field-error" role="alert">{errors.agree_terms}</p>}
            </div>
            <div className="wizard-nav">
              <button className="secondary-button" type="button" onClick={() => setCheckoutPlan(null)} disabled={subBusy}>
                取消
              </button>
              <button className="primary-button" type="submit" disabled={subBusy}>
                {subBusy ? "前往綠界…" : "前往綠界綁定信用卡並付款"}
              </button>
            </div>
          </form>
        )}
      </div>
      {dialogHost}
    </section>
  );
}

export { SubscriptionPanel };
