// History 頁：依使用者要求恢復為 462848b（Night Watch 改版前）的版本。
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges.jsx";
import { LineChart } from "../../shared/AppShared.jsx";

// ============================================================
// History 頁（同網址歷次分數）
// ============================================================

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

export { HistoryPage };
