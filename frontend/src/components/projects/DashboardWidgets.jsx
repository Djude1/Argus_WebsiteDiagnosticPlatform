// 網站專案總覽儀表板的區塊（資料來自 /api/projects/<id>/overview/，見 backend apps/scans/projects.py）。
//
// 圖表準則：各維度的分數走勢用「每個維度一條小走勢線」（small multiples），每列以維度名稱標示，
// 不靠顏色辨識——品牌的 SEO／AEO 類別色在色覺差異與一般視覺下都太接近（validate_palette 不通過）。
// 數量比較用單色、附文字與數值的長條；每個資料點都有 <title> 提供滑過提示。
import { Link } from "react-router-dom";

import { ScanStatusBadge, ScoreBadge } from "../scans/ScanBadges.jsx";
import { CATEGORY_LABELS } from "../../shared/AppShared.jsx";
import { formatDate, formatDateTime, formatDuration, formatRelative } from "../../shared/formatters";

export const CATEGORY_ORDER = ["seo", "aeo", "geo", "ux", "security"];

const SPARK_W = 120;
const SPARK_H = 30;
const SPARK_PAD = 4;

/** 單一序列的小走勢線（0–100 分），最後一點加圓點；資料點滑過顯示日期與分數。 */
export function Sparkline({ points, label }) {
  const values = points.filter((point) => typeof point.value === "number");
  if (values.length < 2) {
    return <span className="dash-spark-empty">{values.length ? "僅 1 次" : "—"}</span>;
  }
  const step = (SPARK_W - SPARK_PAD * 2) / (values.length - 1);
  const xy = values.map((point, index) => ({
    ...point,
    x: SPARK_PAD + index * step,
    y: SPARK_PAD + (1 - point.value / 100) * (SPARK_H - SPARK_PAD * 2),
  }));
  const last = xy[xy.length - 1];
  return (
    <svg
      className="dash-spark"
      viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
      width={SPARK_W}
      height={SPARK_H}
      role="img"
      aria-label={`${label}分數走勢：${values.map((p) => p.value).join("、")}`}
    >
      <polyline points={xy.map((p) => `${p.x},${p.y}`).join(" ")} className="dash-spark-line" />
      {xy.map((p) => (
        <circle key={`${p.x}`} cx={p.x} cy={p.y} r={p === last ? 3 : 6} className={p === last ? "dash-spark-last" : "dash-spark-hit"}>
          <title>{`${p.label}：${p.value} 分`}</title>
        </circle>
      ))}
    </svg>
  );
}

/** 各維度：目前分數條＋歷次走勢＋分數或未評估原因。 */
export function CategoryPanel({ latest, trend }) {
  const scores = latest.category_scores || {};
  return (
    <ul className="dash-category-list">
      {CATEGORY_ORDER.map((category) => {
        const checked = latest.categories.includes(category);
        const score = scores[category];
        let note = "";
        if (!checked) note = "本次未勾選";
        else if (score === undefined || score === null) {
          note = category === "aeo" && latest.aeo_status === "insufficient" ? "未評估（內容不足）" : "未評估";
        }
        const tone = score >= 80 ? "good" : score >= 60 ? "medium" : "bad";
        const history = trend.map((point) => ({
          label: formatDate(point.completed_at),
          value: point.category_scores?.[category],
        }));
        return (
          <li key={category} className="dash-category-row">
            <span className="dash-category-name">{CATEGORY_LABELS[category]}</span>
            <span className="project-category-bar" aria-hidden="true">
              {!note && <span className={`project-category-fill tone-${tone}`} style={{ width: `${score}%` }} />}
            </span>
            <Sparkline points={history} label={CATEGORY_LABELS[category]} />
            <span className="dash-category-score">{note || Math.round(score)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** 數量長條（單色、文字標示），例如各維度問題數。給 linkFor 時有數量的列可點。 */
export function CountBars({ items, emptyText, linkFor }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  if (!items.some((item) => item.value)) return <p className="hint-text">{emptyText}</p>;
  return (
    <ul className="dash-count-list">
      {items.map((item) => {
        const body = (
          <>
            <span className="dash-count-label">{item.label}</span>
            <span className="dash-count-track" aria-hidden="true">
              <span className="dash-count-fill" style={{ width: `${(item.value / max) * 100}%` }} />
            </span>
            <span className="dash-count-value">{item.value}</span>
          </>
        );
        return (
          <li key={item.key}>
            {linkFor && item.value ? (
              <Link className="dash-count-row is-link" to={linkFor(item)} title={`查看${item.label}的問題`}>{body}</Link>
            ) : (
              <span className="dash-count-row">{body}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** 本次掃描的覆蓋與耗時：讓「沒有問題」有意義——先看到底檢查了多少。 */
export function ScanStatsList({ latest }) {
  const stats = latest.stats;
  const rows = [
    { label: "已分析頁面", value: `${stats.pages}${stats.max_pages > 1 ? ` ／ 上限 ${stats.max_pages}` : "（單頁）"}` },
    { label: "被阻擋頁面", value: stats.pages_blocked, warn: stats.pages_blocked > 0 },
    { label: "擷取失敗", value: stats.pages_failed, warn: stats.pages_failed > 0 },
    { label: "發現項目", value: stats.findings },
    { label: "掃描耗時", value: formatDuration(stats.duration_seconds) },
    { label: "模式", value: latest.scan_mode === "active" ? "主動測試" : "被動偵測" },
  ];
  return (
    <dl className="dash-stats">
      {rows.map((row) => (
        <div key={row.label} className={row.warn ? "is-warn" : ""}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function percent(ratio) {
  return ratio == null ? "—" : `${Math.round(ratio * 100)}%`;
}

/** AEO 問答檢測摘要（逐題結果在專案的「AEO 問答」分頁）。 */
export function AeoSummary({ aeo }) {
  if (!aeo) return <p className="hint-text">這次掃描沒有勾選 AEO。</p>;
  if (aeo.status !== "evaluated") {
    return <p className="hint-text">未充分評估：{aeo.reason}</p>;
  }
  const counts = aeo.counts || {};
  return (
    <div className="dash-aeo">
      <div className="dash-aeo-ratios">
        <div>
          <strong>{percent(aeo.answered_ratio)}</strong>
          <span>問題可從網站找到答案</span>
        </div>
        <div>
          <strong>{percent(aeo.evidence_ratio)}</strong>
          <span>答案附有原文證據</span>
        </div>
      </div>
      <p className="dash-aeo-counts">
        共 {aeo.questions_total} 題：可回答 {counts.answered ?? 0}、資訊不足 {counts.insufficient ?? 0}、
        衝突 {counts.conflict ?? 0}、無答案 {counts.missing ?? 0}
      </p>
    </div>
  );
}

/** 最近幾次掃描（含進行中與失敗），可直接點進結果。 */
export function RecentScans({ scans }) {
  if (!scans.length) return <p className="hint-text">還沒有掃描紀錄。</p>;
  return (
    <ul className="dash-recent">
      {scans.map((scan) => (
        <li key={scan.id}>
          <Link to={`/scans/${scan.id}`} className="dash-recent-row" title={formatDateTime(scan.created_at)}>
            <span className="dash-recent-time">{formatRelative(scan.created_at)}</span>
            <span className="dash-recent-meta">
              {scan.max_pages > 1 ? "整站" : "單頁"}
              {scan.scan_mode === "active" ? " · 主動" : ""}
            </span>
            <ScanStatusBadge status={scan.status} />
            <ScoreBadge score={scan.overall_score} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
