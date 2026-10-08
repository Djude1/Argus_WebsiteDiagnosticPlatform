// 掃描頁「效能」分頁（後端 ScanJob.performance_report，apps/scans/pagespeed.py）。
// Lighthouse＝Google 機房單次實驗室量測；CrUX＝Chrome 使用者過去 28 天的真實體驗。
// 兩者都是外部指標，不計入 Argus 分數，畫面上必須分開呈現並標示來源。

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

const FIELD_TONE = { FAST: "good", AVERAGE: "warn", SLOW: "bad" };

/** 沒有效能量測時說明原因：沒勾使用體驗、平台尚未設定金鑰，或量測失敗（後端 coverage.checks.pagespeed）。 */
function missingReason(categories, check) {
  if (categories && !categories.includes("ux")) {
    return "這次掃描沒有勾選「使用體驗」面向，所以沒有量測首頁效能。";
  }
  if (check?.status === "skipped") {
    return "平台尚未設定 Google PageSpeed Insights，所以這次沒有量測首頁效能。這是平台端的設定，需要由平台管理員設定 API 金鑰後才會量測，與你勾選的面向無關。";
  }
  if (check?.status === "failed") {
    return `這次的效能量測沒有成功（${check.reason || "原因不明"}），下次掃描會再量測。`;
  }
  return "這次掃描沒有效能量測。勾選「使用體驗」面向且平台已設定 Google PageSpeed Insights 時，會量測首頁的 Lighthouse 分數與真實使用者體驗。";
}

/**
 * @param {{
 *   report: any,
 *   categories?: string[] | null,
 *   check?: { status?: string, reason?: string } | null,
 * }} props
 */
function PerformancePanel({ report, categories = null, check = null }) {
  if (!report?.lab) {
    return (
      <section className="panel">
        <p className="hint-text">{missingReason(categories, check)}</p>
      </section>
    );
  }
  const { lab, field } = report;
  const scores = lab.scores || {};
  const metrics = Object.values(lab.metrics || {});
  return (
    <div className="perf-panels">
      <section className="panel perf-block">
        <h2 className="perf-title">Lighthouse 實驗室量測</h2>
        <p className="perf-lead">
          Google 以模擬行動裝置量測首頁一次（Lighthouse {lab.version || ""}）。單次量測會隨網路與伺服器狀況浮動，
          不計入 Argus 分數。
        </p>
        {lab.error ? (
          <p className="error-text">Lighthouse 無法完成量測（{lab.error}）。</p>
        ) : (
          <ul className="perf-scores">
            {SCORE_LABELS.filter(([key]) => scores[key] != null).map(([key, label]) => (
              <li key={key} className={`perf-score is-${scoreTone(scores[key])}`}>
                <span className="perf-score-value">{scores[key]}</span>
                <span className="perf-score-label">{label}</span>
              </li>
            ))}
          </ul>
        )}
        {metrics.length > 0 && (
          <dl className="perf-metrics">
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
            <h3 className="perf-subtitle">最值得改善的項目</h3>
            <ul className="perf-opportunities">
              {lab.opportunities.map((item) => (
                <li key={item.id}>
                  {item.title}
                  {item.display ? <span className="perf-muted">（{item.display}）</span> : null}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <section className="panel perf-block">
        <h2 className="perf-title">真實使用者體驗（CrUX）</h2>
        <p className="perf-lead">
          Chrome 使用者{field?.period || "過去 28 天"}的實際體驗（第 75 百分位）。
          {field?.scope === "origin" && "這個網址的資料不足，以下是整個網站的資料。"}
        </p>
        {field?.metrics ? (
          <dl className="perf-metrics">
            {Object.entries(field.metrics).map(([name, item]) => (
              <div key={name} className={`is-${FIELD_TONE[item.category] || "none"}`}>
                <dt>{name}</dt>
                <dd>
                  {formatField(name, item.p75)}
                  {item.category_label && <span className="perf-muted">（{item.category_label}）</span>}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="hint-text">{field?.reason || "沒有真實使用者資料。"}</p>
        )}
      </section>
    </div>
  );
}

export { PerformancePanel };
