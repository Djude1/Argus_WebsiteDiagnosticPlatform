import { BRAND_MARKS } from "./brandMarks.jsx";

/**
 * 技術棧 logo 牆：4 欄垂直 marquee，欄與欄反向且速度不同，
 * 上下用 mask 漸層淡出，hover 暫停捲動。
 */

// 全部項目都對應專案實際使用的技術
// （pyproject.toml / frontend/package.json / frontend/Dockerfile / .github/workflows / k8s）
const TECH_STACK = [
  "React", "Vite", "Tailwind CSS", "React Router", "PWA",
  "Python", "Django", "Celery", "Redis", "PostgreSQL",
  "Playwright", "Gunicorn", "JWT", "Google OAuth", "uv",
  "Docker", "NGINX", "Kubernetes", "Argo CD", "GitHub Actions", "Cloudflare",
];

const COLUMN_COUNT = 4;
// 每欄速度錯開，避免視覺上同步成一整塊
const COLUMN_DURATIONS = [28, 36, 32, 40];

// 用輪流分派而非連續切片，項目數不是 4 的倍數時各欄長度才不會差太多
const columns = Array.from({ length: COLUMN_COUNT }, (_, col) =>
  TECH_STACK.filter((_, i) => i % COLUMN_COUNT === col),
);

function TechTile({ label }) {
  const mark = BRAND_MARKS[label];
  return (
    <div className="tech-tile" title={label}>
      <span className="tech-tile-mark">
        <svg viewBox={mark.viewBox} role="presentation" focusable="false" aria-hidden="true">
          {mark.node}
        </svg>
      </span>
      <span className="tech-tile-label">{label}</span>
    </div>
  );
}

export default function TechMarquee() {
  return (
    <div className="tech-marquee">
      {columns.map((column, colIndex) => (
        <div
          key={colIndex}
          className={`tech-marquee-col${colIndex % 2 === 1 ? " is-reverse" : ""}`}
          style={{ "--marquee-duration": `${COLUMN_DURATIONS[colIndex]}s` }}
        >
          <div className="tech-marquee-track">
            <div className="tech-marquee-group">
              {column.map((label) => (
                <TechTile key={label} label={label} />
              ))}
            </div>
            {/* 複製一份讓 translateY(-50%) 無縫循環；對輔助技術隱藏避免重複朗讀 */}
            <div className="tech-marquee-group is-clone" aria-hidden="true">
              {column.map((label) => (
                <TechTile key={label} label={label} />
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
