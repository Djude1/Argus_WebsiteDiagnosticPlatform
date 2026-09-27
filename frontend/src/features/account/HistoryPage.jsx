import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { IrisScore } from "../../components/brand/IrisScore";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges";
import { LineChart } from "../../shared/AppShared";
import { PlusIcon } from "../../shared/ActionIcons";
import { formatDateTime } from "../../shared/formatters";
import { AccountEmpty, AccountError, AccountSkeleton } from "./AccountStates";

const SHORT_DATE = new Intl.DateTimeFormat("zh-Hant", { month: "numeric", day: "numeric" });

function deltaMeta(delta) {
  if (delta === null || delta === undefined) return null;
  if (delta > 0) return { tone: "good", text: `▲ +${delta}`, label: `比上次進步 ${delta} 分` };
  if (delta < 0) return { tone: "bad", text: `▼ ${delta}`, label: `比上次退步 ${Math.abs(delta)} 分` };
  return { tone: "neutral", text: "持平", label: "與上次相同" };
}

// ============================================================
// History 頁（同網址歷次分數）
// ============================================================

function HistoryPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError("");
    api
      .get("/history/")
      .then((r) => !cancelled && setData(r.data))
      .catch(() => !cancelled && setError("無法載入歷史資料。"));
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  if (error) return <AccountError message={error} onRetry={() => setReloadKey((k) => k + 1)} />;
  if (!data) return <AccountSkeleton label="載入歷史紀錄中…" tiles={0} blocks={2} />;

  const totalScans = data.origins.reduce((sum, o) => sum + (o.total_scans || 0), 0);

  return (
    <div className="acct-page">
      <header className="acct-page-head">
        <div>
          <p className="ag-eyebrow">History</p>
          <h1 className="acct-page-title">同網址分數歷史</h1>
          <p className="acct-page-sub">每個網站的歷次健檢與分數走勢，看出修正是否見效。</p>
        </div>
        {data.origins.length > 0 && (
          <dl className="acct-page-meta">
            <div><dt>網站</dt><dd className="ag-num">{data.origins.length}</dd></div>
            <div><dt>健檢次數</dt><dd className="ag-num">{totalScans}</dd></div>
          </dl>
        )}
      </header>

      {data.origins.length === 0 ? (
        <AccountEmpty
          title="尚無紀錄"
          action={(
            <button type="button" className="primary-button" onClick={() => navigate("/scans")}>
              <PlusIcon className="acct-btn-icon" /> 開始第一次掃描
            </button>
          )}
        >
          <p>完成第一次掃描後，這裡會依網址整理每次的分數，重掃就能看見進步幅度。</p>
        </AccountEmpty>
      ) : (
        <div className="hist-grid">
          {data.origins.map((origin) => {
            const chronological = origin.scans
              .filter((s) => s.overall_score !== null && s.overall_score !== undefined)
              .slice()
              .reverse();
            const chartData = chronological.map((s) => ({
              label: SHORT_DATE.format(new Date(s.created_at)),
              value: s.overall_score,
            }));
            const delta = deltaMeta(origin.delta);
            return (
              <article key={origin.origin} className="hist-card">
                <header className="hist-card-head">
                  <IrisScore score={origin.latest_score} size={64} />
                  <div className="hist-card-id">
                    <h2 className="hist-origin" title={origin.origin}>{origin.origin}</h2>
                    <p className="hist-card-meta">
                      共 {origin.total_scans} 次健檢
                      {delta && (
                        <span className={`hist-delta tone-${delta.tone}`} aria-label={delta.label}>
                          {delta.text}
                        </span>
                      )}
                    </p>
                  </div>
                </header>
                {chartData.length > 0 && (
                  <div className="hist-chart">
                    <LineChart data={chartData} ariaLabel={`${origin.origin} 分數趨勢`} />
                  </div>
                )}
                <ul className="hist-list">
                  {origin.scans.slice(0, 5).map((s, idx) => (
                    <li key={s.id}>
                      <button
                        className={`hist-row ${idx === 0 ? "is-latest" : ""}`}
                        type="button"
                        onClick={() => navigate(`/scans/${s.id}`)}
                      >
                        <span className="hist-row-time">
                          {idx === 0 && <span className="hist-latest-chip">最新</span>}
                          <span className="ag-num">{formatDateTime(s.created_at)}</span>
                        </span>
                        <ScanStatusBadge status={s.status} />
                        <ScoreBadge score={s.overall_score} />
                      </button>
                    </li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default HistoryPage;
export { HistoryPage };
