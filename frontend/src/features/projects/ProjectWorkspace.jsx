// 網站專案工作區的外框：側邊欄（目前專案的功能）＋主內容，以及所有專案、新增專案與舊入口轉址。
// 資料關係與頁面架構見 docs/adr/0003-site-project-workspace.md。
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";

import { api } from "../../api";
import { CATEGORY_ORDER, Sparkline } from "../../components/projects/DashboardWidgets.jsx";
import SiteFavicon from "../../components/projects/SiteFavicon.jsx";
import { CATEGORY_LABELS, apiErrorMessage, isInProgress } from "../../shared/AppShared.jsx";
import { formatDateTime, formatRelative } from "../../shared/formatters";
import { useArgusStore } from "../../store";

// 側邊欄只用文字（名稱＋一行說明），目前頁以底色與字重標示——不用圖示與彩色左邊條。
const SECTIONS = [
  { key: "", label: "總覽", hint: "分數與本次變化" },
  { key: "scans", label: "掃描", hint: "建立與檢視掃描" },
  { key: "issues", label: "問題分析", hint: "新增、持續、未出現" },
  { key: "pages", label: "頁面", hint: "每頁狀態、速度與問題" },
  { key: "aeo", label: "AEO 問答", hint: "問題能否在網站找到答案" },
  { key: "history", label: "歷史報告", hint: "歷次分數與報告" },
  { key: "settings", label: "專案設定", hint: "預設掃描、網址、封存" },
];

/** 分數的文字色調（數字本身上色，不用彩色底的徽章）。 */
export function scoreTone(score) {
  if (score === null || score === undefined) return "is-none";
  return score >= 80 ? "is-good" : score >= 60 ? "is-medium" : "is-bad";
}

function sectionOf(pathname) {
  const match = pathname.match(/^\/projects\/\d+\/(\w+)/);
  return match ? match[1] : "";
}

export function projectPath(projectId, section = "") {
  return `/projects/${projectId}${section ? `/${section}` : ""}`;
}

function ProjectSidebar({ project, activeSection }) {
  return (
    <aside className="project-sidebar" aria-label="網站專案功能">
      <div className="project-sidebar-head">
        <div className="project-sidebar-title">
          <SiteFavicon project={project} />
          <p className="project-sidebar-name">{project.name}</p>
          <span
            className={`project-score-num ${scoreTone(project.summary?.latest_score)}`}
            title="最近一次完成的掃描分數"
          >
            {project.summary?.latest_score ?? "—"}
          </span>
        </div>
        <a
          className="project-sidebar-origin"
          href={project.origin}
          target="_blank"
          rel="noopener noreferrer"
          title="在新分頁開啟網站"
        >
          {project.hostname} ↗
        </a>
      </div>
      <nav className="project-sidebar-nav">
        {SECTIONS.map((section) => {
          const active = activeSection === section.key;
          return (
            <Link
              key={section.key || "overview"}
              to={projectPath(project.id, section.key)}
              className={`project-sidebar-link ${active ? "active" : ""}`}
              aria-current={active ? "page" : undefined}
            >
              <span className="project-sidebar-link-text">
                <span className="project-sidebar-link-label">{section.label}</span>
                <span className="project-sidebar-link-hint">{section.hint}</span>
              </span>
            </Link>
          );
        })}
      </nav>
      {activeSection !== "scans" && (
        <Link className="project-sidebar-cta" to={projectPath(project.id, "scans")}>
          建立新掃描 →
        </Link>
      )}
    </aside>
  );
}

/** 載入單一專案；成功時設為目前專案（封存的不設，避免切換器停在看不到的專案）。 */
function useProject(projectId) {
  const setCurrentProject = useArgusStore((s) => s.setCurrentProject);
  const upsertProject = useArgusStore((s) => s.upsertProject);
  const [project, setProjectState] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId) return undefined;
    let cancelled = false;
    setProjectState(null);
    setError("");
    api
      .get(`/projects/${projectId}/`)
      .then((response) => {
        if (cancelled) return;
        setProjectState(response.data);
        if (!response.data.archived_at) setCurrentProject(response.data.id);
      })
      .catch(() => {
        if (!cancelled) setError("找不到這個網站專案，可能已被移除或不屬於你的帳號。");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, setCurrentProject]);

  // 頁面改了專案（改名、恢復、封存）時同步回切換器的清單
  const setProject = useCallback(
    (next) => {
      setProjectState(next);
      upsertProject(next);
    },
    [upsertProject],
  );

  return { project, error, setProject };
}

function ProjectFrame({ project, activeSection, setProject, children }) {
  const setCurrentProject = useArgusStore((s) => s.setCurrentProject);
  const [restoring, setRestoring] = useState(false);

  async function restore() {
    setRestoring(true);
    try {
      const response = await api.post(`/projects/${project.id}/restore/`);
      setProject(response.data);
      setCurrentProject(response.data.id);
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div className="project-shell">
      <ProjectSidebar project={project} activeSection={activeSection} />
      <div className="project-main">
        {project.archived_at && (
          <div className="project-archived-banner" role="status">
            <span>這個專案已封存：不會出現在專案清單與切換器，掃描與報告都還在。</span>
            <button type="button" className="secondary-button" onClick={restore} disabled={restoring}>
              {restoring ? "恢復中…" : "恢復專案"}
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

function ProjectError({ message }) {
  return (
    <section className="panel project-empty">
      <p className="error-text">{message}</p>
      <Link className="secondary-button" to="/projects">← 回到所有專案</Link>
    </section>
  );
}

/** /projects/:projectId/*：總覽、掃描、問題分析、歷史報告、專案設定的共同外框。 */
function ProjectWorkspace() {
  const { projectId } = useParams();
  const location = useLocation();
  const { project, error, setProject } = useProject(projectId);
  if (error) return <ProjectError message={error} />;
  if (!project) return <section className="panel"><p className="hint-text">載入網站專案中…</p></section>;
  return (
    <ProjectFrame project={project} activeSection={sectionOf(location.pathname)} setProject={setProject}>
      <Outlet context={{ project, setProject }} />
    </ProjectFrame>
  );
}

/**
 * /scans/:scanId（含拓樸、複刻）的外框：網址維持不變（MCP、報告與舊連結都指向這裡），
 * 依掃描所屬專案顯示同一個側邊欄，「掃描」為目前分頁。
 */
function ProjectScanShell() {
  const { scanId } = useParams();
  const [projectId, setProjectId] = useState(null);
  const [scanError, setScanError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setProjectId(null);
    setScanError("");
    api
      .get(`/scans/${scanId}/`)
      .then((response) => {
        if (!cancelled) setProjectId(response.data.project || "none");
      })
      .catch(() => {
        if (!cancelled) setScanError("無法載入掃描資料，可能不存在或無權限。");
      });
    return () => {
      cancelled = true;
    };
  }, [scanId]);

  const { project, error, setProject } = useProject(projectId === "none" ? null : projectId);

  if (scanError) return <ProjectError message={scanError} />;
  // 沒有所屬專案（理論上不會發生：migration 已回填）或專案讀不到時，仍讓使用者看得到掃描
  if (projectId === "none" || error) return <Outlet context={{ project: null }} />;
  if (!project) return <section className="panel"><p className="hint-text">載入掃描資料中…</p></section>;
  return (
    <ProjectFrame project={project} activeSection="scans" setProject={setProject}>
      <Outlet context={{ project }} />
    </ProjectFrame>
  );
}

/** 舊入口（/dashboard、/scans、/history）：轉到目前專案的對應分頁；沒有專案時引導新增。 */
function ProjectHomeRedirect({ section = "" }) {
  const projects = useArgusStore((s) => s.projects);
  const currentProjectId = useArgusStore((s) => s.currentProjectId);
  const fetchProjects = useArgusStore((s) => s.fetchProjects);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (projects === null) {
      fetchProjects().then((data) => {
        if (data === null) setFailed(true);
      });
    }
  }, [projects, fetchProjects]);

  if (failed) return <ProjectError message="無法載入網站專案，請重新整理頁面。" />;
  if (projects === null) return <section className="panel"><p className="hint-text">載入網站專案中…</p></section>;
  if (!projects.length) return <Navigate to="/projects/new" replace />;
  const target = projects.find((item) => item.id === currentProjectId) || projects[0];
  return <Navigate to={projectPath(target.id, section)} replace />;
}

function scoreDelta(summary) {
  if (summary.latest_score == null || summary.previous_score == null) return null;
  return summary.latest_score - summary.previous_score;
}

/** 跨網站的總覽（取代原本的 Dashboard 全帳號統計）：一列數字，不做成四張卡片。 */
function PortfolioSummary({ projects }) {
  const scored = projects.map((p) => p.summary.latest_score).filter((score) => score != null);
  const average = scored.length ? Math.round(scored.reduce((a, b) => a + b, 0) / scored.length) : null;
  const attention = scored.filter((score) => score < 60).length;
  const running = projects.filter((p) => p.summary.latest_scan && isInProgress(p.summary.latest_scan.status)).length;
  const openIssues = projects.reduce(
    (sum, p) => sum + Object.values(p.summary.issue_counts || {}).reduce((a, b) => a + b, 0),
    0,
  );
  const items = [
    { label: "網站", value: projects.length },
    { label: "平均分數", value: average ?? "—", hint: scored.length < projects.length ? `${projects.length - scored.length} 個尚未完成掃描` : "" },
    { label: "低於 60 分", value: attention, tone: attention ? "is-bad" : "" },
    { label: "目前問題", value: openIssues, hint: "各網站最新一次完成掃描" },
    { label: "掃描進行中", value: running },
  ];
  return (
    <dl className="project-portfolio">
      {items.map((item) => (
        <div key={item.label} className={`project-portfolio-item ${item.tone || ""}`}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
          {item.hint && <p>{item.hint}</p>}
        </div>
      ))}
    </dl>
  );
}

const ISSUE_SEVERITIES = [
  ["critical", "嚴重"],
  ["high", "高"],
  ["medium", "中"],
  ["low", "低"],
];

const PROJECT_SORTS = {
  attention: { label: "需要注意", compare: (a, b) => (a.summary.latest_score ?? 101) - (b.summary.latest_score ?? 101) },
  recent: {
    label: "最近掃描",
    compare: (a, b) =>
      String(b.summary.latest_scan?.created_at || "").localeCompare(String(a.summary.latest_scan?.created_at || "")),
  },
  name: { label: "名稱", compare: (a, b) => a.name.localeCompare(b.name, "zh-Hant") },
};

/** 一個網站的一列：圖示與名稱、分數與變化、走勢、各維度、目前問題、上次掃描。 */
function ProjectRow({ project, onRestore, restoring }) {
  const summary = project.summary;
  const delta = scoreDelta(summary);
  const latest = summary.latest_scan;
  const archived = Boolean(project.archived_at);
  const running = latest && isInProgress(latest.status);
  const history = (summary.score_history || []).map((value, index) => ({ label: `第 ${index + 1} 次`, value }));
  const issues = summary.issue_counts || {};
  const issueTotal = Object.values(issues).reduce((a, b) => a + b, 0);
  return (
    <tr className={archived ? "is-archived" : ""}>
      <th scope="row">
        <span className="project-row-site">
        <SiteFavicon project={project} />
        <span className="project-row-name">
          {archived ? (
            <strong>{project.name}</strong>
          ) : (
            <Link to={projectPath(project.id)} className="project-row-link">{project.name}</Link>
          )}
          <small>{project.hostname}</small>
        </span>
        </span>
      </th>
      <td className="project-row-score">
        <span className={`project-score-num is-lg ${scoreTone(summary.latest_score)}`}>{summary.latest_score ?? "—"}</span>
        {delta !== null && delta !== 0 && (
          <span className={`project-delta ${delta > 0 ? "is-up" : "is-down"}`}>{delta > 0 ? `+${delta}` : delta}</span>
        )}
      </td>
      <td className="project-row-trend">
        <Sparkline points={history} label={`${project.name} 的分數`} />
      </td>
      <td className="project-row-cats">
        {summary.last_completed_at ? (
          <ul className="project-mini-cats">
            {CATEGORY_ORDER.map((category) => {
              const score = summary.latest_category_scores?.[category];
              return (
                <li key={category} title={`${CATEGORY_LABELS[category]}：${score == null ? "未評估" : Math.round(score)}`}>
                  <span>{CATEGORY_LABELS[category]}</span>
                  <span className="project-mini-track" aria-hidden="true">
                    {score != null && <span className={`project-mini-fill ${scoreTone(score)}`} style={{ width: `${score}%` }} />}
                  </span>
                  <b>{score == null ? "—" : Math.round(score)}</b>
                </li>
              );
            })}
          </ul>
        ) : (
          <span className="hint-text">尚無完成的掃描</span>
        )}
      </td>
      <td className="project-row-issues">
        {issueTotal ? (
          <span className="project-issue-tally">
            {ISSUE_SEVERITIES.filter(([key]) => issues[key]).map(([key, label]) => (
              <span key={key} className={`project-sev-dot sev-${key}`}>{label} {issues[key]}</span>
            ))}
          </span>
        ) : (
          <span className="hint-text">{summary.last_completed_at ? "沒有待處理問題" : "—"}</span>
        )}
      </td>
      <td className="project-row-last">
        {running ? (
          <Link className="project-running" to={`/scans/${latest.id}`}>掃描進行中</Link>
        ) : latest ? (
          <span title={formatDateTime(latest.created_at)}>{formatRelative(latest.created_at)}</span>
        ) : (
          <span className="hint-text">尚未掃描</span>
        )}
        <small>{summary.scans_count ? `共 ${summary.scans_count} 次` : ""}</small>
      </td>
      <td className="project-row-actions">
        {archived ? (
          <>
            <button type="button" className="secondary-button" onClick={() => onRestore(project)} disabled={restoring}>
              {restoring ? "恢復中…" : "恢復專案"}
            </button>
            <Link className="project-text-link" to={projectPath(project.id, "history")}>查看歷史</Link>
          </>
        ) : (
          <>
            <Link className="project-text-link" to={projectPath(project.id, "issues")}>問題</Link>
            <Link className="project-text-link" to={projectPath(project.id, "scans")}>掃描</Link>
          </>
        )}
      </td>
    </tr>
  );
}

function ProjectTable({ projects, caption, onRestore, restoringId }) {
  return (
    <div className="project-table-wrap">
      <table className="project-registry">
        <caption className="project-sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">網站</th>
            <th scope="col">分數</th>
            <th scope="col">走勢</th>
            <th scope="col">各維度</th>
            <th scope="col">目前問題</th>
            <th scope="col">上次掃描</th>
            <th scope="col"><span className="project-sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <ProjectRow
              key={project.id}
              project={project}
              onRestore={onRestore}
              restoring={restoringId === project.id}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** /projects：所有網站專案（跨網站總覽＋專案卡片；已封存的另列，可直接恢復）。 */
function ProjectsListPage() {
  const projects = useArgusStore((s) => s.projects);
  const fetchProjects = useArgusStore((s) => s.fetchProjects);
  const upsertProject = useArgusStore((s) => s.upsertProject);
  const [archived, setArchived] = useState(null);
  const [showArchived, setShowArchived] = useState(false);
  const [restoringId, setRestoringId] = useState(null);
  const [sort, setSort] = useState("attention");
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    if (!showArchived || archived !== null) return;
    api
      .get("/projects/", { params: { archived: true } })
      .then((response) => setArchived(response.data))
      .catch(() => setArchived([]));
  }, [showArchived, archived]);

  async function restore(project) {
    setRestoringId(project.id);
    try {
      const response = await api.post(`/projects/${project.id}/restore/`);
      upsertProject(response.data);
      setArchived((list) => (list || []).filter((item) => item.id !== project.id));
    } finally {
      setRestoringId(null);
    }
  }

  const keyword = query.trim().toLowerCase();
  const visible = (projects || [])
    .filter((p) => !keyword || `${p.name} ${p.origin}`.toLowerCase().includes(keyword))
    .sort(PROJECT_SORTS[sort].compare);

  return (
    <div className="project-page project-list-page">
      <header className="project-page-head">
        <div>
          <p className="eyebrow">網站專案</p>
          <h1 className="project-page-title">所有專案</h1>
          <p className="project-page-sub">一個專案對應一個網站；掃描、問題分析與歷史報告都以網站為單位保存。</p>
        </div>
      </header>
      {projects === null && <p className="hint-text">載入中…</p>}
      {projects && projects.length === 0 && (
        <section className="panel project-empty">
          <p className="project-empty-title">還沒有網站專案</p>
          <p className="hint-text">新增你要管理的網站，之後每次掃描的分數、問題與報告都會集中在那裡。</p>
          <Link className="primary-button" to="/projects/new">新增第一個專案</Link>
        </section>
      )}
      {projects && projects.length > 0 && (
        <>
          <PortfolioSummary projects={projects} />
          <div className="project-list-toolbar">
            <Link className="primary-button" to="/projects/new">新增網站專案</Link>
            <div className="project-filter" role="group" aria-label="排序">
              <span className="project-filter-label">排序</span>
              {Object.entries(PROJECT_SORTS).map(([key, option]) => (
                <button
                  key={key}
                  type="button"
                  className={`project-chip ${sort === key ? "active" : ""}`}
                  aria-pressed={sort === key}
                  onClick={() => setSort(key)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            {projects.length > 4 && (
              <input
                type="search"
                className="input project-list-search"
                placeholder="搜尋網站名稱或網址"
                aria-label="搜尋網站專案"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            )}
          </div>
          <ProjectTable projects={visible} caption="網站專案" />
          {!visible.length && <p className="hint-text">找不到符合「{query}」的網站。</p>}
        </>
      )}
      <section className="project-archived">
        <button
          type="button"
          className="project-text-link"
          aria-expanded={showArchived}
          onClick={() => setShowArchived((value) => !value)}
        >
          {showArchived ? "隱藏已封存的專案" : "顯示已封存的專案"}
        </button>
        {showArchived && archived === null && <p className="hint-text">載入中…</p>}
        {showArchived && archived?.length === 0 && <p className="hint-text">沒有已封存的專案。</p>}
        {showArchived && archived?.length > 0 && (
          <ProjectTable projects={archived} caption="已封存的網站專案" onRestore={restore} restoringId={restoringId} />
        )}
      </section>
    </div>
  );
}

/** /projects/new：新增網站專案。同一網站已有專案時引導過去，已封存的會自動恢復。 */
function ProjectCreatePage() {
  const navigate = useNavigate();
  const upsertProject = useArgusStore((s) => s.upsertProject);
  const setCurrentProject = useArgusStore((s) => s.setCurrentProject);
  const projects = useArgusStore((s) => s.projects);
  const [startUrl, setStartUrl] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [existing, setExisting] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setExisting(null);
    try {
      const response = await api.post("/projects/", { start_url: startUrl, name });
      upsertProject(response.data);
      setCurrentProject(response.data.id);
      navigate(projectPath(response.data.id, "scans"));
    } catch (err) {
      if (err?.response?.status === 409) {
        setExisting(err.response.data.project);
        setError(err.response.data.detail);
      } else {
        setError(apiErrorMessage(err, "新增專案失敗，請確認網址。"));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="project-page project-create-page">
      {projects && projects.length > 0 && (
        <Link className="back-to-list-button" to="/projects">← 回到所有專案</Link>
      )}
      <form className="panel project-create-form" onSubmit={handleSubmit}>
        <p className="eyebrow">新增網站專案</p>
        <h1 className="project-page-title">你要管理哪個網站？</h1>
        <p className="project-page-sub">
          一個專案對應一個網站（同一個協定、網域與連接埠）。新增後即可建立第一次掃描，
          之後的分數變化、問題與報告都會保存在專案裡。
        </p>
        <label className="project-field" htmlFor="project-url">
          <span>網站網址</span>
          <input
            id="project-url"
            className="input"
            type="text"
            inputMode="url"
            placeholder="https://example.com/"
            value={startUrl}
            onChange={(event) => setStartUrl(event.target.value)}
            required
          />
          <small>也是之後掃描的預設起始網址，可在專案設定修改。</small>
        </label>
        <label className="project-field" htmlFor="project-name">
          <span>專案名稱（選填）</span>
          <input
            id="project-name"
            className="input"
            type="text"
            maxLength={80}
            placeholder="預設為網域名稱"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        {error && <p className="error-text" role="alert">{error}</p>}
        {existing && (
          <Link className="secondary-button" to={projectPath(existing.id)}>
            前往「{existing.name}」
          </Link>
        )}
        <button type="submit" className="primary-button" disabled={submitting || !startUrl.trim()}>
          {submitting ? "建立中…" : "建立專案並開始掃描"}
        </button>
      </form>
    </div>
  );
}

export {
  ProjectCreatePage,
  ProjectHomeRedirect,
  ProjectScanShell,
  ProjectsListPage,
  ProjectWorkspace,
};
