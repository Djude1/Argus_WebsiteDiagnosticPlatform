import { Link } from "react-router-dom";

import SiteFavicon from "./SiteFavicon.jsx";
import { isInProgress } from "../../shared/AppShared.jsx";
import { formatDateTime, formatRelative } from "../../shared/formatters";
import { CheckCircleIcon, ExternalIcon } from "../../shared/LineIcons";

// 網站專案各分頁共用的頁首：麵包屑（專案／網站／分頁）、網站圖示、名稱與驗證標記、網址、
// 最後掃描時間與狀態；description 放中間的說明文字，aside 放右側（動作按鈕或掃描選擇）。
// 最後掃描與狀態取自 project.summary（GET /api/projects/<id>/ 的 latest_scan、last_completed_at）。

function scanState(summary) {
  const latest = summary?.latest_scan;
  if (latest && isInProgress(latest.status)) return { tone: "running", label: "掃描進行中" };
  if (summary?.last_completed_at) return { tone: "done", label: "掃描完成" };
  if (latest?.status === "failed") return { tone: "failed", label: "上次掃描失敗" };
  return { tone: "none", label: "尚未掃描" };
}

export default function ProjectHeader({ project, section = "", description = "", aside = null }) {
  const summary = project.summary || {};
  const state = scanState(summary);
  const lastAt = summary.last_completed_at;
  return (
    <>
      <nav className="project-breadcrumb" aria-label="目前位置">
        <Link to="/projects">專案</Link>
        <span aria-hidden="true">/</span>
        {section ? <Link to={`/projects/${project.id}`}>{project.name}</Link> : <span aria-current="page">{project.name}</span>}
        {section && (
          <>
            <span aria-hidden="true">/</span>
            <span aria-current="page">{section}</span>
          </>
        )}
      </nav>
      <header className="project-hero">
        <div className="project-hero-id">
          <SiteFavicon project={project} size="xl" />
          <div className="project-hero-text">
            <h1 className="project-hero-name">
              {project.name}
              {project.domain_verified && (
                <span className="project-hero-verified" title="已通過網域所有權驗證，可進行主動式資安測試">
                  <CheckCircleIcon />
                  <span className="project-sr-only">已驗證</span>
                </span>
              )}
            </h1>
            <a className="project-hero-url" href={project.origin} target="_blank" rel="noopener noreferrer">
              {project.origin}
              <ExternalIcon />
            </a>
            <p className="project-hero-meta">
              <span title={lastAt ? formatDateTime(lastAt) : undefined}>
                最後掃描：{lastAt ? `${formatDateTime(lastAt)}（${formatRelative(lastAt)}）` : "—"}
              </span>
              <span className={`project-state-pill is-${state.tone}`}>{state.label}</span>
            </p>
          </div>
        </div>
        {description && <p className="project-hero-desc">{description}</p>}
        {aside && <div className="project-hero-aside">{aside}</div>}
      </header>
    </>
  );
}

export { ProjectHeader };
