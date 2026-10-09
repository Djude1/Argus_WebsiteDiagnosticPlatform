/**
 * 快速檢查頁「網站測速」的 Google PageSpeed Insights 結果（2026-10-09）。
 * 後端 speed-test 會回 `pagespeed`：unavailable（平台沒設金鑰，不顯示）／pending（附 job，背景量測中）／
 * done（附 report，格式同 ScanJob.performance_report）／failed（附 reason）。
 * pending 時每 3 秒輪詢 `/insights/speed-test/pagespeed/<job>/`，最多 2.5 分鐘。
 */
import { useEffect, useState } from "react";

import { api } from "../../api";

const POLL_MS = 3000;
const MAX_POLLS = 50;

const SCORE_LABELS = [
  ["performance", "效能"],
  ["accessibility", "無障礙"],
  ["best-practices", "最佳做法"],
  ["seo", "SEO"],
];

function scoreTone(score) {
  if (score >= 90) return "good";
  if (score >= 50) return "warn";
  return "bad";
}

function formatField(name, value) {
  if (name === "CLS") return value.toFixed(2);
  return value >= 1000 ? `${(value / 1000).toFixed(1)} 秒` : `${value} 毫秒`;
}

function usePageSpeed(initial) {
  const [state, setState] = useState(initial);
  useEffect(() => {
    setState(initial);
    if (initial?.status !== "pending" || !initial.job) return undefined;
    let polls = 0;
    let cancelled = false;
    let timer;
    const poll = async () => {
      polls += 1;
      try {
        const res = await api.get(`/insights/speed-test/pagespeed/${initial.job}/`);
        if (cancelled) return;
        if (res.data.status !== "pending") {
          setState(res.data);
          return;
        }
      } catch {
        if (cancelled) return;
        setState({ status: "failed", reason: "無法取得 Google 量測結果，請重新測速。" });
        return;
      }
      if (polls >= MAX_POLLS) {
        setState({ status: "failed", reason: "Google 量測逾時，請稍後再測一次。" });
        return;
      }
      timer = setTimeout(poll, POLL_MS);
    };
    timer = setTimeout(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [initial]);
  return state;
}

const FIELD_TONE = { FAST: "good", AVERAGE: "warn", SLOW: "bad" };

export default function PageSpeedResult({ pagespeed }) {
  const state = usePageSpeed(pagespeed);
  if (!state || state.status === "unavailable") return null;
  if (state.status === "done") return <PageSpeedReport report={state.report} cached={state.cached} />;
  return (
    <section className="speed-panel speed-panel-wide" aria-live="polite">
      <header className="speed-panel-head">
        <h3>Google PageSpeed Insights</h3>
        <span className="speed-tag">行動版</span>
      </header>
      {state.status === "pending" ? (
        <p className="speed-pending">
          <span className="speed-spinner" aria-hidden="true" />
          Google 正在量測，約需 20～60 秒，結果出來會自動顯示。
        </p>
      ) : (
        <p className="speed-lead">這次沒有取得 Google 量測結果：{state.reason || "原因不明"}</p>
      )}
    </section>
  );
}

function PageSpeedReport({ report, cached }) {
  const lab = report?.lab || {};
  const field = report?.field || {};
  const scores = lab.scores || {};
  const metrics = Object.values(lab.metrics || {});
  const fieldMetrics = Object.entries(field.metrics || {});
  return (
    <>
      <section className="speed-panel" aria-live="polite">
        <header className="speed-panel-head">
          <h3>Lighthouse 實驗室量測</h3>
          <span className="speed-tag">Google PageSpeed Insights・行動版</span>
        </header>
        <p className="speed-lead">
          Google 以模擬行動裝置量測一次（Lighthouse {lab.version || ""}），數值會隨網路與伺服器狀況浮動。
          {cached && "10 分鐘內測過同一網址，沿用上次結果。"}
        </p>
        {lab.error ? (
          <p className="speed-lead">Lighthouse 無法完成量測（{lab.error}）。</p>
        ) : (
          <ul className="speed-scores">
            {SCORE_LABELS.filter(([key]) => scores[key] != null).map(([key, label]) => (
              <li key={key} className={`speed-score is-${scoreTone(scores[key])}`}>
                <strong>{scores[key]}</strong>
                <span>{label}</span>
              </li>
            ))}
          </ul>
        )}
        {metrics.length > 0 && (
          <dl className="speed-metrics">
            {metrics.map((metric) => (
              <div key={metric.label}>
                <dt>{metric.label}</dt>
                <dd>{metric.display || "—"}</dd>
              </div>
            ))}
          </dl>
        )}
        {lab.opportunities?.length > 0 && (
          <>
            <h4 className="speed-subtitle">最值得改善的項目</h4>
            <ul className="speed-opportunities">
              {lab.opportunities.map((item) => (
                <li key={item.id}>
                  <span>{item.title}</span>
                  {item.display && <span className="speed-muted">{item.display}</span>}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section className="speed-panel">
        <header className="speed-panel-head">
          <h3>真實使用者體驗</h3>
          <span className="speed-tag">Chrome CrUX</span>
        </header>
        {fieldMetrics.length > 0 ? (
          <>
            <p className="speed-lead">
              Chrome 使用者過去 28 天的實際體驗（第 75 百分位）。
              {field.scope === "origin" && "這個網址的資料不足，以下是整個網站的資料。"}
            </p>
            <dl className="speed-metrics is-field">
              {fieldMetrics.map(([name, item]) => (
                <div key={name} className={`is-${FIELD_TONE[item.category] || "none"}`}>
                  <dt>{name}</dt>
                  <dd>
                    {formatField(name, item.p75)}
                    {item.category_label && <span className="speed-muted">{item.category_label}</span>}
                  </dd>
                </div>
              ))}
            </dl>
          </>
        ) : (
          <p className="speed-lead">{field.reason || "這個網站的真實使用者資料不足。"}</p>
        )}
      </section>
    </>
  );
}
