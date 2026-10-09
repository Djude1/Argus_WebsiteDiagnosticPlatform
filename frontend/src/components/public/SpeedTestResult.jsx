/**
 * 快速檢查頁「網站測速」結果（2026-10-09 重排，比照會員頁效能分頁）：
 * 第一塊是 Argus 單次輕量量測（分數＋等級文字、指標、發現的問題），
 * 下方是 Google PageSpeed Insights（PageSpeedResult：Lighthouse 實驗室量測與 CrUX 真實使用者兩塊）。
 */
import PageSpeedResult from "./PageSpeedResult.jsx";

const GRADE = {
  good: { tone: "good", label: "良好" },
  needs_work: { tone: "warn", label: "需改善" },
  poor: { tone: "bad", label: "不佳" },
};
const SEVERITY = { high: "高", medium: "中", low: "低" };

export default function SpeedTestResult({ result }) {
  const grade = GRADE[result.grade] || GRADE.needs_work;
  const m = result.metrics || {};
  const metrics = [
    ["伺服器回應（TTFB）", `${m.ttfb_ms} 毫秒`],
    ["HTML 傳輸量", `${m.transfer_kb} KB`],
    ["阻塞渲染的 script", `${m.blocking_scripts} / ${m.scripts} 個`],
    ["延遲載入的圖片", `${m.lazy_images} / ${m.images} 張`],
    ["樣式表", `${m.stylesheets} 個`],
    ["第三方網域", `${m.third_party_hosts} 個`],
  ];
  return (
    <div className="speed-results">
      <section className="speed-panel">
        <header className="speed-panel-head">
          <h3>Argus 快速測速</h3>
          <span className="speed-tag">單次輕量量測</span>
        </header>
        <div className="speed-summary">
          <div className={`speed-grade is-${grade.tone}`}>
            <strong>{result.score}</strong>
            <span>{grade.label}</span>
          </div>
          <div className="speed-summary-text">
            <p className="speed-url">{result.final_url || result.url}</p>
            <p className="speed-lead">{result.core_web_vitals_note}</p>
          </div>
        </div>
        <dl className="speed-metrics">
          {metrics.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <h4 className="speed-subtitle">發現的問題</h4>
        {result.findings?.length > 0 ? (
          <ul className="speed-findings">
            {result.findings.map((f, idx) => (
              <li key={`${f.title}-${idx}`}>
                <span className={`speed-sev is-${f.severity || "low"}`}>{SEVERITY[f.severity] || "低"}</span>
                <span className="speed-finding-text">
                  <strong>{f.title}</strong>
                  <span>{f.description}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="speed-lead">沒有發現明顯的效能風險。</p>
        )}
      </section>
      <PageSpeedResult pagespeed={result.pagespeed} />
    </div>
  );
}
