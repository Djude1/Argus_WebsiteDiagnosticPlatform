/**
 * 快速檢查頁「釣魚偵測」結果（網址與郵件共用，2026-10-09 重排）：
 * 風險分數＋等級文字＋長條、建議、偵測到的可疑訊號；郵件另列寄件資訊。
 * 長條寬度是動態值（風險分數），以 CSS 變數帶入。
 */
const LEVEL = {
  high: { tone: "bad", label: "高風險" },
  medium: { tone: "warn", label: "中風險" },
  low: { tone: "warn", label: "低風險" },
  minimal: { tone: "good", label: "低訊號" },
};

export default function PhishingResult({ result, email = false }) {
  const level = LEVEL[result.risk_level] || LEVEL.minimal;
  const features = result.features || [];
  const meta = email
    ? [
        ["寄件網域", result.from_domain],
        ["回覆網域（Reply-To）", result.reply_to_domain],
        ["退信網域（Return-Path）", result.return_path_domain],
        ["信內連結", `${result.url_count ?? 0} 個`],
        ["附件", result.attachments?.length ? result.attachments.join("、") : "無"],
      ]
    : [];
  return (
    <div className="phish-result" aria-live="polite">
      <div className={`phish-risk is-${level.tone}`}>
        <div className="phish-risk-head">
          <strong>{result.risk_score}</strong>
          <span className="phish-risk-max">/ 100</span>
          <span className="phish-risk-level">{level.label}</span>
        </div>
        <div
          className="phish-meter"
          role="meter"
          aria-label="風險分數"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={result.risk_score}
        >
          <span style={{ "--risk": `${result.risk_score}%` }} />
        </div>
        <p className="phish-advice">{result.recommendation}</p>
      </div>
      {meta.length > 0 && (
        <dl className="speed-metrics phish-meta">
          {meta.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || "未解析"}</dd>
            </div>
          ))}
        </dl>
      )}
      <h4 className="speed-subtitle">偵測到的可疑訊號（{features.length}）</h4>
      {features.length > 0 ? (
        <ul className="speed-findings">
          {features.slice(0, 6).map((f, idx) => (
            <li key={`${f.title}-${idx}`}>
              <span className="speed-finding-text">
                <strong>{f.title}</strong>
                <span className="phish-evidence">{f.evidence}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="speed-lead">沒有偵測到明顯的可疑特徵；這不代表一定安全，仍請依情境判斷。</p>
      )}
    </div>
  );
}
