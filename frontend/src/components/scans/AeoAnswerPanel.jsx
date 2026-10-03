import { useState } from "react";

// AEO 問答檢測逐題結果（scan.aeo_report，後端 apps/scans/aeo/evaluate.py）。
// 每一題顯示判定與證據：可回答的題目附原文與位置；其他題目附理由與相關段落。
// 內容不足以出題時只顯示「未充分評估」與原因，不顯示分數。

const VERDICT_TONE = {
  answered: "is-good",
  insufficient: "is-warn",
  conflict: "is-bad",
  missing: "is-bad",
};

function percent(ratio) {
  return ratio == null ? "—" : `${Math.round(ratio * 100)}%`;
}

function AeoAnswerPanel({ report }) {
  const [openKey, setOpenKey] = useState(null);
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
  const questions = report.questions || [];
  return (
    <section className="aeo-panel" aria-labelledby="aeo-panel-title">
      <div className="aeo-panel-head">
        <div>
          <h3 id="aeo-panel-title" className="aeo-panel-title">AEO 問答檢測</h3>
          <p className="aeo-panel-note">
            依網站內容建立 {report.questions_total} 個問題，在已掃描頁面中找答案並附上原文。
            有答案的問題比例 {percent(report.answered_ratio)}，答案附有原文的比例 {percent(report.evidence_ratio)}。
          </p>
        </div>
        <dl className="aeo-panel-counts">
          <div className="is-good"><dt>可回答</dt><dd>{counts.answered ?? 0}</dd></div>
          <div className="is-warn"><dt>資訊不足</dt><dd>{counts.insufficient ?? 0}</dd></div>
          <div className="is-bad"><dt>衝突</dt><dd>{counts.conflict ?? 0}</dd></div>
          <div className="is-bad"><dt>無答案</dt><dd>{counts.missing ?? 0}</dd></div>
        </dl>
      </div>
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
                <span className="aeo-question-text">{q.text}</span>
                <span className="aeo-question-more" aria-hidden="true">{open ? "收合" : "看證據"}</span>
              </button>
              {open && (
                <div className="aeo-question-body">
                  <p className="aeo-question-reason">{q.reason}</p>
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
