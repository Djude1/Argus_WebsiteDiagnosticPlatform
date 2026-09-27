import { useEffect, useState } from "react";

import {
  cancelSubscription,
  fetchMySubscription,
  fetchSubscriptionPlans,
  subscribePlan,
} from "../../api";
import { useArgusStore } from "../../store";
import { apiErrorMessage, useConfirmDialogs } from "../../shared/AppShared";
import { formatDate } from "../../shared/formatters";
import { StarIcon } from "../../shared/LineIcons";

// ----- BillingPage 訂閱區塊（與單次購點 wizard 並列，月訂閱 vs 單次購點一目了然） -----

// 訂閱狀態 → 賣點語氣（active=綠、cancelled=amber、expired=灰）
const SUB_STATUS_TONE = {
  active: "good",
  cancelled: "warn",
  expired: "neutral",
};


export default function SubscriptionPanel({ purchasePlans }) {
  // subState：undefined=載入中、null=無訂閱、物件=目前訂閱
  const [subPlans, setSubPlans] = useState([]);
  const [subscribeEnabled, setSubscribeEnabled] = useState(false);
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

  async function handleSubscribe(plan) {
    const ok = await confirmDialog(
      `確定要訂閱「${plan.name}」嗎？測試環境以 NT$ ${plan.monthly_price_ntd.toLocaleString()} 視為首月一次付款，開通後立即發放 ${plan.monthly_coins.toLocaleString()} 點。`,
    );
    if (!ok) return;
    setSubBusy(true);
    setSubFeedback(null);
    try {
      const data = await subscribePlan(plan.code);
      setSubState(data.subscription);
      setSubFeedback({
        tone: "good",
        text: `已開通「${plan.name}」，首月 ${plan.monthly_coins.toLocaleString()} 點已入帳。`,
      });
      fetchWallet();
    } catch (err) {
      // 503（付費關閉）等後端 detail 會在這裡以繁中文案顯示
      setSubFeedback({
        tone: "bad",
        text: apiErrorMessage(err, "訂閱失敗，請稍後再試。"),
      });
    } finally {
      setSubBusy(false);
    }
  }

  async function handleCancel() {
    const ok = await confirmDialog(
      "確定要取消訂閱嗎？當期已付款權益會保留到期滿為止，之後不再每月發點。",
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
            每月自動發放點數、換算單點成本更低；隨時可取消，當期權益保留到期滿。適合持續巡檢的網站。
          </p>
        </div>
        <div className="billing-wallet-summary" aria-label="目前訂閱狀態">
          <span>目前方案</span>
          <strong>{subState ? subState.plan_name : "—"}</strong>
          <span>{subState ? subState.status_label : "尚未訂閱"}</span>
        </div>
      </header>

      {subscribeEnabled ? (
        <div className="billing-environment-notice tone-test" role="status">
          <span className="billing-environment-chip">STAGE</span>
          <span>
            <strong>安全測試模式</strong>・訂閱視為首月一次付款，不會定期扣款；開通後立即發放當月點數。
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
                <dt>剩餘期數</dt>
                <dd>{subState.periods_remaining} 期</dd>
              </div>
              <div>
                <dt>{isActive ? "下次贈點日" : "權益到期日"}</dt>
                <dd>{formatDate(subState.current_period_end)}</dd>
              </div>
              <div>
                <dt>開始日</dt>
                <dd>{formatDate(subState.started_at)}</dd>
              </div>
              {subState.cancelled_at && (
                <div>
                  <dt>取消時間</dt>
                  <dd>{formatDate(subState.cancelled_at)}</dd>
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
                  {isRecommended && <span className="billing-plan-recommend"><StarIcon /> 推薦</span>}
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
                    onClick={() => handleSubscribe(plan)}
                    disabled={!subscribeEnabled || subBusy}
                  >
                    {subscribeEnabled ? (subBusy ? "處理中…" : "訂閱此方案") : "目前未開放"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {dialogHost}
    </section>
  );
}
