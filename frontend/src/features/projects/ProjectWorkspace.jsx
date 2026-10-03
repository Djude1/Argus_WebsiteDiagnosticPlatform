// 網站專案工作區的外框：側邊欄（目前專案的功能）＋主內容，以及所有專案、新增專案與舊入口轉址。
// 資料關係與頁面架構見 docs/adr/0003-site-project-workspace.md。
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";

import { api, fetchVerifiedDomains } from "../../api";
import { CATEGORY_ORDER, Sparkline } from "../../components/projects/DashboardWidgets.jsx";
import ScanDefaultsFields, { DEFAULT_SCAN_SETTINGS } from "../../components/projects/ScanDefaultsFields.jsx";
import SiteFavicon from "../../components/projects/SiteFavicon.jsx";
import { CATEGORY_LABELS, apiErrorMessage, isInProgress } from "../../shared/AppShared.jsx";
import { formatDate, formatDateTime, formatNumber, formatRelative } from "../../shared/formatters";
import {
  BrowserIcon,
  ChatIcon,
  ClockIcon,
  FlagIcon,
  GearIcon,
  HomeIcon,
  SpiderIcon,
} from "../../shared/LineIcons";
import { useArgusStore } from "../../store";

// 側邊欄：圖示＋名稱＋一行說明；目前頁用淺色底（不用彩色左邊條）
const SECTIONS = [
  { key: "", label: "總覽", hint: "分數與本次變化", Icon: HomeIcon },
  { key: "scans", label: "掃描", hint: "建立與檢視掃描", Icon: SpiderIcon },
  { key: "issues", label: "問題分析", hint: "新增、持續、未出現", Icon: FlagIcon },
  { key: "pages", label: "頁面", hint: "每頁狀態、速度與問題", Icon: BrowserIcon },
  { key: "aeo", label: "AEO 問答", hint: "問題能否在網站找到答案", Icon: ChatIcon },
  { key: "history", label: "歷史報告", hint: "歷次分數與報告", Icon: ClockIcon },
  { key: "settings", label: "專案設定", hint: "預設掃描、網址、封存", Icon: GearIcon },
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
              <section.Icon className="project-sidebar-icon" />
              <span className="project-sidebar-link-text">
                <span className="project-sidebar-link-label">{section.label}</span>
                <span className="project-sidebar-link-hint">{section.hint}</span>
              </span>
            </Link>
          );
        })}
      </nav>
      <SidebarPlanCard />
      <p className="project-sidebar-footer">
        <Link to="/project">產品介紹</Link>
        <Link to="/partners">聯絡我們</Link>
        <Link to="/reviews">使用者評論</Link>
      </p>
    </aside>
  );
}

/**
 * 側邊欄底部的方案卡：目前訂閱方案（/api/billing/subscription/）與點數餘額（store 的 wallet）。
 * 有訂閱時進度條＝餘額／方案每月點數；沒有訂閱時只顯示餘額。
 */
function SidebarPlanCard() {
  const wallet = useArgusStore((s) => s.wallet);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);
  const [subscription, setSubscription] = useState(undefined);

  useEffect(() => {
    if (wallet === null) fetchWallet();
  }, [wallet, fetchWallet]);
  useEffect(() => {
    api
      .get("/billing/subscription/")
      .then((response) => setSubscription(response.data.subscription))
      .catch(() => setSubscription(null));
  }, []);

  const balance = wallet?.balance;
  const active = subscription && subscription.status === "active" ? subscription : null;
  const monthly = active?.plan_monthly_coins || 0;
  const ratio = monthly && balance != null ? Math.min(1, balance / monthly) : null;
  return (
    <section className="project-plan-card" aria-label="目前方案">
      <p className="project-plan-label">目前方案</p>
      <p className="project-plan-name">{subscription === undefined ? "…" : active ? active.plan_name : "未訂閱"}</p>
      {ratio !== null && (
        <span className="project-plan-bar" aria-hidden="true">
          <span style={{ width: `${ratio * 100}%` }} />
        </span>
      )}
      <p className="project-plan-coins">
        {balance == null ? "—" : balance.toLocaleString()}
        {monthly ? ` / ${monthly.toLocaleString()}` : ""} coin
      </p>
      {active?.current_period_end && (
        <p className="project-plan-hint">下次贈點 {formatDate(active.current_period_end)}</p>
      )}
      <Link className="project-plan-cta" to="/billing">{active ? "購點與訂閱 →" : "購點或訂閱方案 →"}</Link>
    </section>
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

/**
 * 示範專案的說明列：資料來自虛構網站的三次真實掃描（後端 apps/scans/demo/），唯讀。
 * 每個分頁都顯示，讓使用者知道這不是自己的網站，並直接引導新增自己的網站或封存示範專案。
 */
function DemoProjectBanner({ project }) {
  const navigate = useNavigate();
  const removeProject = useArgusStore((s) => s.removeProject);
  const [archiving, setArchiving] = useState(false);
  const [error, setError] = useState("");

  async function archive() {
    setArchiving(true);
    setError("");
    try {
      await api.delete(`/projects/${project.id}/`);
      removeProject(project.id);
      navigate("/projects");
    } catch (err) {
      setError(apiErrorMessage(err, "封存失敗，請稍後再試。"));
      setArchiving(false);
    }
  }

  return (
    <div className="project-demo-banner" role="note">
      <span className="project-demo-badge">示範專案</span>
      <p>
        這是 Argus 的示範：「{project.name}」是虛構網站，資料來自它的三次真實掃描。
        總覽、問題分析、頁面、AEO 問答、報告與修正產出都能點開看看；示範專案不能建立新掃描。
      </p>
      <div className="project-demo-actions">
        <Link className="primary-button" to="/projects/new">新增你的網站</Link>
        <button type="button" className="secondary-button" onClick={archive} disabled={archiving}>
          {archiving ? "封存中…" : "看完了，封存示範"}
        </button>
      </div>
      {error && <p className="error-text" role="alert">{error}</p>}
    </div>
  );
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
        {project.is_demo && !project.archived_at && <DemoProjectBanner project={project} />}
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
          {project.is_demo && <span className="project-demo-badge">示範</span>}
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
    <div className="panel project-table-wrap">
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
/** 把使用者輸入的網址正規化成「網站」（協定＋網域＋連接埠）；沒打協定時補 https://。 */
export function parseSiteUrl(raw) {
  const value = (raw || "").trim();
  if (!value) return null;
  for (const candidate of [value, `https://${value}`]) {
    try {
      const url = new URL(candidate);
      if ((url.protocol === "http:" || url.protocol === "https:") && url.hostname.includes(".")) {
        return { href: url.href, origin: url.origin, hostname: url.hostname.toLowerCase() };
      }
    } catch {
      // 試下一種寫法
    }
  }
  return null;
}

// 整站掃描的頁數上限（與掃描表單的 MAX_SITE_SCAN_PAGES 一致），用來估算每次掃描的點數上限
const MAX_SITE_PAGES = 50;

const AFTER_CREATE_OPTIONS = [
  { value: "scan", label: "前往建立第一次掃描", hint: "以下方的預設設定開好掃描表單，確認後再送出（送出前不扣點）" },
  { value: "overview", label: "先到專案總覽", hint: "之後再從「掃描」分頁建立" },
];

/**
 * 新增網站專案：網址與名稱、專案說明、預設掃描設定（範圍、維度、模式）、建立後要做什麼。
 * 右側即時預覽：網站、同網站是否已有專案、網域驗證狀態、以預設設定掃一次大約多少點數。
 */
function ProjectCreatePage() {
  const navigate = useNavigate();
  const upsertProject = useArgusStore((s) => s.upsertProject);
  const setCurrentProject = useArgusStore((s) => s.setCurrentProject);
  const projects = useArgusStore((s) => s.projects);
  const wallet = useArgusStore((s) => s.wallet);
  const fetchWallet = useArgusStore((s) => s.fetchWallet);
  const [startUrl, setStartUrl] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [defaults, setDefaults] = useState(DEFAULT_SCAN_SETTINGS);
  const [afterCreate, setAfterCreate] = useState("scan");
  const [verifiedDomains, setVerifiedDomains] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [existing, setExisting] = useState(null);

  useEffect(() => {
    if (!wallet) fetchWallet?.();
    let cancelled = false;
    fetchVerifiedDomains()
      .then((data) => !cancelled && setVerifiedDomains(data.results || []))
      .catch(() => !cancelled && setVerifiedDomains([]));
    return () => {
      cancelled = true;
    };
    // 只在進頁面時抓一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const site = parseSiteUrl(startUrl);
  const duplicate = site ? (projects || []).find((p) => p.origin === site.origin) : null;
  const domainVerified = site && verifiedDomains
    ? verifiedDomains.some(
        (item) => item.is_effectively_verified && (site.hostname === item.domain || site.hostname.endsWith(`.${item.domain}`)),
      )
    : null;
  const coinPerCategory = wallet?.coin_per_category ?? 2;
  const pages = defaults.default_scope === "single" ? 1 : MAX_SITE_PAGES;
  const estimate = pages * defaults.default_categories.length * coinPerCategory;
  const urlInvalid = Boolean(startUrl.trim()) && !site;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setExisting(null);
    try {
      const response = await api.post("/projects/", {
        start_url: startUrl,
        name,
        description,
        ...defaults,
      });
      upsertProject(response.data);
      setCurrentProject(response.data.id);
      navigate(projectPath(response.data.id, afterCreate === "scan" ? "scans" : ""));
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
      <header className="project-create-head">
        <p className="eyebrow">新增網站專案</p>
        <h1 className="project-page-title">你要管理哪個網站？</h1>
        <p className="project-page-sub">
          一個專案對應一個網站（同一個協定、網域與連接埠）。歷次掃描的分數變化、問題與報告都會保存在專案裡；
          下面的掃描設定是之後建立掃描時的預設值，每次仍可調整，建立專案本身不扣點。
        </p>
      </header>

      <form className="project-create-layout" onSubmit={handleSubmit}>
        <div className="project-create-main">
          <section className="panel project-create-section">
            <h2 className="project-create-step"><span>1</span>網站資料</h2>
            <label className="project-field" htmlFor="project-url">
              <span>網站網址 <em className="project-required">必填</em></span>
              <input
                id="project-url"
                className="input"
                type="text"
                inputMode="url"
                placeholder="https://example.com/"
                value={startUrl}
                onChange={(event) => setStartUrl(event.target.value)}
                aria-invalid={urlInvalid || undefined}
                aria-describedby="project-url-hint"
                required
              />
              <small id="project-url-hint">
                {urlInvalid ? "請輸入完整網址，例如 https://example.com/。" : "也是之後掃描的起始網址；可以是首頁或網站內的任何一頁。"}
              </small>
            </label>
            <label className="project-field" htmlFor="project-name">
              <span>專案名稱</span>
              <input
                id="project-name"
                className="input"
                type="text"
                maxLength={80}
                placeholder={site ? site.hostname : "預設為網域名稱"}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="project-field" htmlFor="project-description">
              <span>專案說明</span>
              <textarea
                id="project-description"
                className="input"
                rows={3}
                maxLength={300}
                placeholder="例如：公司官網、2025 改版後的電商網站、客戶 A 的活動頁"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <small>選填，最多 300 字；網站還沒掃描前會顯示在專案頁首。</small>
            </label>
          </section>

          <section className="panel project-create-section">
            <h2 className="project-create-step"><span>2</span>預設掃描設定</h2>
            <ScanDefaultsFields
              value={defaults}
              onChange={setDefaults}
              domainVerified={domainVerified}
              hostname={site?.hostname || ""}
              idPrefix="create"
            />
          </section>

          <section className="panel project-create-section">
            <h2 className="project-create-step"><span>3</span>建立之後</h2>
            <div className="project-choice-row">
              {AFTER_CREATE_OPTIONS.map((option) => (
                <label key={option.value} className={`project-choice ${afterCreate === option.value ? "active" : ""}`}>
                  <input
                    type="radio"
                    name="after-create"
                    value={option.value}
                    checked={afterCreate === option.value}
                    onChange={() => setAfterCreate(option.value)}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <small>{option.hint}</small>
                  </span>
                </label>
              ))}
            </div>
          </section>
        </div>

        <aside className="project-create-aside">
          <section className="panel project-create-preview" aria-live="polite">
            <p className="project-create-preview-label">專案預覽</p>
            <div className="project-create-site">
              <SiteFavicon project={{ name: name || site?.hostname || "?", favicon: "" }} size="lg" />
              <div>
                <strong>{name.trim() || site?.hostname || "尚未輸入網址"}</strong>
                <small>{site ? site.origin : "輸入網址後顯示網站"}</small>
              </div>
            </div>
            <dl className="project-create-facts">
              <div>
                <dt>網域驗證</dt>
                <dd>
                  {!site
                    ? "—"
                    : domainVerified === null
                      ? "檢查中…"
                      : domainVerified
                        ? <span className="project-create-ok">已驗證，可做主動測試</span>
                        : <span>未驗證（只能被動偵測）</span>}
                </dd>
              </div>
              <div>
                <dt>預設範圍</dt>
                <dd>{defaults.default_scope === "single" ? "單一頁面" : `整個網站（最多 ${MAX_SITE_PAGES} 頁）`}</dd>
              </div>
              <div>
                <dt>預設維度</dt>
                <dd>{defaults.default_categories.map((c) => CATEGORY_LABELS[c] || c).join("、")}</dd>
              </div>
              <div>
                <dt>每次掃描約</dt>
                <dd>
                  <strong>最多 {formatNumber(estimate)} coin</strong>
                  <small>依實際頁數結算，多扣的會退回</small>
                </dd>
              </div>
              <div>
                <dt>目前餘額</dt>
                <dd>{wallet ? `${formatNumber(wallet.balance ?? 0)} coin` : "—"}</dd>
              </div>
            </dl>
            {wallet && (wallet.balance ?? 0) < estimate && (
              <p className="project-field-note" role="note">
                目前餘額不足以用這組預設掃描整個網站（依實際頁數結算，頁數少時可能夠用）。
                可改成單一頁面或減少維度，或<Link className="project-text-link" to="/billing">購點</Link>。
                建立專案本身不扣點。
              </p>
            )}
            {duplicate && (
              <p className="project-field-note" role="note">
                這個網站已經是你的專案「{duplicate.name}」。
                <Link className="project-text-link" to={projectPath(duplicate.id)}>前往該專案 →</Link>
              </p>
            )}
            {error && <p className="error-text" role="alert">{error}</p>}
            {existing && (
              <Link className="secondary-button" to={projectPath(existing.id)}>前往「{existing.name}」</Link>
            )}
            <button type="submit" className="primary-button project-create-submit" disabled={submitting || !site || Boolean(duplicate)}>
              {submitting ? "建立中，正在取得網站圖示…" : afterCreate === "scan" ? "建立專案並前往掃描" : "建立專案"}
            </button>
            <p className="project-create-note">
              只掃描你擁有或已取得授權的網站；建立掃描時會再確認授權範圍。
            </p>
          </section>
        </aside>
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
