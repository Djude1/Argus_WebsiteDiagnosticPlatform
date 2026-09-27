/*
 * IrisScore：品牌化的 0–100 分數環。
 * 外圈是分數弧（good ≥ 80／medium ≥ 60／bad），內圈 12 道刻度呼應 ArgusMark 的 12 顆小眼。
 * score 為 null 代表尚無分數，只畫軌道與「—」。
 */

type IrisScoreProps = {
  score: number | null | undefined;
  size?: number;
  caption?: string;
  className?: string;
};

export function scoreTone(score: number | null | undefined): "good" | "medium" | "bad" | "none" {
  if (score === null || score === undefined || Number.isNaN(score)) return "none";
  if (score >= 80) return "good";
  if (score >= 60) return "medium";
  return "bad";
}

export function IrisScore({ score, size = 96, caption, className = "" }: IrisScoreProps) {
  const stroke = Math.max(4, Math.round(size * 0.075));
  const radius = size / 2 - stroke;
  const circumference = 2 * Math.PI * radius;
  const hasScore = typeof score === "number" && !Number.isNaN(score);
  const clamped = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const offset = circumference * (1 - clamped / 100);
  const tickRadius = radius - stroke * 1.4;
  const ticks = Array.from({ length: 12 }, (_, i) => {
    const angle = (i / 12) * Math.PI * 2;
    const inner = tickRadius - stroke * 0.5;
    return {
      x1: size / 2 + Math.cos(angle) * inner,
      y1: size / 2 + Math.sin(angle) * inner,
      x2: size / 2 + Math.cos(angle) * tickRadius,
      y2: size / 2 + Math.sin(angle) * tickRadius,
    };
  });
  return (
    <div
      className={`ag-iris-score ${className}`}
      data-tone={scoreTone(score)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={hasScore ? `分數 ${Math.round(clamped)}${caption ? `，${caption}` : ""}` : "尚無分數"}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="ag-iris-score-track" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} />
        <g className="ag-iris-score-ticks" strokeWidth={Math.max(1, stroke * 0.22)} strokeLinecap="round">
          {ticks.map((tick, index) => (
            <line key={index} {...tick} />
          ))}
        </g>
        <circle
          className="ag-iris-score-value"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="ag-iris-score-label">
        <span className="ag-iris-score-num" style={{ fontSize: Math.round(size * 0.3) }}>
          {hasScore ? Math.round(clamped) : "—"}
        </span>
        {caption ? <span className="ag-iris-score-caption">{caption}</span> : null}
      </span>
    </div>
  );
}

export default IrisScore;
