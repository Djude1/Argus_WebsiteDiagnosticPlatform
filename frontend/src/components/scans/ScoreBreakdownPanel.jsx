// 掃描頁「分數說明」分頁（後端 /api/scans/:id/score-breakdown/，apps/scans/score_explain.py）。
// 每個維度：基準分、逐項扣分（同一問題在多頁出現只扣一次）、只修好該項時的分數、不扣分的項目與未完整完成的檢查。

import { scoreGrade, scoreTone } from "../projects/DashboardWidgets";

const CATEGORY_LABELS = { seo: "SEO", aeo: "AEO", geo: "GEO", security: "資安", ux: "UX" };
const SEVERITY_LABELS = { critical: "嚴重", high: "高", medium: "中", low: "低", info: "資訊" };
const WEIGHT_ORDER = ["critical", "high", "medium", "low", "info"];

function CategoryBreakdown({ entry, decay }) {
  const label = CATEGORY_LABELS[entry.category] || entry.category;
  const tone = scoreTone(entry.score);
  return (
    <section className="panel score-explain-block">
      <header className="score-explain-head">
        <h2 className="score-explain-title">{label}</h2>
        <p className={`score-explain-score is-${tone}`}>
          <b>{entry.score}</b> 分 · {scoreGrade(entry.score)}
        </p>
        {entry.coverage === "partial" && <span className="score-explain-tag">部分評估</span>}
      </header>
      <p className="score-explain-formula">
        {entry.base_source === "aeo_answerability"
          ? `基準分 ${entry.base}（AEO 問答檢測的可回答性分數）`
          : `基準分 ${entry.base}`}
        {entry.penalty > 0
          ? `，扣分權重合計 ${entry.penalty}：${entry.base} × e^(−${entry.penalty}／${decay}) ≈ ${entry.recomputed_score} 分`
          : "，沒有扣分項目"}
      </p>
      {entry.deductions.length > 0 && (
        <div className="score-explain-table-wrap">
          <table className="score-explain-table">
            <thead>
              <tr>
                <th scope="col">扣分項目</th>
                <th scope="col">嚴重度</th>
                <th scope="col">權重</th>
                <th scope="col">出現</th>
                <th scope="col">只修好這項</th>
              </tr>
            </thead>
            <tbody>
              {entry.deductions.map((item) => (
                <tr key={item.rule_id || item.title}>
                  <td>{item.title}</td>
                  <td><span className={`project-sev sev-${item.severity}`}>{SEVERITY_LABELS[item.severity] || item.severity}</span></td>
                  <td>{item.weight}</td>
                  <td>{item.occurrences > 1 ? `${item.occurrences} 處` : "1 處"}</td>
                  <td>{item.score_without} 分</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ul className="score-explain-notes">
        {entry.in_base > 0 && <li>另有 {entry.in_base} 筆逐題問答結果已反映在基準分，不重複扣分。</li>}
        {entry.info > 0 && <li>{entry.info} 筆資訊類項目不扣分。</li>}
        {entry.incomplete_checks.length > 0 && (
          <li>沒有完整完成的檢查：{entry.incomplete_checks.join("、")}。沒有發現問題不代表沒有問題。</li>
        )}
      </ul>
    </section>
  );
}

function ScoreBreakdownPanel({ data }) {
  if (!data?.available || !data.categories.length) {
    return (
      <section className="panel">
        <p className="hint-text">掃描完成並計分後，這裡會說明每個維度的分數怎麼算出來。</p>
      </section>
    );
  }
  return (
    <div className="score-explain">
      <section className="panel score-explain-block">
        <h2 className="score-explain-title">分數怎麼算</h2>
        <p className="score-explain-formula">
          網站分數 {data.overall_score} 分＝下列 {data.categories.length} 個維度分數的平均。每個維度從基準分開始，
          依問題嚴重度累計扣分權重，分數＝基準分 × e^(−權重合計／{data.decay_constant})，
          所以修好嚴重的問題分數回升最多。
        </p>
        <ul className="score-explain-weights">
          {WEIGHT_ORDER.map((severity) => (
            <li key={severity}>
              <span className={`project-sev sev-${severity}`}>{SEVERITY_LABELS[severity]}</span>
              權重 {data.weights[severity] ?? 0}
            </li>
          ))}
        </ul>
        <p className="hint-text">
          同一個問題出現在多個頁面只扣一次（出現次數代表範圍，不是嚴重度）。外部指標（Lighthouse、真實使用者體驗、
          安全標頭等第）不計入這個分數。
        </p>
        {!data.matches && (
          <p className="score-explain-warning" role="status">
            這次掃描的分數是用較早版本的計分規則算的，下面依目前規則說明，數字可能和顯示的分數略有不同。
          </p>
        )}
      </section>
      {data.categories.map((entry) => (
        <CategoryBreakdown key={entry.category} entry={entry} decay={data.decay_constant} />
      ))}
    </div>
  );
}

export { ScoreBreakdownPanel };
