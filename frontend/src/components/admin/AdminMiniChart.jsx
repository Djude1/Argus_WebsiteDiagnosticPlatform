// 後台多序列折線圖（14 天活動）。
//
// 與 shared/AppShared.jsx 的 LineChart 是兩套實作，暫時並存：後者服務使用者端的
// 掃描圖表、座標與色階規則不同。統一為單一圖表系統列在後續工作，不在本次範圍。

export function AdminMiniChart({ series, keys, height = 110 }) {
  // series: [{date, ...values}]；keys: [{key, label, color}]
  if (!series || series.length === 0) {
    return <div className="admin-empty">尚無資料</div>;
  }
  const w = 480;
  const padding = { top: 8, right: 8, bottom: 24, left: 36 };
  const plotW = w - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const allValues = series.flatMap((row) => keys.map((k) => row[k.key] || 0));
  const maxV = Math.max(...allValues, 1);
  const step = series.length > 1 ? plotW / (series.length - 1) : 0;
  const yFor = (v) => padding.top + plotH - (v / maxV) * plotH;
  const xFor = (i) => padding.left + i * step;
  const yTicks = [0, Math.round(maxV / 2), maxV];

  return (
    <svg className="admin-mini-chart" viewBox={`0 0 ${w} ${height}`} width="100%" height={height}>
      <defs>
        {keys.map((k) => (
          <linearGradient key={k.key} id={`admin-chart-fill-${k.key}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={k.color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={k.color} stopOpacity="0" />
          </linearGradient>
        ))}
      </defs>
      {yTicks.map((t) => (
        <g key={t}>
          <line
            x1={padding.left}
            x2={w - padding.right}
            y1={yFor(t)}
            y2={yFor(t)}
            stroke="#e2e8f0"
            strokeDasharray="2 4"
          />
          <text x={padding.left - 6} y={yFor(t) + 3} fontSize="10" fill="#94a3b8" textAnchor="end">
            {t.toLocaleString()}
          </text>
        </g>
      ))}
      {keys.map((k) => {
        const points = series.map((row, i) => [xFor(i), yFor(row[k.key] || 0)]);
        const linePoints = points.map(([x, y]) => `${x},${y}`).join(" ");
        const areaPoints = [
          `${points[0][0]},${padding.top + plotH}`,
          ...points.map(([x, y]) => `${x},${y}`),
          `${points[points.length - 1][0]},${padding.top + plotH}`,
        ].join(" ");
        const [lastX, lastY] = points[points.length - 1];
        return (
          <g key={k.key}>
            <polygon points={areaPoints} fill={`url(#admin-chart-fill-${k.key})`} stroke="none" />
            <polyline
              points={linePoints}
              fill="none"
              stroke={k.color}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <circle
              className="admin-mini-chart-dot"
              cx={lastX}
              cy={lastY}
              r="3.5"
              fill={k.color}
            />
          </g>
        );
      })}
      {series.length > 0 && (
        <>
          <text x={xFor(0)} y={height - 4} fontSize="10" fill="#94a3b8" textAnchor="start">
            {series[0].date.slice(5)}
          </text>
          <text x={xFor(series.length - 1)} y={height - 4} fontSize="10" fill="#94a3b8" textAnchor="end">
            {series[series.length - 1].date.slice(5)}
          </text>
        </>
      )}
    </svg>
  );
}
