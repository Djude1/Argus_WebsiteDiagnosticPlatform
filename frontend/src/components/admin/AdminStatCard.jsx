// 後台統計卡與其內嵌的 sparkline。
//
// 原本定義在 AdminPages.jsx 內部，概覽與評論治理都要用卻無法重用；抽出後
// 兩處共用同一份，樣式不會再各自漂移。

export function AdminStatCard({ label, value, hint, tone = "cyan", icon: Icon, hero = false, spark }) {
  return (
    <div className={`admin-stat-card tone-${tone}${hero ? " hero" : ""}`}>
      <div className="admin-stat-head">
        <div className="admin-stat-label">{label}</div>
        {Icon && (
          <span className="admin-stat-icon-chip">
            <Icon />
          </span>
        )}
      </div>
      <div className="admin-stat-value">{value}</div>
      {hint && <div className="admin-stat-hint">{hint}</div>}
      {spark && <div className="admin-stat-spark">{spark}</div>}
    </div>
  );
}

export function AdminSparkline({ series, dataKey, color = "#0ea5e9", height = 40 }) {
  if (!series || series.length < 2) return null;
  const w = 240;
  const values = series.map((row) => row[dataKey] || 0);
  const maxV = Math.max(...values, 1);
  const minV = Math.min(...values, 0);
  const range = maxV - minV || 1;
  const step = w / (series.length - 1);
  const yFor = (v) => height - ((v - minV) / range) * height;
  const linePoints = values.map((v, i) => `${i * step},${yFor(v)}`).join(" ");
  const areaPoints = `0,${height} ${linePoints} ${w},${height}`;
  const gradId = `admin-spark-${dataKey}`;
  return (
    <svg className="admin-stat-spark-svg" viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#${gradId})`} stroke="none" />
      <polyline points={linePoints} fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
