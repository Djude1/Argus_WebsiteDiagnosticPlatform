import { useState } from "react";

// AEO 問答檢測逐題結果（scan.aeo_report，後端 apps/scans/aeo/evaluate.py）。
// 每一題顯示判定與證據：可回答的題目附原文與位置；其他題目附理由與相關段落。
// 內容不足以出題時只顯示「未充分評估」與原因，不顯示分數。
// 用在網站專案的「AEO 問答」分頁（features/projects/ProjectPages.jsx 的 ProjectAeoPage）；
// withFilter 時可依判定篩選題目。
// 可回答與內容衝突的題目另附可信度（確認／可能／推測，後端 aeo/answers.py 的 confidence）與限制說明；
// 舊掃描沒有這兩個欄位就不顯示。

const VERDICT_FILTERS = [
  ["all", "全部"],
  ["answered", "可回答"],
  ["insufficient", "資訊不足"],
  ["conflict", "衝突"],
  ["missing", "無答案"],
];

const VERDICT_TONE = {
  answered: "is-good",
  insufficient: "is-warn",
  conflict: "is-bad",
  missing: "is-bad",
};

function percent(ratio) {
  return ratio == null ? "—" : `${Math.round(ratio * 100)}%`;
}

function AeoAnswerPanel({ report, withFilter = false }) {
  const [openKey, setOpenKey] = useState(null);
  const [verdict, setVerdict] = useState("all");
  if (!report || !report.status) return null;

  if (report.status !== "evaluated") {
    return (
      <section className="aeo-panel" aria-labelledby="aeo-panel-title">
        <h3 id="aeo-panel-title" className="aeo-panel-title">AEO 問答檢測</h3>
        <p className="aeo-panel-note">未充分評估：{report.reason}</p>
      </section>
    );
  }

  const counts = report.counts || {};
  const questions = (report.questions || []).filter((q) => verdict === "all" || q.verdict === verdict);
  return (
    <section className="aeo-panel" aria-labelledby={withFilter ? undefined : "aeo-panel-title"} aria-label={withFilter ? "逐題結果" : undefined}>
      {/* 分頁模式時，標題與數字已在頁首的數字列，不再重複 */}
      {!withFilter && <div className="aeo-panel-head">
        <div>
          <h3 id="aeo-panel-title" className="aeo-panel-title">AEO 問答檢測</h3>
          <p className="aeo-panel-note">
            依網站內容建立 {report.questions_total} 個問題，在已掃描頁面中找答案並附上原文。
            有答案的問題比例 {percent(report.answered_ratio)}，答案附有原文的比例 {percent(report.evidence_ratio)}
            {report.citation ? `，答案可被搜尋引擎與 AI 引用的比例 ${percent(report.citation.citable_ratio)}` : ""}。
          </p>
        </div>
        <dl className="aeo-panel-counts">
          <div className="is-good"><dt>可回答</dt><dd>{counts.answered ?? 0}</dd></div>
          <div className="is-warn"><dt>資訊不足</dt><dd>{counts.insufficient ?? 0}</dd></div>
          <div className="is-bad"><dt>衝突</dt><dd>{counts.conflict ?? 0}</dd></div>
          <div className="is-bad"><dt>無答案</dt><dd>{counts.missing ?? 0}</dd></div>
        </dl>
      </div>}
      {withFilter && (
        <div className="project-filter" role="group" aria-label="依判定篩選">
          <span className="project-filter-label">判定</span>
          {VERDICT_FILTERS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`project-chip ${verdict === key ? "active" : ""}`}
              aria-pressed={verdict === key}
              onClick={() => setVerdict(key)}
            >
              {label}
              {key !== "all" ? ` ${counts[key] ?? 0}` : ""}
            </button>
          ))}
        </div>
      )}
      {questions.length === 0 && <p className="aeo-panel-note">沒有符合的題目。</p>}
      <ul className="aeo-question-list">
        {questions.map((q) => {
          const key = `${q.key}-${q.text}`;
          const open = openKey === key;
          return (
            <li key={key} className="aeo-question">
              <button
                type="button"
                className="aeo-question-toggle"
                aria-expanded={open}
                onClick={() => setOpenKey(open ? null : key)}
              >
                <span className={`aeo-verdict ${VERDICT_TONE[q.verdict] || ""}`}>{q.verdict_label}</span>
                {q.confidence_label && (
                  <span className={`aeo-confidence is-${q.confidence}`}>可信度：{q.confidence_label}</span>
                )}
                {/* 引用可得性只標出有問題的（可被引用是常態，不逐題重複） */}
                {q.citation && q.citation.status !== "citable" && (
                  <span className={`aeo-citation is-${q.citation.status}`}>{q.citation.label}</span>
                )}
                <span className="aeo-question-text">{q.text}</span>
                <span className="aeo-question-more" aria-hidden="true">{open ? "收合" : "看證據"}</span>
              </button>
              {open && (
                <div className="aeo-question-body">
                  <p className="aeo-question-reason">{q.reason}</p>
                  {q.limitation && <p className="aeo-question-limit">判定限制：{q.limitation}</p>}
                  {q.citation && q.citation.reasons.length > 0 && (
                    <p className="aeo-question-limit">{q.citation.label}：{q.citation.reasons.join("；")}</p>
                  )}
                  {(q.evidence || []).length > 0 ? (
                    <ul className="aeo-evidence-list">
                      {q.evidence.map((e, i) => (
                        <li key={`${e.url}-${i}`}>
                          <a href={e.url} target="_blank" rel="noopener noreferrer">{e.url}</a>
                          <span className="aeo-evidence-loc">{e.location}</span>
                          <blockquote>{e.quote}</blockquote>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="aeo-panel-note">已掃描的頁面中沒有相關段落。</p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default AeoAnswerPanel;
export { AeoAnswerPanel };
