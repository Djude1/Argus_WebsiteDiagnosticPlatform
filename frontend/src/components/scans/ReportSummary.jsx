import {
  CATEGORY_COLOR,
  CATEGORY_LABELS,
  SEVERITY_LABEL,
  SeverityBarChart,
  StackedBar,
} from "../../shared/AppShared.jsx";

/**
 * 報告摘要：嚴重度分佈、類別佔比、Top Actions（最先處理的幾件事）。
 * 計數一律用後端 finding-stats 的真實數字（呼叫端已處理 fallback）。
 */
function ReportSummary({ severityTotals, categoryTotals, topActions, inProgress, showCharts, onSelectAction }) {
  const actions = (topActions || []).slice(0, 5);
  return (
    <section className="report-summary" aria-label="報告摘要">
      {showCharts && (
        <>
          <div className="panel report-summary-card">
            <SeverityBarChart severityTotals={severityTotals} title="嚴重度分佈" />
            {inProgress && <p className="report-summary-note">掃描進行中，數字為目前已發現的部分結果</p>}
          </div>
          <div className="panel report-summary-card">
            {/* 標題要講清楚在數什麼。這裡數的是原始筆數：同一個問題出現在 37 個
                頁面就算 37 筆，與下方 finding 清單對得上。報告裡的同名圖數的是
                合併重複後的項目數，兩個數字都對、但回答的是不同問題，沒標註就會
                讓人以為其中一邊算錯了。 */}
            <div className="bar-chart-header">
              <h4 className="bar-chart-header-h4">類別佔比</h4>
            </div>
            <p className="report-summary-note">依原始筆數計算（同一問題出現在多個頁面會分別計入）</p>
            <StackedBar
              data={Object.keys(CATEGORY_LABELS).map((cat) => ({
                label: CATEGORY_LABELS[cat],
                value: categoryTotals[cat] || 0,
                color: CATEGORY_COLOR[cat],
              }))}
            />
          </div>
        </>
      )}
      <div className="panel report-summary-card report-actions">
        <div className="bar-chart-header">
          <h4 className="bar-chart-header-h4">
            {actions.length ? `最先處理的 ${actions.length} 件事` : "最先處理的事"}
          </h4>
          <span className="report-actions-tag">Top Actions</span>
        </div>
        {actions.length ? (
          <ol className="report-actions-list">
            {actions.map((action, idx) => (
              <li key={`${action.category}-${action.title}-${idx}`}>
                <button className="top-action-row" type="button" onClick={() => onSelectAction(action)}>
                  <span className="top-action-rank ag-num">{idx + 1}</span>
                  <span className="top-action-body">
                    <span className="top-action-title">{action.title}</span>
                    <span className="top-action-meta">
                      <span className={`severity ${action.severity}`}>
                        {SEVERITY_LABEL[action.severity] || action.severity}
                      </span>
                      <span className={`category-pill cat-${action.category}`}>
                        {(CATEGORY_LABELS[action.category] || action.category).toUpperCase()}
                      </span>
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p className="report-summary-empty">
            {inProgress ? "掃描完成後，這裡會列出最值得先修的項目。" : "這次掃描沒有需要優先處理的項目。"}
          </p>
        )}
      </div>
    </section>
  );
}

export default ReportSummary;
