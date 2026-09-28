// Dashboard 頁：依使用者要求恢復為 462848b（Night Watch 改版前）的版本。
// 樣式由 styles/legacy-member/ 提供，只在 App.jsx 的 .member-legacy 範圍內生效。
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges.jsx";
import {
  CATEGORY_COLOR,
  CATEGORY_LABELS,
  CountUp,
  SeverityBarChart,
  StackedBar,
} from "../../shared/AppShared.jsx";

// ============================================================
// Dashboard 頁
// ============================================================

function formatRelativeTime(isoString) {
  if (!isoString) return "";
  const elapsedSeconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (elapsedSeconds < 60) return "剛剛";
  if (elapsedSeconds < 3600) return `${Math.floor(elapsedSeconds / 60)} 分鐘前`;
  if (elapsedSeconds < 86400) return `${Math.floor(elapsedSeconds / 3600)} 小時前`;
  const elapsedDays = Math.floor(elapsedSeconds / 86400);
  if (elapsedDays < 30) return `${elapsedDays} 天前`;
  if (elapsedDays < 365) return `${Math.floor(elapsedDays / 30)} 個月前`;
  return `${Math.floor(elapsedDays / 365)} 年前`;
}

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
          hint={`≈ 還能掃 ${Math.floor((wallet?.balance || 0) / ((wallet?.coin_per_category || 2) * 5)).toLocaleString()} 頁（五維全選） · 累積花費 NT$ ${(wallet?.total_purchased_ntd || 0).toLocaleString()}`}
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

      {/* 版面重排：最常用的「最近掃描」放主欄，旁邊是各維度平均；圖表放到下方並排 */}
      <div className="dashboard-main">
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
              <li className="dashboard-empty">
                <p>還沒有掃描紀錄，從輸入網址開始第一次健檢。</p>
                <button type="button" className="primary-button" onClick={() => navigate("/scans")}>
                  建立第一個掃描
                </button>
              </li>
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

        <div className="panel dashboard-panel">
          <div className="dashboard-panel-header">
            <h3>各維度平均分</h3>
            <span className="hint-text-sm">基於完成的掃描</span>
          </div>
          <ul className="category-avg-list">
            {Object.keys(CATEGORY_LABELS).map((cat) => {
              const value = data.category_averages?.[cat];
              const has = value !== null && value !== undefined;
              const tone = !has ? "muted" : value >= 80 ? "good" : value >= 60 ? "medium" : "bad";
              return (
                <li className="category-avg-row" key={cat}>
                  <span className={`category-pill cat-${cat}`}>{CATEGORY_LABELS[cat]}</span>
                  <span className="category-avg-track" aria-hidden="true">
                    <span className={`category-avg-fill tone-${tone}`} style={{ width: `${has ? value : 0}%` }} />
                  </span>
                  <span className={`category-avg-value tone-${tone}`}>{has ? Math.round(value) : "—"}</span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      <div className="dashboard-charts">
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
      </div>
      <AnnouncementToast announcements={toasts} onDismiss={handleDismiss} />
    </div>
  );
}


export { DashboardPage };
