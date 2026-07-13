import { STATUS_LABELS, isInProgress } from "../../shared/AppShared.jsx";

export function ScanStatusBadge({ status }) {
  const meta = STATUS_LABELS[status] || { label: status, tone: "slate", emoji: "?" };
  const pulse = isInProgress(status) ? "animate-pulse" : "";
  return (
    <span className={`status-badge status-${meta.tone} ${pulse}`}>
      <span aria-hidden="true">{meta.emoji}</span>
      <span>{meta.label}</span>
    </span>
  );
}

export function ScoreBadge({ score }) {
  if (score === null || score === undefined) {
    return <span className="score-badge muted">尚無分數</span>;
  }
  const tone = score >= 80 ? "good" : score >= 60 ? "medium" : "bad";
  return <span className={`score-badge ${tone}`}>{score}</span>;
}
