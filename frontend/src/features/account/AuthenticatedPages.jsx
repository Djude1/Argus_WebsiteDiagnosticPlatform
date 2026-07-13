import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import NavActions from "../../components/navigation/NavActions.jsx";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges.jsx";
import { useArgusStore } from "../../store";
import brandLogo from "../../assets/brand-logo.webp";
import {
  CATEGORY_COLOR,
  CATEGORY_LABELS,
  CountUp,
  LineChart,
  SeverityBarChart,
  StackedBar,
  apiErrorMessage,
  useDialogFocus,
} from "../../shared/AppShared.jsx";

const NAV_ITEMS = [
  { to: "/project", label: "首頁", emoji: "🏠" },
  { to: "/dashboard", label: "Dashboard", emoji: "📊" },
  { to: "/scans", label: "掃描", emoji: "🔍" },
  { to: "/history", label: "歷史", emoji: "📈" },
  { to: "/billing", label: "購點", emoji: "💎" },
  { to: "/reviews", label: "評論", emoji: "⭐" },
  { to: "/settings", label: "設定", emoji: "⚙️" },
];

function TopNav() {
  const accessToken = useArgusStore((state) => state.accessToken);
  const replayIntro = useArgusStore((s) => s.replayIntro);
  const location = useLocation();
  const navigate = useNavigate();
  if (!accessToken) return null;
  // /admin/* 與公開頁走獨立 layout，不顯示前台 TopNav
  if (location.pathname.startsWith("/admin")) return null;
  if (["/project", "/team", "/purchase", "/download"].some((p) =>
    location.pathname.startsWith(p),
  )) return null;
  // 掃描頁的 top bar 不顯示「評論」入口（首頁等其他頁保留）
  const onScanPage = location.pathname.startsWith("/scans");
  const visibleNavItems = onScanPage
    ? NAV_ITEMS.filter((item) => item.to !== "/reviews")
    : NAV_ITEMS;
  return (
    <nav className="argus-nav">
      <div className="argus-nav-inner">
        <button type="button" className="argus-brand active" onClick={() => { replayIntro(); navigate("/project"); }} title="重播開場動畫" aria-label="重播 ARGUS 開場動畫">
          <img src={brandLogo} className="argus-brand-logo" alt="ARGUS — AI 網站健檢平台" />
          <span className="argus-brand-sub">AI 網站健檢平台</span>
        </button>
        <div className="argus-nav-links">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `argus-nav-link ${isActive ? "active" : ""}`
              }
            >
              <span aria-hidden="true">{item.emoji}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
        <NavActions />
      </div>
    </nav>
  );
}

// ============================================================
// Dashboard 頁
// ============================================================

function ScoreRing({ value, label, size = 96 }) {
  const display = value === null || value === undefined ? "—" : Math.round(value);
  const pct = typeof value === "number" ? Math.max(0, Math.min(100, value)) : 0;
  const tone = pct >= 80 ? "good" : pct >= 60 ? "medium" : "bad";
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  return (
    <div className={`score-ring tone-${tone}`} style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth="8"
          className="ring-track"
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          fill="none"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="ring-progress"
        />
      </svg>
      <div className="score-ring-text">
        <span className="score-ring-value">{display}</span>
        {label && <span className="score-ring-label">{label}</span>}
      </div>
    </div>
  );
}

function StatTile({ label, value, hint, tone = "neutral", animateValue, onClick }) {
  const inner = (
    <>
      <p className="stat-tile-label">{label}</p>
      <p className="stat-tile-value">
        {typeof animateValue === "number" ? <CountUp value={animateValue} /> : value}
      </p>
      {hint && <p className="stat-tile-hint">{hint}</p>}
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        className={`stat-tile tone-${tone} is-clickable`}
        onClick={onClick}
      >
        {inner}
      </button>
    );
  }
  return <div className={`stat-tile tone-${tone}`}>{inner}</div>;
}

// formatRelativeTime 在下方 L3690 已定義，這裡不重複。

// Dashboard 公告一律採非阻塞 toast；法律授權保留在建立掃描流程內。
function AnnouncementToast({ announcements, onDismiss }) {
  const [hovering, setHovering] = useState({});

  useEffect(() => {
    // 對每個顯示中的 toast 排 5 秒自動關（hover 時暫停）
    const timers = announcements
      .filter((a) => !hovering[a.id])
      .map((a) =>
        setTimeout(() => onDismiss(a.id), 5000),
      );
    return () => timers.forEach((t) => clearTimeout(t));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [announcements, hovering]);

  if (!announcements.length) return null;
  return (
    <div className="argus-toast-stack" role="status" aria-live="polite">
      {announcements.map((ann) => (
        <div
          key={ann.id}
          className="argus-toast"
          onMouseEnter={() => setHovering((h) => ({ ...h, [ann.id]: true }))}
          onMouseLeave={() => setHovering((h) => ({ ...h, [ann.id]: false }))}
        >
          <div className="argus-toast-body">
            <div className="argus-toast-title">{ann.title}</div>
            <div className="argus-toast-content">{ann.content.slice(0, 100)}{ann.content.length > 100 ? "…" : ""}</div>
          </div>
          <button
            type="button"
            className="argus-toast-close"
            onClick={() => onDismiss(ann.id)}
            aria-label="關閉公告"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

function DashboardPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [categoriesData, setCategoriesData] = useState(null);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.get("/dashboard/"), api.get("/findings-by-category/")])
      .then(([dashRes, catRes]) => {
        if (cancelled) return;
        setData(dashRes.data);
        setCategoriesData(catRes.data);
      })
      .catch(() => {
        if (!cancelled) setError("無法載入 Dashboard 資料。");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    api.get("/admin/announcements/active/")
      .then((r) => {
        const all = r.data.announcements || [];
        const toShow = all.filter((ann) => {
          try {
            return !localStorage.getItem(`ann_dismissed_${ann.id}`);
          } catch {
            return true;
          }
        });
        if (toShow.length) {
          setToasts(toShow);
        }
      })
      .catch(() => {});
  }, []);

  function handleDismiss(annId) {
    try {
      localStorage.setItem(`ann_dismissed_${annId}`, "1");
    } catch {
      // 儲存空間受限時仍允許關閉本次顯示的公告。
    }
    setToasts((prev) => prev.filter((a) => a.id !== annId));
  }

  if (error) {
    return (
      <section className="panel">
        <p className="error-text">{error}</p>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="panel">
        <p className="hint-text">載入 Dashboard 中...</p>
      </section>
    );
  }

  const { wallet } = data;
  const totalFindings = Object.values(data.severity_totals || {}).reduce(
    (sum, n) => sum + n,
    0,
  );

  return (
    <div className="dashboard-grid">
      <div className="dashboard-hero">
        <div className="dashboard-hero-text">
          <p className="eyebrow text-cyan-300">總覽</p>
          <h2 className="dashboard-hero-title">
            你已執行 <span>{data.total_scans}</span> 次健檢
          </h2>
          <p className="dashboard-hero-sub">
            完成 {data.completed_scans}・失敗 {data.failed_scans}・點數餘額{" "}
            <strong>{wallet?.balance ?? 0}</strong> coin
          </p>
          <div className="dashboard-hero-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => navigate("/scans")}
            >
              + 開始新掃描
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => navigate("/history")}
            >
              查看歷史
            </button>
          </div>
        </div>
        <ScoreRing value={data.average_score} label="平均分" size={120} />
      </div>

      <div className="stat-grid">
        <StatTile
          label="掃描總數"
          animateValue={data.total_scans}
          hint="所有狀態合計"
          tone="cyan"
        />
        <StatTile
          label="點數餘額"
          animateValue={wallet?.balance || 0}
          hint={`≈ 還能掃 ${Math.floor((wallet?.balance || 0) / (wallet?.coin_per_page || 10)).toLocaleString()} 頁 · 累積花費 NT$ ${(wallet?.total_purchased_ntd || 0).toLocaleString()}`}
          tone="violet"
        />
        <StatTile
          label="累計 Findings"
          animateValue={totalFindings}
          hint="跨所有完成掃描"
          tone="amber"
        />
        <StatTile
          label="高/嚴重"
          animateValue={
            (data.severity_totals?.critical || 0) +
            (data.severity_totals?.high || 0)
          }
          hint="critical + high · 點看清單"
          tone="rose"
          onClick={() => navigate("/scans")}
        />
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>Findings 嚴重度分佈</h3>
          <span className="hint-text-sm">跨所有掃描</span>
        </div>
        <SeverityBarChart
          severityTotals={data.severity_totals}
          title=""
        />
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>各類別 finding 佔比</h3>
          <span className="hint-text-sm">哪一類問題最多</span>
        </div>
        <StackedBar
          data={Object.keys(CATEGORY_LABELS).map((cat) => ({
            label: CATEGORY_LABELS[cat],
            value: categoriesData?.categories?.[cat]?.total_findings || 0,
            color: CATEGORY_COLOR[cat],
          }))}
        />
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>各類別平均</h3>
          <span className="hint-text-sm">基於完成的掃描</span>
        </div>
        <div className="category-rings">
          {Object.keys(CATEGORY_LABELS).map((cat) => (
            <div className="category-ring-item" key={cat}>
              <ScoreRing
                value={data.category_averages?.[cat] ?? null}
                size={84}
              />
              <span className={`category-pill cat-${cat}`}>
                {CATEGORY_LABELS[cat]}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel dashboard-panel">
        <div className="dashboard-panel-header">
          <h3>最近掃描</h3>
          <button
            className="secondary-button"
            type="button"
            onClick={() => navigate("/scans")}
          >
            前往掃描頁
          </button>
        </div>
        <ul className="recent-list">
          {data.recent_scans.length === 0 && (
            <li className="text-sm text-slate-400">尚無掃描紀錄。</li>
          )}
          {data.recent_scans.map((scan) => (
            <li key={scan.id}>
              <button
                className="recent-row"
                type="button"
                onClick={() => navigate(`/scans/${scan.id}`)}
              >
                <span className="recent-origin">{scan.origin}</span>
                <span className="recent-time">{formatRelativeTime(scan.completed_at || scan.created_at)}</span>
                <ScanStatusBadge status={scan.status} />
                <ScoreBadge score={scan.overall_score} />
              </button>
            </li>
          ))}
        </ul>
      </div>
      <AnnouncementToast announcements={toasts} onDismiss={handleDismiss} />
    </div>
  );
}

// ============================================================
// History 頁（同網址歷次分數）
// ============================================================

function Sparkline({ values }) {
  if (!values.length) return <span className="text-slate-400">—</span>;
  const w = 120;
  const h = 32;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? w / (values.length - 1) : 0;
  const points = values
    .map((v, i) => `${i * step},${h - ((v - min) / range) * (h - 6) - 3}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="sparkline">
      <polyline points={points} fill="none" strokeWidth="2" />
    </svg>
  );
}

function HistoryPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .get("/history/")
      .then((r) => !cancelled && setData(r.data))
      .catch(() => !cancelled && setError("無法載入歷史資料。"));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;
  if (!data) return <section className="panel"><p className="hint-text">載入中...</p></section>;

  return (
    <section className="panel">
      <div className="dashboard-panel-header">
        <h3>同網址分數歷史</h3>
        <span className="hint-text-sm">每個 origin 的歷次健檢</span>
      </div>
      {data.origins.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">尚無紀錄。</p>
      )}
      <div className="history-grid">
        {data.origins.map((origin) => {
          const chronological = origin.scans
            .filter((s) => s.overall_score !== null && s.overall_score !== undefined)
            .slice()
            .reverse();
          const chartData = chronological.map((s) => ({
            label: new Date(s.created_at).toLocaleDateString("zh-Hant", {
              month: "numeric",
              day: "numeric",
            }),
            value: s.overall_score,
          }));
          const deltaLabel =
            origin.delta === null || origin.delta === undefined
              ? null
              : origin.delta > 0
                ? `▲ +${origin.delta}`
                : origin.delta < 0
                  ? `▼ ${origin.delta}`
                  : "—";
          const deltaTone =
            origin.delta === null || origin.delta === undefined
              ? "neutral"
              : origin.delta >= 0
                ? "good"
                : "bad";
          return (
            <div key={origin.origin} className="history-card">
              <div className="history-card-head">
                <span className="history-origin">{origin.origin}</span>
                <span className="hint-text-sm">{origin.total_scans} 次</span>
              </div>
              <div className="history-card-mid">
                <ScoreBadge score={origin.latest_score} />
                {deltaLabel && (
                  <span className={`history-delta tone-${deltaTone}`}>{deltaLabel}</span>
                )}
              </div>
              {chartData.length > 0 && (
                <div className="history-chart">
                  <LineChart data={chartData} ariaLabel={`${origin.origin} 分數趨勢`} />
                </div>
              )}
              <ul className="history-list">
                {origin.scans.slice(0, 5).map((s, idx) => (
                  <li key={s.id}>
                    <button
                      className={`history-row ${idx === 0 ? "is-latest" : "is-older"}`}
                      type="button"
                      onClick={() => navigate(`/scans/${s.id}`)}
                    >
                      {idx === 0 ? (
                        <span className="history-latest-chip" aria-label="最新">
                          ✨ 最新
                        </span>
                      ) : null}
                      <span className="text-xs text-slate-500">
                        {new Date(s.created_at).toLocaleString("zh-Hant")}
                      </span>
                      <ScanStatusBadge status={s.status} />
                      <ScoreBadge score={s.overall_score} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}

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
      {WIZARD_STEPS.map((step, idx) => {
        const state = step.id < current ? "done" : step.id === current ? "active" : "pending";
        return (
          <li key={step.id} className={`wizard-step ${state}`}>
            <span className="wizard-step-circle">
              {state === "done" ? "✓" : step.id}
            </span>
            <span className="wizard-step-label">{step.label}</span>
            {idx < WIZARD_STEPS.length - 1 && <span className="wizard-step-bar" />}
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
      if (!buyer.company_name.trim()) errs.company_name = "公司發票須填公司抬頭";
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
    if (!buyer.agree_terms) errs.agree_terms = "請勾選同意購買條款";
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
            <dt>金額</dt><dd>NT$ {completedOrder.price_ntd.toLocaleString()}</dd>
            <dt>入帳點數</dt><dd>+{completedOrder.coin_amount.toLocaleString()} coin</dd>
            <dt>當前餘額</dt><dd className="hl-balance">{wallet?.balance?.toLocaleString()} coin</dd>
            <dt>發票類型</dt><dd>{completedOrder.invoice_type_label}{completedOrder.invoice_type === "company" ? `（${completedOrder.company_name} / ${completedOrder.tax_id}）` : ""}</dd>
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
    <section className="panel space-y-4">
      <div>
        <p className="eyebrow">點數商店</p>
        <h2 className="section-title">購買 Argus 點數</h2>
        <p className="mt-1 text-sm text-slate-600">
          每爬一頁需 {wallet?.coin_per_page ?? 10} coin；目前餘額 <strong>{wallet?.balance?.toLocaleString() ?? "—"}</strong> coin。
        </p>
        {paymentMode === "ecpay_test" ? (
          <div className="billing-test-banner" role="status">
            <span className="billing-test-chip">ECPAY TEST</span>
            <span>
              目前使用<strong>綠界測試環境</strong>，不會真的扣款；只有簽章、訂單與金額驗證通過後才會入點。
            </span>
          </div>
        ) : (
          <div className="billing-test-banner" role="status">
            <span className="billing-test-chip">暫停購點</span>
            <span>綠界測試付款尚未啟用，目前不接受訂單，也不會直接入點。</span>
          </div>
        )}
      </div>

      <WizardStepper current={step} />

      {step === 1 && (
        <div className="billing-plan-grid">
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
        <div className="wizard-form-wrap">
          <div className="wizard-summary-mini">
            <span>已選方案</span>
            <strong>{selectedPlan.name}</strong>
            <span className="wizard-summary-price">
              NT$ {selectedPlan.price_ntd.toLocaleString()} ／ {selectedPlan.coin_amount} coin
            </span>
          </div>

          <div className="wizard-form">
            <div className="wizard-field">
              <label htmlFor="buyer_name">姓名 *</label>
              <input
                id="buyer_name"
                className="input"
                placeholder="王小明"
                value={buyer.buyer_name}
                onChange={(e) => setBuyer({ ...buyer, buyer_name: e.target.value })}
              />
              {errors.buyer_name && <p className="wizard-field-error">{errors.buyer_name}</p>}
            </div>

            <div className="wizard-field">
              <label htmlFor="buyer_email">收據寄送 email *</label>
              <input
                id="buyer_email"
                className="input"
                type="email"
                placeholder="you@example.com"
                value={buyer.buyer_email}
                onChange={(e) => setBuyer({ ...buyer, buyer_email: e.target.value })}
              />
              {errors.buyer_email && <p className="wizard-field-error">{errors.buyer_email}</p>}
            </div>

            {/* 發票設定 */}
            <div className="billing-invoice-section">
              <h4 className="billing-section-title">發票設定</h4>

              {/* 發票類型 */}
              <div className="billing-radio-group">
                <label className="billing-radio-label">
                  <input
                    type="radio"
                    name="invoice_type"
                    checked={buyer.invoice_type === "personal"}
                    onChange={() => setBuyer({ ...buyer, invoice_type: "personal", carrier_type: "cloud", carrier_id: "" })}
                  />
                  個人電子發票
                </label>
                <label className="billing-radio-label">
                  <input
                    type="radio"
                    name="invoice_type"
                    checked={buyer.invoice_type === "company"}
                    onChange={() => setBuyer({ ...buyer, invoice_type: "company", carrier_type: "cloud", carrier_id: "" })}
                  />
                  公司統一發票
                </label>
              </div>

              {/* 個人：載具選擇 */}
              {buyer.invoice_type === "personal" && (
                <div className="billing-carrier-section">
                  <div className="billing-radio-group">
                    <label className="billing-radio-label">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "cloud"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "cloud", carrier_id: "" })}
                      />
                      雲端發票（自動歸戶，不需載具）
                    </label>
                    <label className="billing-radio-label">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "mobile_barcode"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "mobile_barcode", carrier_id: "" })}
                      />
                      手機條碼載具
                    </label>
                    <label className="billing-radio-label">
                      <input
                        type="radio"
                        name="carrier_type"
                        checked={buyer.carrier_type === "citizen_digital"}
                        onChange={() => setBuyer({ ...buyer, carrier_type: "citizen_digital", carrier_id: "" })}
                      />
                      自然人憑證載具
                    </label>
                  </div>
                  {buyer.carrier_type !== "cloud" && (
                    <input
                      className={`input ${errors.carrier_id ? "is-error" : ""}`}
                      type="text"
                      placeholder={buyer.carrier_type === "mobile_barcode" ? "/XXXXXXX（手機條碼）" : "AB12345678901234（自然人憑證）"}
                      value={buyer.carrier_id}
                      onChange={(e) => setBuyer({ ...buyer, carrier_id: e.target.value.toUpperCase() })}
                    />
                  )}
                  {errors.carrier_id && <p className="billing-error">{errors.carrier_id}</p>}
                </div>
              )}

              {/* 公司：公司名稱 + 統一編號 */}
              {buyer.invoice_type === "company" && (
                <div className="billing-company-section">
                  <input
                    className={`input ${errors.company_name ? "is-error" : ""}`}
                    type="text"
                    placeholder="公司名稱"
                    value={buyer.company_name || ""}
                    onChange={(e) => setBuyer({ ...buyer, company_name: e.target.value })}
                  />
                  {errors.company_name && <p className="billing-error">{errors.company_name}</p>}
                  <input
                    className={`input ${errors.tax_id ? "is-error" : ""}`}
                    type="text"
                    placeholder="統一編號（8 碼數字）"
                    value={buyer.tax_id || ""}
                    onChange={(e) => setBuyer({ ...buyer, tax_id: e.target.value.replace(/\D/g, "") })}
                    maxLength={8}
                  />
                  {errors.tax_id && <p className="billing-error">{errors.tax_id}</p>}
                </div>
              )}
            </div>

            <div className="wizard-field">
              <label className="wizard-checkbox">
                <input
                  type="checkbox"
                  checked={buyer.agree_terms}
                  onChange={(e) => setBuyer({ ...buyer, agree_terms: e.target.checked })}
                />
                <span>
                  我已閱讀並同意<strong>購買條款</strong>：點數一經入帳不可退費（如需退費請聯絡管理員），
                  並理解本系統使用綠界測試環境，不會產生真實扣款。
                </span>
              </label>
              {errors.agree_terms && <p className="wizard-field-error">{errors.agree_terms}</p>}
            </div>
          </div>

          <div className="wizard-nav">
            <button className="secondary-button" type="button" onClick={() => setStep(1)}>
              ← 上一步
            </button>
            <button className="primary-button" type="button" onClick={goToConfirm}>
              下一步：確認訂購 →
            </button>
          </div>
        </div>
      )}

      {step === 3 && selectedPlan && (
        <div className="wizard-confirm">
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
            <h4>買家資訊</h4>
            <dl className="wizard-confirm-dl">
              <dt>姓名</dt><dd>{buyer.buyer_name}</dd>
              <dt>email</dt><dd>{buyer.buyer_email}</dd>
              <dt>發票</dt>
              <dd>
                {buyer.invoice_type === "company"
                  ? `公司發票（${buyer.company_name} / 統編 ${buyer.tax_id}）`
                  : "個人電子發票"}
              </dd>
              {buyer.invoice_type === "personal" && (
                <>
                  <dt>載具</dt>
                  <dd>
                    {buyer.carrier_type === "cloud" && "雲端發票（寄 email）"}
                    {buyer.carrier_type === "mobile_barcode" && `手機條碼 ${buyer.carrier_id}`}
                    {buyer.carrier_type === "citizen_digital" && `自然人憑證 ${buyer.carrier_id}`}
                  </dd>
                </>
              )}
            </dl>
          </div>

          <div className="wizard-confirm-total">
            <span>應付金額</span>
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
              {submitting ? "前往綠界測試環境…" : "前往綠界測試付款"}
            </button>
          </div>
        </div>
      )}

    </section>
  );
}

// ============================================================
// Reviews 頁（Trustpilot 風格：所有人看得到，自己可寫/改）
// ============================================================

function StarRating({ value, onChange, readOnly = false, size = 24 }) {
  const stars = [1, 2, 3, 4, 5];
  return (
    <div className={`star-rating ${readOnly ? "is-read" : ""}`} role="radiogroup">
      {stars.map((n) => (
        <button
          key={n}
          type="button"
          className={`star ${n <= (value || 0) ? "filled" : ""}`}
          style={{ fontSize: size }}
          onClick={readOnly ? undefined : () => onChange?.(n)}
          aria-label={`${n} 星`}
          disabled={readOnly}
        >
          ★
        </button>
      ))}
    </div>
  );
}

// 相對時間 helper：3 分鐘前 / 2 小時前 / 1 天前 / 1 個月前
function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const sec = Math.floor((now - then) / 1000);
  if (sec < 60) return "剛剛";
  if (sec < 3600) return `${Math.floor(sec / 60)} 分鐘前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小時前`;
  const days = Math.floor(sec / 86400);
  if (days < 30) return `${days} 天前`;
  if (days < 365) return `${Math.floor(days / 30)} 個月前`;
  return `${Math.floor(days / 365)} 年前`;
}

// 取出第一個字當 avatar 縮寫
function getAvatarLetter(name) {
  if (!name) return "?";
  const trimmed = name.trim();
  return trimmed.charAt(0).toUpperCase();
}

// 從名字算 hash 取 6 種顏色之一（avatar 背景色）
function avatarColorFor(name) {
  const colors = [
    "#06b6d4", "#6366f1", "#ec4899", "#f59e0b", "#10b981", "#a855f7",
  ];
  let h = 0;
  for (let i = 0; i < (name || "").length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return colors[h % colors.length];
}

// 圖片 lightbox modal
function ImageLightbox({ url, onClose }) {
  useEffect(() => {
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!url) return null;
  return (
    <div className="lightbox-backdrop" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="關閉">×</button>
      <img src={url} alt="預覽" className="lightbox-image" onClick={(e) => e.stopPropagation()} />
    </div>
  );
}

function ReviewMessageBubble({ msg, onHelpful, onImageClick }) {
  const sideClass = msg.is_admin ? "is-admin" : "is-user";
  const avatar = msg.is_admin ? "🛡️" : getAvatarLetter(msg.author_display);
  const avatarBg = msg.is_admin ? "#6366f1" : avatarColorFor(msg.author_display);
  return (
    <li className={`review-msg ${sideClass}`}>
      <div className="review-msg-avatar" style={{ background: avatarBg }}>{avatar}</div>
      <div className="review-msg-content">
        <div className="review-msg-head">
          <span className="review-msg-author">
            {msg.author_display}
            {msg.is_admin && <span className="review-msg-badge">Argus 官方</span>}
          </span>
          <span className="review-msg-time" title={new Date(msg.created_at).toLocaleString("zh-Hant")}>
            {formatRelativeTime(msg.created_at)}
          </span>
        </div>
        {msg.body && <p className="review-msg-body">{msg.body}</p>}
        {msg.image_url && (
          <button
            type="button"
            className="review-msg-image-btn"
            onClick={() => onImageClick(msg.image_url)}
          >
            <img src={msg.image_url} alt="附件" className="review-msg-image" />
          </button>
        )}
        <div className="review-msg-actions">
          <button
            type="button"
            className={`helpful-btn ${msg.my_helpful ? "active" : ""}`}
            onClick={() => onHelpful(msg)}
          >
            👍 有幫助 {msg.helpful_count > 0 && <span>· {msg.helpful_count}</span>}
          </button>
        </div>
      </div>
    </li>
  );
}

function ReviewMessageComposer({ reviewId, onPosted }) {
  const [body, setBody] = useState("");
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const imageInputRef = useRef(null);

  function clearImage() {
    setImageFile(null);
    if (imageInputRef.current) imageInputRef.current.value = "";
  }

  useEffect(() => {
    if (!imageFile) {
      setImagePreview("");
      return undefined;
    }
    const preview = URL.createObjectURL(imageFile);
    setImagePreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [imageFile]);

  function handleImageChange(event) {
    const file = event.target.files?.[0] || null;
    if (!file) return;
    const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!allowedTypes.includes(file.type)) {
      setError("只接受 JPEG、PNG 或 WebP 圖片。");
      event.target.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("圖片大小不可超過 5 MiB。");
      event.target.value = "";
      return;
    }
    setError("");
    setImageFile(file);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!body.trim() && !imageFile) {
      setError("請輸入文字或附上圖片");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const formData = new FormData();
      if (body.trim()) formData.append("body", body.trim());
      if (imageFile) formData.append("image", imageFile);
      await api.post(`/reviews/${reviewId}/messages/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setBody("");
      clearImage();
      onPosted?.();
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          err?.response?.data?.image?.[0] ||
          err?.response?.data?.non_field_errors?.[0] ||
          "送出失敗，請稍後再試。",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="review-composer" onSubmit={handleSubmit}>
      <textarea
        className="input review-composer-input"
        placeholder="補充說明或回覆管理員…"
        rows={2}
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      <div className="review-composer-row">
        <label className="review-composer-image">
          📎 附圖
          <input
            ref={imageInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleImageChange}
          />
        </label>
        {imageFile && (
          <span className="review-composer-filename" title={imageFile.name}>
            {imageFile.name}
            <button
              type="button"
              className="review-composer-clear"
              onClick={clearImage}
              aria-label="移除附圖"
            >×</button>
          </span>
        )}
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "送出中…" : "送出"}
        </button>
      </div>
      <p className="review-composer-hint">支援 JPEG、PNG、WebP；上限 5 MiB、最長邊 4096 px。</p>
      {imagePreview && (
        <img
          className="review-composer-preview"
          src={imagePreview}
          alt={`待上傳圖片預覽：${imageFile.name}`}
        />
      )}
      {error && <p className="review-composer-error">{error}</p>}
    </form>
  );
}

function ReviewCard({ review, onHelpful, onMessageHelpful, onImageClick, onPosted, loggedIn }) {
  const [expanded, setExpanded] = useState(review.is_mine);
  const messageCount = (review.messages || []).length;
  const avatarBg = avatarColorFor(review.user_display);
  return (
    <article
      className={[
        "review-card",
        review.is_mine ? "is-mine" : "",
        review.is_featured ? "is-featured" : "",
      ].filter(Boolean).join(" ")}
    >
      {review.is_featured && (
        <span className="review-featured-ribbon">⭐ 精選評論</span>
      )}
      <header className="review-card-head">
        <div className="review-card-author-row">
          <div className="review-card-avatar" style={{ background: avatarBg }}>
            {getAvatarLetter(review.user_display)}
          </div>
          <div className="review-card-author-meta">
            <div className="review-card-author">
              {review.user_display}
              {review.is_mine && <span className="review-mine-chip">我</span>}
              {review.verified_buyer && <span className="review-verified-chip">✓ 已購買</span>}
            </div>
            <div className="review-card-time" title={new Date(review.created_at).toLocaleString("zh-Hant")}>
              {formatRelativeTime(review.created_at)}
            </div>
          </div>
        </div>
        <StarRating value={review.rating} readOnly size={20} />
      </header>

      {review.comment && (
        <p className="review-card-body">{review.comment}</p>
      )}

      <div className="review-card-actions">
        <button
          type="button"
          className={`helpful-btn ${review.my_helpful ? "active" : ""}`}
          onClick={() => onHelpful(review)}
          disabled={!loggedIn}
          title={loggedIn ? "" : "請先登入"}
        >
          👍 有幫助 {review.helpful_count > 0 && <span>· {review.helpful_count}</span>}
        </button>
        {messageCount > 0 && (
          <button
            type="button"
            className="thread-toggle-btn"
            onClick={() => setExpanded((v) => !v)}
          >
            💬 {messageCount} 則對話 {expanded ? "▴" : "▾"}
          </button>
        )}
      </div>

      {expanded && (
        <ol className="review-thread">
          {(review.messages || []).map((m) => (
            <ReviewMessageBubble
              key={m.id}
              msg={m}
              onHelpful={(msg) => onMessageHelpful(msg)}
              onImageClick={onImageClick}
            />
          ))}
        </ol>
      )}

      {loggedIn && review.is_mine && (
        <ReviewMessageComposer
          reviewId={review.id}
          onPosted={() => { onPosted?.(); setExpanded(true); }}
        />
      )}
    </article>
  );
}

function ReviewsPage() {
  const [reviews, setReviews] = useState([]);
  const [mine, setMine] = useState(null);
  const [initialRating, setInitialRating] = useState(0);
  const [initialComment, setInitialComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [sort, setSort] = useState("helpful");
  const [lightboxUrl, setLightboxUrl] = useState(null);
  const accessToken = useArgusStore((s) => s.accessToken);

  async function loadAll() {
    const list = await api.get(`/reviews/?sort=${sort}`).catch(() => null);
    if (list) setReviews(list.data.reviews || []);
    if (accessToken) {
      try {
        const me = await api.get("/reviews/mine/");
        setMine(me.data);
      } catch {
        setMine(null);
      }
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, sort]);

  async function handleReviewHelpful(review) {
    if (!accessToken) return;
    try {
      const r = await api.post(`/reviews/${review.id}/helpful/`);
      setReviews((rs) => rs.map((x) =>
        x.id === review.id
          ? { ...x, helpful_count: r.data.helpful_count, my_helpful: r.data.my_helpful }
          : x,
      ));
    } catch {}
  }

  async function handleMessageHelpful(msg) {
    if (!accessToken) return;
    try {
      const r = await api.post(`/reviews/messages/${msg.id}/helpful/`);
      setReviews((rs) => rs.map((x) => ({
        ...x,
        messages: (x.messages || []).map((m) =>
          m.id === msg.id
            ? { ...m, helpful_count: r.data.helpful_count, my_helpful: r.data.my_helpful }
            : m,
        ),
      })));
    } catch {}
  }

  async function handleFirstReview(event) {
    event.preventDefault();
    if (!initialRating) {
      setFeedback({ tone: "bad", message: "請選擇 1-5 星" });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const response = await api.post("/reviews/mine/", {
        rating: initialRating,
        comment: initialComment,
      });
      setMine(response.data);
      setFeedback({ tone: "good", message: "評論已送出，感謝你！" });
      await loadAll();
    } catch (err) {
      setFeedback({
        tone: "bad",
        message: err?.response?.data?.detail || "送出失敗，請稍後再試。",
      });
    } finally {
      setSubmitting(false);
    }
  }

  const total = reviews.length;
  const avg = total
    ? (reviews.reduce((s, r) => s + r.rating, 0) / total).toFixed(2)
    : null;
  const distribution = [5, 4, 3, 2, 1].map((star) => ({
    star,
    count: reviews.filter((r) => r.rating === star).length,
  }));

  return (
    <section className="panel space-y-4">
      <div>
        <p className="eyebrow">使用者評論</p>
        <h1 className="section-title">大家對 Argus 的評價</h1>
        <p className="mt-1 text-xs text-slate-500">
          星等一人只能評一次（送出後鎖定）；後續可在留言區補充意見、附上問題照片，與管理員對話。
        </p>
      </div>

      <div className="reviews-stats">
        <div className="reviews-avg">
          <div className="reviews-avg-value">{avg ?? "—"}</div>
          <StarRating value={avg ? Math.round(avg) : 0} readOnly size={20} />
          <p className="reviews-avg-meta">共 {total} 則評論</p>
        </div>
        <div className="reviews-distribution">
          {distribution.map((d) => {
            const pct = total ? (d.count / total) * 100 : 0;
            return (
              <div key={d.star} className="reviews-dist-row">
                <span className="reviews-dist-label">{d.star} ★</span>
                <div className="reviews-dist-track">
                  <div
                    className="reviews-dist-fill"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="reviews-dist-count">{d.count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 還沒評過的人才看到評分表單 */}
      {accessToken && !mine && (
        <form className="reviews-form" onSubmit={handleFirstReview}>
          <p className="reviews-form-title">寫下你對 Argus 的評價（一次定終生）</p>
          <StarRating value={initialRating} onChange={setInitialRating} size={32} />
          <textarea
            className="input reviews-textarea"
            placeholder="（選填）你最喜歡的功能、改進建議..."
            rows={3}
            value={initialComment}
            onChange={(e) => setInitialComment(e.target.value)}
          />
          {feedback && (
            <p className={`reviews-feedback tone-${feedback.tone}`}>
              {feedback.message}
            </p>
          )}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "送出中..." : "送出評論"}
          </button>
        </form>
      )}

      {accessToken && mine && (
        <div className="reviews-mine-banner">
          <span>
            ✓ 你已為 Argus 評分 <strong>{"★".repeat(mine.rating)}{"☆".repeat(5 - mine.rating)}</strong>（{mine.rating}）
          </span>
          <span className="text-xs text-slate-500">
            如要補充意見，請在下方自己的評論卡裡留言。
          </span>
        </div>
      )}

      <div className="reviews-toolbar">
        <span className="text-sm text-slate-600">共 {reviews.length} 則評論</span>
        <div className="reviews-sort">
          <button
            type="button"
            className={`reviews-sort-btn ${sort === "helpful" ? "active" : ""}`}
            onClick={() => setSort("helpful")}
          >最有幫助</button>
          <button
            type="button"
            className={`reviews-sort-btn ${sort === "newest" ? "active" : ""}`}
            onClick={() => setSort("newest")}
          >最新</button>
        </div>
      </div>

      <div className="reviews-list">
        {reviews.length === 0 && (
          <p className="hint-text">尚未有評論。第一個寫下評價吧！</p>
        )}
        {reviews.map((review) => (
          <ReviewCard
            key={review.id}
            review={review}
            loggedIn={!!accessToken}
            onHelpful={handleReviewHelpful}
            onMessageHelpful={handleMessageHelpful}
            onImageClick={setLightboxUrl}
            onPosted={loadAll}
          />
        ))}
      </div>

      <ImageLightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />
    </section>
  );
}

// ============================================================
// Settings 頁
// ============================================================

function SettingsPage() {
  const navigate = useNavigate();
  const wallet = useArgusStore((s) => s.wallet);
  const setToken = useArgusStore((s) => s.setToken);
  const [data, setData] = useState(null);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdError, setPwdError] = useState("");

  const [meData, setMeData] = useState(null);
  useEffect(() => {
    api.get("/auth/me/").then((r) => {
      setMeData(r.data);
      setFirstName(r.data.first_name || "");
      setLastName(r.data.last_name || "");
    }).catch(() => {});
    api.get("/dashboard/").then((r) => setData(r.data)).catch(() => {});
  }, []);

  const balance = wallet?.balance ?? 0;
  const purchased = wallet?.total_purchased_ntd ?? 0;
  const scansUsed = wallet?.total_scans_used ?? 0;
  const totalFindings = data
    ? Object.values(data.severity_totals || {}).reduce((sum, n) => sum + n, 0)
    : 0;
  const isEmailAccount = meData?.auth_provider === "email";

  async function handleSaveProfile(e) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg("");
    try {
      await api.patch("/auth/me/", { first_name: firstName, last_name: lastName });
      setSaveMsg("已儲存");
    } catch {
      setSaveMsg("儲存失敗");
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    setPwdError("");
    if (newPwd !== confirmPwd) { setPwdError("兩次密碼不一致"); return; }
    if (newPwd.length < 8) { setPwdError("新密碼至少 8 個字元"); return; }
    try {
      await api.post("/auth/change-password/", { old_password: oldPwd, new_password: newPwd });
      setToken(null);
      navigate("/login", { replace: true });
    } catch (err) {
      setPwdError(err.response?.data?.detail || "密碼變更失敗");
    }
  }

  return (
    <div className="settings-page">
      <h1 className="settings-title">帳號設定</h1>

      <section className="settings-section">
        <h2 className="settings-section-title">點數錢包</h2>
        <div className="settings-wallet-row">
          <div>
            <p className="settings-wallet-balance">{balance} <span className="settings-wallet-unit">coin</span></p>
            <p className="settings-card-hint">累積購買 NT$ {purchased.toLocaleString()} · 累計 {scansUsed} 次掃描</p>
          </div>
          <button className="settings-save-btn" type="button" onClick={() => navigate("/billing")}>前往購點</button>
        </div>
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">個人資料</h2>
        <form className="settings-form" onSubmit={handleSaveProfile}>
          <div className="settings-field">
            <label>Email</label>
            <p className="settings-field-value">{meData?.email || meData?.username}</p>
          </div>
          <div className="settings-field">
            <label>名字</label>
            <input className="input" value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="名" />
          </div>
          <div className="settings-field">
            <label>姓氏</label>
            <input className="input" value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="姓" />
          </div>
          <button className="settings-save-btn" type="submit" disabled={saving}>
            {saving ? "儲存中…" : "儲存變更"}
          </button>
          {saveMsg && <p className="settings-msg">{saveMsg}</p>}
        </form>
      </section>

      <section className="settings-section">
        <h2 className="settings-section-title">登入方式</h2>
        <p className="settings-field-value">
          {isEmailAccount ? "Email 帳號" : "Google 帳號（透過 Google 管理密碼）"}
        </p>
      </section>

      {isEmailAccount && (
        <section className="settings-section">
          <h2 className="settings-section-title">更改密碼</h2>
          <form className="settings-form" onSubmit={handleChangePassword}>
            <input className="input" type="password" placeholder="目前密碼" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} autoComplete="current-password" />
            <input className="input" type="password" placeholder="新密碼（至少 8 字元）" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} autoComplete="new-password" />
            <input className="input" type="password" placeholder="確認新密碼" value={confirmPwd} onChange={(e) => setConfirmPwd(e.target.value)} autoComplete="new-password" />
            {pwdError && <p className="settings-error">{pwdError}</p>}
            <button className="settings-save-btn" type="submit">更新密碼</button>
          </form>
        </section>
      )}

      <section className="settings-section settings-danger-zone">
        <h2 className="settings-section-title danger">危險操作</h2>
        <p className="settings-danger-desc">刪除帳號將移除所有掃描紀錄與點數，此操作無法復原。</p>
        <button
          className="settings-danger-btn"
          type="button"
          onClick={() => {
            if (window.confirm("確定要刪除帳號嗎？此操作無法復原。")) {
              alert("請聯絡管理員協助刪除帳號。");
            }
          }}
        >
          刪除帳號
        </button>
      </section>
    </div>
  );
}

// ============================================================
// 公開頁面（PublicLayout + /project /team /purchase /download）
// 不需登入即可瀏覽，獨立 nav，PWA 真實可安裝。
// ============================================================

export {
  TopNav,
  DashboardPage,
  HistoryPage,
  BillingPage,
  ReviewsPage,
  SettingsPage,
};
