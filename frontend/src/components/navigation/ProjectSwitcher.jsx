import { useEffect, useId, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import SiteFavicon from "../projects/SiteFavicon";
import { GearIcon } from "../../shared/LineIcons";
import { useArgusStore } from "../../store";

// 頂部工具列的網站專案切換器（docs/adr/0003-site-project-workspace.md）：
// 顯示目前專案，下拉列出所有專案（含最新分數）、各專案的設定入口、「所有專案」與「新增專案」。
// 切換時停留在同一個分頁（A 的問題分析 → B 的問題分析）；從掃描詳情等其他頁切換則回到新專案的總覽。
// 專案多於 SEARCH_THRESHOLD 個時顯示搜尋框；↑／↓ 在選項間移動，Esc 關閉並把焦點還給按鈕。

const SECTION_PATTERN = /^\/projects\/\d+(\/(scans|seo|issues|pages|aeo|history|settings))?\/?$/;
const SEARCH_THRESHOLD = 6;

/** 切換到 projectId 後要去的網址。 */
export function projectSwitchPath(pathname, projectId) {
  const match = pathname.match(SECTION_PATTERN);
  const section = match && match[1] ? match[1] : "";
  return `/projects/${projectId}${section}`;
}

function ProjectMark({ project }) {
  return <SiteFavicon project={project} className="project-switcher-mark" />;
}

function scoreTone(score) {
  if (score === null || score === undefined) return "is-none";
  return score >= 80 ? "is-good" : score >= 60 ? "is-medium" : "is-bad";
}

function ProjectSwitcher() {
  const projects = useArgusStore((s) => s.projects);
  const currentProjectId = useArgusStore((s) => s.currentProjectId);
  const fetchProjects = useArgusStore((s) => s.fetchProjects);
  const setCurrentProject = useArgusStore((s) => s.setCurrentProject);
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef(null);
  const menuId = useId();

  useEffect(() => {
    if (projects === null) fetchProjects();
  }, [projects, fetchProjects]);

  const list = projects || [];
  const showSearch = list.length > SEARCH_THRESHOLD;

  useEffect(() => {
    if (!open) return undefined;
    function onPointer(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") {
        setOpen(false);
        wrapRef.current?.querySelector(".project-switcher-trigger")?.focus();
        return;
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const items = [...(wrapRef.current?.querySelectorAll('[role="menuitem"]') || [])];
      if (!items.length) return;
      event.preventDefault();
      const index = items.indexOf(document.activeElement);
      const step = event.key === "ArrowDown" ? 1 : -1;
      items[(index + step + items.length) % items.length].focus();
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    // 開啟時焦點移到搜尋框（專案多時）或第一個選項
    const first = wrapRef.current?.querySelector(".project-switcher-search, [role=\"menuitem\"]");
    first?.focus();
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const current = list.find((project) => project.id === currentProjectId) || null;
  const keyword = query.trim().toLowerCase();
  const visible = keyword
    ? list.filter((p) => `${p.name} ${p.origin}`.toLowerCase().includes(keyword))
    : list;

  function close() {
    setOpen(false);
    setQuery("");
  }

  function go(path) {
    close();
    navigate(path);
  }

  function switchTo(project) {
    setCurrentProject(project.id);
    go(projectSwitchPath(location.pathname, project.id));
  }

  return (
    <div className="project-switcher" ref={wrapRef}>
      <button
        type="button"
        className="project-switcher-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => (open ? close() : setOpen(true))}
      >
        {current ? <ProjectMark project={current} /> : null}
        <span className="project-switcher-label">
          <span className="project-switcher-kicker">目前網站</span>
          <span className="project-switcher-name">
            {current ? current.name : list.length ? "選擇網站專案" : "尚無網站專案"}
          </span>
        </span>
        <span className="project-switcher-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="project-switcher-menu" id={menuId} role="menu" aria-label="網站專案">
          {showSearch && (
            <input
              type="search"
              className="project-switcher-search"
              placeholder="搜尋網站名稱或網址"
              aria-label="搜尋網站專案"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          )}
          <div className="project-switcher-list">
            {visible.map((project) => {
              const isCurrent = project.id === currentProjectId;
              const score = project.summary?.latest_score;
              return (
                <div key={project.id} className={`project-switcher-row ${isCurrent ? "is-current" : ""}`}>
                  <button
                    type="button"
                    role="menuitem"
                    className="project-switcher-item"
                    aria-current={isCurrent ? "true" : undefined}
                    onClick={() => switchTo(project)}
                  >
                    <ProjectMark project={project} />
                    <span className="project-switcher-item-text">
                      <strong>
                        {project.name}
                        {project.is_demo && <span className="project-switcher-demo">示範</span>}
                      </strong>
                      <small>{project.origin}</small>
                    </span>
                    <span
                      className={`project-switcher-score ${scoreTone(score)}`}
                      title={score == null ? "尚無完成的掃描" : "最近一次完成的掃描分數"}
                    >
                      {score ?? "—"}
                    </span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="project-switcher-gear"
                    aria-label={`${project.name} 的專案設定`}
                    title="專案設定"
                    onClick={() => {
                      setCurrentProject(project.id);
                      go(`/projects/${project.id}/settings`);
                    }}
                  >
                    <GearIcon />
                  </button>
                </div>
              );
            })}
            {list.length === 0 && (
              <p className="project-switcher-empty">
                一個專案對應一個網站，掃描、問題與報告都會集中在專案裡。
              </p>
            )}
            {list.length > 0 && visible.length === 0 && (
              <p className="project-switcher-empty">找不到符合「{query}」的網站。</p>
            )}
          </div>
          <div className="project-switcher-foot">
            <button type="button" role="menuitem" className="project-switcher-all" onClick={() => go("/projects")}>
              所有專案
            </button>
            <button type="button" role="menuitem" className="project-switcher-new" onClick={() => go("/projects/new")}>
              ＋ 新增專案
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ProjectSwitcher;
export { ProjectSwitcher };
