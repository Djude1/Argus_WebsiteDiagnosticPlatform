/**
 * 快速檢查頁「單頁檢查」結果（2026-10-09 重排，與網站測速同一套版面）：
 * 第一塊是總分＋等級文字與三個面向分數，第二塊是依嚴重度排序的問題，最後是完整掃描的導流。
 */
const GRADE = {
  good: { tone: "good", label: "良好" },
  needs_work: { tone: "warn", label: "需改善" },
  poor: { tone: "bad", label: "不佳" },
};
const SEVERITY = { high: "高", medium: "中", low: "低" };
const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 };
const CATEGORY = { seo: "SEO", security: "資安", aeo_geo: "AEO/GEO" };

function scoreTone(score) {
  if (score >= 85) return "good";
  if (score >= 60) return "warn";
  return "bad";
}

export default function QuickScanResult({ result, onFullScan }) {
  const grade = GRADE[result.grade] || GRADE.needs_work;
  const findings = [...(result.findings || [])].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3),
  );
  return (
    <div className="speed-results">
      <section className="speed-panel">
        <header className="speed-panel-head">
          <h3>單頁快速檢查</h3>
          <span className="speed-tag">只檢查這一頁</span>
        </header>
        <div className="speed-summary">
          <div className={`speed-grade is-${grade.tone}`}>
            <strong>{result.overall_score}</strong>
            <span>{grade.label}</span>
          </div>
          <div className="speed-summary-text">
            <p className="speed-url">{result.final_url || result.url}</p>
            <p className="speed-lead">{result.note}</p>
          </div>
        </div>
        <ul className="speed-scores is-three">
          {(result.categories || []).map((c) => (
            <li key={c.key} className={`speed-score is-${scoreTone(c.score)}`}>
              <strong>{c.score}</strong>
              <span>{c.label}</span>
            </li>
          ))}
        </ul>
        <h4 className="speed-subtitle">發現的問題（{findings.length}）</h4>
        {findings.length > 0 ? (
          <ul className="speed-findings">
            {findings.map((f, idx) => (
              <li key={`${f.title}-${idx}`}>
                <span className={`speed-sev is-${f.severity || "low"}`}>{SEVERITY[f.severity] || "低"}</span>
                <span className="speed-finding-text">
                  <strong>
                    {f.title}
                    {CATEGORY[f.category] && <span className="speed-cat">{CATEGORY[f.category]}</span>}
                  </strong>
                  <span>{f.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="speed-lead">這一頁沒有發現明顯問題。</p>
        )}
      </section>
      <section className="speed-panel speed-panel-wide speed-upsell">
        <div>
          <h3>完整掃描看得更完整</h3>
          <p className="speed-lead">
            整站爬取與逐頁截圖、五個面向的問題與修正順序、防偽 PDF 報告，
            還能針對單一頁面產出優化後的版本；註冊後第一次完整掃描免費。
          </p>
        </div>
        <button type="button" className="public-cta-primary" onClick={onFullScan}>
          登入建立完整掃描
        </button>
      </section>
    </div>
  );
}
