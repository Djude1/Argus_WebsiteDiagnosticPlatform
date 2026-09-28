import { useState } from "react";

import { formatNumber } from "../../shared/formatters.js";

// 後台多序列趨勢圖（14 天活動）。
//
// 改為「小倍數」（small multiples）：每個序列一列、各自的縱軸。原本三條線共用一個縱軸，
// AI tokens 是幾十萬、掃描數是個位數，後兩條線永遠貼在 0，看不出任何趨勢。
// 滑過任一列時，所有列同步標出同一天，並在列首顯示當天數值（未滑過時顯示最新一天）。
//
// 配色走品牌序列：series-1 虹膜青、series-2 守望琥珀、之後依序取維度色（見 20-admin-dashboard-charts.css）。
//
// 與 shared/AppShared.jsx 的 LineChart 是兩套實作，暫時並存：後者服務使用者端的掃描圖表。

const W = 480;
const PAD_X = 4;

export function AdminMiniChart({ series, keys, height = 140 }) {
  // series: [{date, ...values}]；keys: [{key, label, format?}]
  const [hover, setHover] = useState(null);
  if (!series || series.length === 0) {
    return <div className="admin-empty">尚無資料</div>;
  }
  const rowH = Math.max(40, Math.round((height - 20) / Math.max(keys.length, 1)));
  const plotW = W - PAD_X * 2;
  const step = series.length > 1 ? plotW / (series.length - 1) : 0;
  const xFor = (i) => PAD_X + i * step;
  const activeIndex = hover ?? series.length - 1;
  const activeDate = series[activeIndex]?.date?.slice(5);

  return (
    <div className="admin-chart-wrap admin-multiples" onMouseLeave={() => setHover(null)}>
      {keys.map((k, keyIndex) => {
        const values = series.map((row) => Number(row[k.key]) || 0);
        const maxV = Math.max(...values, 1);
        const total = values.reduce((sum, v) => sum + v, 0);
        const yFor = (v) => 4 + (rowH - 8) * (1 - v / maxV);
        const points = values.map((v, i) => [xFor(i), yFor(v)]);
        const line = points.map(([x, y]) => `${x},${y}`).join(" ");
        const area = `${xFor(0)},${rowH} ${line} ${xFor(values.length - 1)},${rowH}`;
        const gradId = `admin-chart-fill-${k.key}`;
        const fmt = k.format || formatNumber;
        const [ax, ay] = points[activeIndex];
        return (
          <div className={`admin-multiple admin-chart-series series-${keyIndex + 1}`} key={k.key}>
            <div className="admin-multiple-head">
              <span className="admin-multiple-label">
                <i aria-hidden="true" />{k.label || k.key}
              </span>
              <span className="admin-multiple-value">
                <span className="admin-multiple-date">{hover === null ? "最新" : activeDate}</span>
                {fmt(values[activeIndex])}
              </span>
            </div>
            <div className="admin-multiple-plot">
            <svg
              className="admin-mini-chart"
              viewBox={`0 0 ${W} ${rowH}`}
              width="100%"
              height={rowH}
              preserveAspectRatio="none"
              role="img"
              aria-label={`${k.label || k.key}：14 天合計 ${fmt(total)}，最高 ${fmt(maxV)}，最新 ${fmt(values[values.length - 1])}`}
            >
              <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" className="admin-chart-stop" stopOpacity="0.28" />
                  <stop offset="100%" className="admin-chart-stop" stopOpacity="0" />
                </linearGradient>
              </defs>
              <line className="admin-chart-grid-line" x1={PAD_X} x2={W - PAD_X} y1={rowH - 0.5} y2={rowH - 0.5} />
              <polygon points={area} fill={`url(#${gradId})`} stroke="none" />
              <polyline className="admin-chart-line" points={line} vectorEffect="non-scaling-stroke" />
              {hover !== null && (
                <line className="admin-chart-hover-line" x1={ax} x2={ax} y1={0} y2={rowH} vectorEffect="non-scaling-stroke" />
              )}
              {series.map((row, i) => (
                <rect
                  key={row.date}
                  className="admin-chart-hit"
                  x={xFor(i) - step / 2}
                  y={0}
                  width={Math.max(step, 1)}
                  height={rowH}
                  onMouseEnter={() => setHover(i)}
                />
              ))}
            </svg>
            <span
              className="admin-multiple-dot"
              aria-hidden="true"
              style={{ left: `${(ax / W) * 100}%`, top: `${ay}px` }}
            />
            </div>
          </div>
        );
      })}
      <div className="admin-multiples-axis" aria-hidden="true">
        <span>{series[0].date.slice(5)}</span>
        <span>{series[series.length - 1].date.slice(5)}</span>
      </div>
    </div>
  );
}
