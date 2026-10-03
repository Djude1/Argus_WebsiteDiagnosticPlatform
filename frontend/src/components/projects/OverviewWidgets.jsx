// 網站專案總覽的小元件：分數環與公告提示（原 Dashboard 頁，見 features/projects/）。
import { useEffect, useState } from "react";

function ScoreRing({ value, label, size = 96 }) {
  const display = value === null || value === undefined ? "—" : Math.round(value);
  const pct = typeof value === "number" ? Math.max(0, Math.min(100, value)) : 0;
  const tone = pct >= 80 ? "good" : pct >= 60 ? "medium" : "bad";
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  return (
    <div className={`score-ring tone-${tone}`} style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth="8"
          className="ring-track"
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          fill="none"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="ring-progress"
        />
      </svg>
      <div className="score-ring-text">
        <span className="score-ring-value">{display}</span>
        {label && <span className="score-ring-label">{label}</span>}
      </div>
    </div>
  );
}

// Dashboard 公告一律採非阻塞 toast；法律授權保留在建立掃描流程內。
function AnnouncementToast({ announcements, onDismiss }) {
  const [hovering, setHovering] = useState({});

  useEffect(() => {
    // 對每個顯示中的 toast 排 5 秒自動關（hover 時暫停）
    const timers = announcements
      .filter((a) => !hovering[a.id])
      .map((a) =>
        setTimeout(() => onDismiss(a.id), 5000),
      );
    return () => timers.forEach((t) => clearTimeout(t));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [announcements, hovering]);

  if (!announcements.length) return null;
  return (
    <div className="argus-toast-stack" role="status" aria-live="polite">
      {announcements.map((ann) => (
        <div
          key={ann.id}
          className="argus-toast"
          onMouseEnter={() => setHovering((h) => ({ ...h, [ann.id]: true }))}
          onMouseLeave={() => setHovering((h) => ({ ...h, [ann.id]: false }))}
        >
          <div className="argus-toast-body">
            <div className="argus-toast-title">{ann.title}</div>
            <div className="argus-toast-content">{ann.content.slice(0, 100)}{ann.content.length > 100 ? "…" : ""}</div>
          </div>
          <button
            type="button"
            className="argus-toast-close"
            onClick={() => onDismiss(ann.id)}
            aria-label="關閉公告"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

export { AnnouncementToast, ScoreRing };
