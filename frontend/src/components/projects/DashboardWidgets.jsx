// 網站專案總覽儀表板的區塊（資料來自 /api/projects/<id>/overview/，見 backend apps/scans/projects.py）。
//
// 圖表準則：各維度的分數走勢用「每個維度一條小走勢線」（small multiples），每列以維度名稱標示，
// 不靠顏色辨識——品牌的 SEO／AEO 類別色在色覺差異與一般視覺下都太接近（validate_palette 不通過）。
// 長條的顏色代表分數等級（≥80 藍／60–79 琥珀／<60 紅，見 scoreTone），旁邊一定附數值與文字等級；
// 嚴重度環圖用保留的嚴重度色，並附圖例（名稱、數量、百分比）。每個資料點都有 <title> 提供滑過提示。
import { Link } from "react-router-dom";

import { formatDate } from "../../shared/formatters";
import { ChatIcon, MagnifierIcon, PhoneIcon, ShieldIcon, SparkIcon } from "../../shared/LineIcons";

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

/** 數量長條（文字標示），例如各維度問題數；item.tone 可指定顏色（good／medium／bad）。給 linkFor 時有數量的列可點。 */
export function CountBars({ items, emptyText, linkFor }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  if (!items.some((item) => item.value)) return <p className="hint-text">{emptyText}</p>;
  return (
    <ul className="dash-count-list">
      {items.map((item) => {
        const body = (
          <>
            <span className="dash-count-label">
              {item.label}
              {item.desc && <small>{item.desc}</small>}
            </span>
            <span className="dash-count-track" aria-hidden="true">
              <span
                className={`dash-count-fill ${item.tone ? `tone-${item.tone}` : ""}`}
                style={{ width: `${(item.value / max) * 100}%` }}
              />
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

// ── 2026-10-03 依參考設計的總覽區塊 ──

function percent(ratio) {
  return ratio == null ? "—" : `${Math.round(ratio * 100)}%`;
}

export const CATEGORY_META = {
  seo: { label: "SEO", desc: "搜尋引擎優化", Icon: MagnifierIcon },
  aeo: { label: "AEO", desc: "AI 答案引用可能性", Icon: ChatIcon },
  geo: { label: "GEO", desc: "生成式搜尋曝光", Icon: SparkIcon },
  ux: { label: "UX", desc: "行動版體驗", Icon: PhoneIcon },
  security: { label: "資安", desc: "網站安全性", Icon: ShieldIcon },
};

/** 分數色調：≥80 良好（藍）、60–79 中等（琥珀）、<60 待加強（紅）。 */
export function scoreTone(score) {
  if (score === null || score === undefined) return "none";
  return score >= 80 ? "good" : score >= 60 ? "medium" : "bad";
}

export function scoreGrade(score) {
  return { good: "良好", medium: "中等", bad: "待加強", none: "—" }[scoreTone(score)];
}

/** 各維度：圖示、名稱與說明、分數條（依分數上色）、分數、歷次走勢（只有一次時寫「僅一次」）。 */
export function CategoryScoreList({ latest, trend }) {
  const scores = latest.category_scores || {};
  return (
    <ul className="dash-cat-list">
      {CATEGORY_ORDER.map((category) => {
        const meta = CATEGORY_META[category];
        const checked = latest.categories.includes(category);
        const score = scores[category];
        const evaluated = checked && score !== undefined && score !== null;
        const history = trend
          .map((point) => ({ label: formatDate(point.completed_at), value: point.category_scores?.[category] }))
          .filter((point) => typeof point.value === "number");
        return (
          <li key={category} className={`dash-cat-row tone-${evaluated ? scoreTone(score) : "none"}`}>
            <span className={`dash-cat-icon cat-${category}`} aria-hidden="true"><meta.Icon /></span>
            <span className="dash-cat-name">
              <strong>{meta.label}</strong>
              <small>{meta.desc}</small>
            </span>
            <span className="dash-cat-track" aria-hidden="true">
              {evaluated && <span className="dash-cat-fill" style={{ width: `${score}%` }} />}
            </span>
            <span className="dash-cat-score">
              {evaluated
                ? Math.round(score)
                : !checked
                  ? "未勾選"
                  : category === "aeo" && latest.aeo_status === "insufficient"
                    ? "內容不足"
                    : "未評估"}
            </span>
            <span className="dash-cat-trend">
              {history.length >= 2 ? <Sparkline points={history} label={meta.label} /> : evaluated ? "僅一次" : ""}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

const DONUT_ORDER = ["critical", "high", "medium", "low", "info"];
const DONUT_LABELS = { critical: "嚴重", high: "高", medium: "中", low: "低", info: "資訊" };

/** 問題嚴重程度分布：甜甜圈圖＋圖例（數量與百分比）；每段可滑過看數字。 */
export function SeverityDonut({ counts }) {
  const total = DONUT_ORDER.reduce((sum, key) => sum + (counts[key] || 0), 0);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="dash-donut">
      <svg viewBox="0 0 140 140" className="dash-donut-chart" role="img" aria-label={`共 ${total} 個問題的嚴重程度分布`}>
        <circle cx="70" cy="70" r={radius} className="dash-donut-track" />
        {total > 0 &&
          DONUT_ORDER.filter((key) => counts[key]).map((key) => {
            const length = (counts[key] / total) * circumference;
            // 段與段之間留 2px 空隙
            const gap = Math.min(2, length / 2);
            const segment = (
              <circle
                key={key}
                cx="70"
                cy="70"
                r={radius}
                className={`dash-donut-seg sev-${key}`}
                strokeDasharray={`${length - gap} ${circumference - length + gap}`}
                strokeDashoffset={-offset}
              >
                <title>{`${DONUT_LABELS[key]}：${counts[key]} 個`}</title>
              </circle>
            );
            offset += length;
            return segment;
          })}
        <text x="70" y="68" textAnchor="middle" className="dash-donut-total">{total}</text>
        <text x="70" y="88" textAnchor="middle" className="dash-donut-unit">個問題</text>
      </svg>
      <ul className="dash-donut-legend">
        {DONUT_ORDER.map((key) => (
          <li key={key}>
            <span className={`dash-donut-dot sev-${key}`} aria-hidden="true" />
            <span className="dash-donut-name">{DONUT_LABELS[key]}</span>
            <span className="dash-donut-count">{counts[key] || 0}</span>
            <span className="dash-donut-pct">{total ? Math.round(((counts[key] || 0) / total) * 100) : 0}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** AEO 問答檢測：兩個比例方塊（附圖示）＋各判定題數。 */
export function AeoTiles({ aeo }) {
  if (!aeo) return <p className="hint-text">這次掃描沒有勾選 AEO。</p>;
  if (aeo.status !== "evaluated") return <p className="hint-text">未充分評估：{aeo.reason}</p>;
  const counts = aeo.counts || {};
  return (
    <>
      <div className="dash-aeo-tiles">
        <div className="dash-aeo-tile">
          <span className="dash-aeo-tile-icon" aria-hidden="true"><MagnifierIcon /></span>
          <span>
            <strong>{percent(aeo.answered_ratio)}</strong>
            <small>問題的答案可以在網站上找到</small>
          </span>
        </div>
        <div className="dash-aeo-tile">
          <span className="dash-aeo-tile-icon" aria-hidden="true"><ShieldIcon /></span>
          <span>
            <strong>{percent(aeo.evidence_ratio)}</strong>
            <small>答案附有原文證據</small>
          </span>
        </div>
      </div>
      <p className="dash-aeo-counts">
        共 {aeo.questions_total} 題：可回答 {counts.answered ?? 0}、資訊不足 {counts.insufficient ?? 0}、
        內容衝突 {counts.conflict ?? 0}、無答案 {counts.missing ?? 0}
      </p>
    </>
  );
}
