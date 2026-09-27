import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { IrisScore } from "../../components/brand/IrisScore";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges";
import { useArgusStore } from "../../store";
import {
  CATEGORY_COLOR,
  CATEGORY_LABELS,
  CountUp,
  SeverityBarChart,
  StackedBar,
} from "../../shared/AppShared";
import { ArrowRightIcon, CloseIcon, PlusIcon } from "../../shared/ActionIcons";
import { formatRelative } from "../../shared/formatters";
import { ChartIcon, CoinIcon, FlagIcon, GlobeIcon, MagnifierIcon, ScoreIcon } from "../../shared/LineIcons";
import { AccountError, AccountSkeleton } from "./AccountStates";

function greeting() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 11) return "早安";
  if (hour >= 11 && hour < 18) return "午安";
  return "晚安";
}

function StatTile({ label, value, hint, tone = "neutral", Icon, onClick, actionLabel }) {
  const inner = (
    <>
      <span className="dash-stat-head">
        <span className="dash-stat-label">{label}</span>
        {Icon && <span className="dash-stat-icon" aria-hidden="true"><Icon /></span>}
      </span>
      <span className="dash-stat-value ag-num"><CountUp value={value} /></span>
      {hint && <span className="dash-stat-hint">{hint}</span>}
      {onClick && actionLabel && (
        <span className="dash-stat-action">{actionLabel} <ArrowRightIcon /></span>
      )}
    </>
  );
  if (onClick) {
    return (
      <button type="button" className={`dash-stat tone-${tone} is-clickable`} onClick={onClick}>
        {inner}
      </button>
    );
  }
  return <div className={`dash-stat tone-${tone}`}>{inner}</div>;
}

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
    <div className="dash-toast-stack" role="status" aria-live="polite">
      {announcements.map((ann) => (
        <div
          key={ann.id}
          className="dash-toast"
          onMouseEnter={() => setHovering((h) => ({ ...h, [ann.id]: true }))}
          onMouseLeave={() => setHovering((h) => ({ ...h, [ann.id]: false }))}
        >
          <span className="dash-toast-dot" aria-hidden="true" />
          <div className="dash-toast-body">
            <div className="dash-toast-title">{ann.title}</div>
            <div className="dash-toast-content">{ann.content.slice(0, 100)}{ann.content.length > 100 ? "…" : ""}</div>
          </div>
          <button
            type="button"
            className="dash-toast-close"
            onClick={() => onDismiss(ann.id)}
            aria-label="關閉公告"
          >
            <CloseIcon />
          </button>
        </div>
      ))}
    </div>
  );
}

const ONBOARDING_STEPS = [
  {
    Icon: GlobeIcon,
    title: "輸入要健檢的網址",
    body: "貼上首頁網址即可；要跑主動式資安測試時，再到「網域驗證」證明所有權。",
  },
  {
    Icon: FlagIcon,
    title: "選擇維度與頁數",
    body: "SEO、AEO、GEO、資安、UX 五個維度可自由組合，送出前會先估算所需點數。",
  },
  {
    Icon: ScoreIcon,
    title: "取得報告與修法",
    body: "每個問題附證據截圖與可直接套用的修正內容，重掃即可追蹤分數變化。",
  },
];

function FirstScanGuide({ onStart }) {
  return (
    <section className="dash-onboard ag-viewfinder" aria-labelledby="dash-onboard-title">
      <div className="dash-onboard-head">
        <p className="ag-eyebrow">第一次使用</p>
        <h2 id="dash-onboard-title">三步驟完成第一次網站健檢</h2>
        <p>Argus 會像百眼巨人一樣逐頁巡視你的網站，找出問題並直接給出修法。</p>
      </div>
      <ol className="dash-onboard-steps">
        {ONBOARDING_STEPS.map((step, index) => (
          <li key={step.title} className="dash-onboard-step">
            <span className="dash-onboard-index ag-num" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <span className="dash-onboard-icon" aria-hidden="true"><step.Icon /></span>
            <h3>{step.title}</h3>
            <p>{step.body}</p>
          </li>
        ))}
      </ol>
      <button type="button" className="primary-button dash-cta" onClick={onStart}>
        <PlusIcon className="acct-btn-icon" /> 開始第一次掃描
      </button>
    </section>
  );
}

function DashboardPage() {
  const navigate = useNavigate();
  const me = useArgusStore((s) => s.me);
  const [data, setData] = useState(null);
  const [categoriesData, setCategoriesData] = useState(null);
  const [error, setError] = useState("");
  const [toasts, setToasts] = useState([]);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError("");
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
  }, [reloadKey]);

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
    return <AccountError message={error} onRetry={() => setReloadKey((k) => k + 1)} />;
  }
  if (!data) {
    return <AccountSkeleton label="載入 Dashboard 中…" />;
  }

  const { wallet } = data;
  const balance = wallet?.balance || 0;
  const totalFindings = Object.values(data.severity_totals || {}).reduce(
    (sum, n) => sum + n,
    0,
  );
  const highRisk = (data.severity_totals?.critical || 0) + (data.severity_totals?.high || 0);
  const pagesLeft = Math.floor(balance / ((wallet?.coin_per_category || 2) * 5));
  const isNewUser = data.total_scans === 0;
  const name = me?.first_name?.trim() || me?.display_name?.trim() || "";

  return (
    <div className="dash">
      <section className="dash-hero ag-surface-grid" aria-labelledby="dash-hero-title">
        <div className="dash-hero-copy">
          <p className="ag-eyebrow">總覽 · Overview</p>
          <h1 id="dash-hero-title" className="dash-hero-title">
            {greeting()}{name ? `，${name}` : ""}
          </h1>
          <p className="dash-hero-sub">
            {isNewUser ? (
              "帳號已就緒，從第一次掃描開始，讓 Argus 替你守望網站。"
            ) : (
              <>
                你已執行 <strong className="ag-num">{data.total_scans}</strong> 次健檢・完成{" "}
                <strong className="ag-num">{data.completed_scans}</strong>・失敗{" "}
                <strong className="ag-num">{data.failed_scans}</strong>
                {highRisk > 0 && (
                  <>
                    ・<span className="dash-hero-flag">{highRisk} 個高風險問題待處理</span>
                  </>
                )}
              </>
            )}
          </p>
          <div className="dash-hero-actions">
            <button type="button" className="primary-button dash-cta" onClick={() => navigate("/scans")}>
              <PlusIcon className="acct-btn-icon" /> 開始新掃描
            </button>
            <button type="button" className="secondary-button" onClick={() => navigate("/history")}>
              查看歷史
            </button>
          </div>
        </div>
        <div className="dash-hero-score">
          <IrisScore score={data.average_score} size={148} caption="平均分" />
          <p className="dash-hero-score-label">整體平均 IrisScore</p>
          <p className="dash-hero-score-hint">基於 {data.completed_scans} 次完成的掃描</p>
        </div>
      </section>

      <div className="dash-stats">
        <StatTile
          label="掃描總數"
          value={data.total_scans}
          hint="所有狀態合計"
          tone="primary"
          Icon={MagnifierIcon}
        />
        <StatTile
          label="點數餘額"
          value={balance}
          hint={`≈ 還能掃 ${pagesLeft.toLocaleString()} 頁（五維全選）・累積花費 NT$ ${(wallet?.total_purchased_ntd || 0).toLocaleString()}`}
          tone="accent"
          Icon={CoinIcon}
          onClick={() => navigate("/billing")}
          actionLabel="前往購點"
        />
        <StatTile
          label="累計 Findings"
          value={totalFindings}
          hint="跨所有完成掃描"
          tone="info"
          Icon={ChartIcon}
        />
        <StatTile
          label="高／嚴重"
          value={highRisk}
          hint="critical + high"
          tone="bad"
          Icon={FlagIcon}
          onClick={() => navigate("/scans")}
          actionLabel="點看清單"
        />
      </div>

      {isNewUser ? (
        <FirstScanGuide onStart={() => navigate("/scans")} />
      ) : (
        <div className="dash-main">
          <section className="panel dash-panel dash-recent" aria-labelledby="dash-recent-title">
            <header className="dash-panel-head">
              <div>
                <h2 id="dash-recent-title">最近掃描</h2>
                <p>點任一列查看完整報告</p>
              </div>
              <button className="ghost-button" type="button" onClick={() => navigate("/scans")}>
                前往掃描頁 <ArrowRightIcon className="acct-btn-icon" />
              </button>
            </header>
            {data.recent_scans.length === 0 ? (
              <p className="dash-empty-line">尚無掃描紀錄。</p>
            ) : (
              <ul className="dash-recent-list">
                {data.recent_scans.map((scan) => (
                  <li key={scan.id}>
                    <button
                      className="dash-recent-row"
                      type="button"
                      onClick={() => navigate(`/scans/${scan.id}`)}
                    >
                      <span className="dash-recent-main">
                        <span className="dash-recent-origin">{scan.origin}</span>
                        <span className="dash-recent-time">{formatRelative(scan.completed_at || scan.created_at)}</span>
                      </span>
                      <ScanStatusBadge status={scan.status} />
                      <ScoreBadge score={scan.overall_score} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel dash-panel" aria-labelledby="dash-sev-title">
            <header className="dash-panel-head">
              <div>
                <h2 id="dash-sev-title">Findings 嚴重度分佈</h2>
                <p>跨所有掃描</p>
              </div>
            </header>
            <SeverityBarChart severityTotals={data.severity_totals} title="" />
          </section>

          <section className="panel dash-panel dash-wide" aria-labelledby="dash-cat-title">
            <header className="dash-panel-head">
              <div>
                <h2 id="dash-cat-title">五個維度</h2>
                <p>各維度平均分數（基於完成的掃描）與問題佔比</p>
              </div>
            </header>
            <div className="dash-cat-rings">
              {Object.keys(CATEGORY_LABELS).map((cat) => (
                <div className="dash-cat-item" key={cat}>
                  <IrisScore score={data.category_averages?.[cat] ?? null} size={84} />
                  <span className={`category-pill cat-${cat}`}>{CATEGORY_LABELS[cat]}</span>
                </div>
              ))}
            </div>
            <div className="dash-cat-share">
              <p className="dash-cat-share-label">問題佔比：哪一類最多</p>
              <StackedBar
                data={Object.keys(CATEGORY_LABELS).map((cat) => ({
                  label: CATEGORY_LABELS[cat],
                  value: categoriesData?.categories?.[cat]?.total_findings || 0,
                  color: CATEGORY_COLOR[cat],
                }))}
              />
            </div>
          </section>
        </div>
      )}
      <AnnouncementToast announcements={toasts} onDismiss={handleDismiss} />
    </div>
  );
}

export default DashboardPage;
export { DashboardPage };
