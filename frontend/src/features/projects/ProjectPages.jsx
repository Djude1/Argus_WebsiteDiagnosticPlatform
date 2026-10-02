// 網站專案的分頁：總覽、掃描、問題分析、頁面、AEO 問答、歷史報告、專案設定（外框見 ProjectWorkspace.jsx）。
// 後端：/api/projects/<id>/（overview／issues）與 /api/scans/?project=<id>。
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import {
  AeoSummary,
  CATEGORY_ORDER,
  CategoryPanel,
  CountBars,
  RecentScans,
  ScanStatsList,
} from "../../components/projects/DashboardWidgets.jsx";
import { AnnouncementToast, ScoreRing } from "../../components/projects/OverviewWidgets.jsx";
import SiteFavicon from "../../components/projects/SiteFavicon.jsx";
import AeoAnswerPanel from "../../components/scans/AeoAnswerPanel.jsx";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges.jsx";
import {
  CATEGORY_LABELS,
  LineChart,
  SEVERITY_LABEL,
  SeverityBarChart,
  SEVERITY_ORDER,
  apiErrorMessage,
  isInProgress,
  useConfirmDialogs,
} from "../../shared/AppShared.jsx";
import { formatDate, formatDateTime, formatRelative } from "../../shared/formatters";
import { useArgusStore } from "../../store";
import { ScanJobForm, ScanList, scanProgress } from "../scans/ScanExperience.jsx";
import { projectPath } from "./ProjectWorkspace.jsx";

const OVERVIEW_POLL_MS = 5000;
const SCANS_POLL_MS = 3000;
const SCAN_LIST_PARAMS = { page_size: 200 };

function SeverityChip({ severity }) {
  return <span className={`project-sev sev-${severity}`}>{SEVERITY_LABEL[severity] || severity}</span>;
}

function DeltaText({ delta }) {
  if (delta === null || delta === undefined) return null;
  if (delta === 0) return <span className="project-delta">持平</span>;
  return (
    <span className={`project-delta ${delta > 0 ? "is-up" : "is-down"}`}>
      {delta > 0 ? `▲ +${delta}` : `▼ ${delta}`}
    </span>
  );
}

/** 該專案的全部掃描（新→舊）；有進行中的掃描時自動輪詢。 */
function useProjectScans(projectId, pollMs = SCANS_POLL_MS) {
  const [scans, setScans] = useState(null);
  const load = useCallback(async () => {
    try {
      const response = await api.get("/scans/", { params: { ...SCAN_LIST_PARAMS, project: projectId } });
      setScans(response.data.results || response.data);
    } catch {
      setScans((current) => current || []);
    }
  }, [projectId]);
  useEffect(() => {
    load();
  }, [load]);
  const hasInProgress = (scans || []).some((scan) => isInProgress(scan.status));
  useEffect(() => {
    if (!hasInProgress) return undefined;
    const timer = setInterval(load, pollMs);
    return () => clearInterval(timer);
  }, [hasInProgress, load, pollMs]);
  return { scans, reload: load };
}

// 公告以非阻塞 toast 顯示（原本在 Dashboard），關閉過的記在瀏覽器不再出現
function useAnnouncements() {
  const [toasts, setToasts] = useState([]);
  useEffect(() => {
    api
      .get("/admin/announcements/active/")
      .then((response) => {
        const all = response.data.announcements || [];
        setToasts(all.filter((ann) => {
          try {
            return !localStorage.getItem(`ann_dismissed_${ann.id}`);
          } catch {
            return true;
          }
        }));
      })
      .catch(() => {});
  }, []);
  function dismiss(annId) {
    try {
      localStorage.setItem(`ann_dismissed_${annId}`, "1");
    } catch {
      // 儲存空間受限時仍允許關閉本次顯示的公告
    }
    setToasts((prev) => prev.filter((ann) => ann.id !== annId));
  }
  return { toasts, dismiss };
}

// ============================================================
// 總覽
// ============================================================

/** 進行中的掃描：目前階段與整體進度（與掃描詳情頁同一個公式 scanProgress）。 */
function ActiveScanBanner({ scan }) {
  const { current, percent } = scanProgress(scan.status, scan.progress);
  return (
    <section className="project-active-banner" aria-live="polite">
      <div className="project-active-head">
        <ScanStatusBadge status={scan.status} />
        <span className="project-active-text">
          正在{current?.title || current?.label || "掃描"}
          {percent != null ? ` · ${percent}%` : ""}
          <small>（{formatRelative(scan.created_at)}建立，完成後總覽會自動更新）</small>
        </span>
        <Link className="secondary-button" to={`/scans/${scan.id}`}>查看進度</Link>
      </div>
      <div
        className={`project-active-bar ${percent == null ? "is-indeterminate" : ""}`}
        role="progressbar"
        aria-label="掃描進度"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
      >
        <span style={{ width: `${percent ?? 30}%` }} />
      </div>
    </section>
  );
}

function ProjectOverviewPage() {
  const { project } = useOutletContext();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const { toasts, dismiss } = useAnnouncements();

  const load = useCallback(async () => {
    try {
      const response = await api.get(`/projects/${project.id}/overview/`);
      setData(response.data);
      setError("");
    } catch {
      setError("無法載入專案總覽。");
    }
  }, [project.id]);

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  // 有掃描在跑時定時更新，完成後總覽自動換成新結果
  const running = Boolean(data?.active_scan);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(load, OVERVIEW_POLL_MS);
    return () => clearInterval(timer);
  }, [running, load]);

  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;
  if (!data) return <section className="panel"><p className="hint-text">載入專案總覽中…</p></section>;

  const latest = data.latest_scan;
  const previous = data.previous_scan;
  const delta =
    latest && previous && latest.overall_score != null && previous.overall_score != null
      ? latest.overall_score - previous.overall_score
      : null;
  const issuesPath = projectPath(project.id, "issues");

  return (
    <div className="project-page">
      <header className="project-page-head project-overview-head">
        <SiteFavicon project={project} size="lg" />
        <div>
          <h1 className="project-page-title">{project.name}</h1>
          <p className="project-page-sub">
            <a href={project.origin} target="_blank" rel="noopener noreferrer" className="project-origin-link">
              {project.origin}
            </a>
            {" · "}共 {data.scans_count} 次掃描{" · "}
            <Link className="project-text-link" to={projectPath(project.id, "scans")}>建立新掃描</Link>
          </p>
        </div>
      </header>

      {data.active_scan && <ActiveScanBanner scan={data.active_scan} />}

      {!latest ? (
        <section className="panel project-empty">
          <p className="project-empty-title">這個網站還沒有完成的掃描</p>
          <p className="hint-text">完成第一次掃描後，這裡會顯示網站分數、各維度分數、問題與改善建議。</p>
          {!data.active_scan && (
            <Link className="primary-button" to={projectPath(project.id, "scans")}>建立第一次掃描</Link>
          )}
        </section>
      ) : (
        <>
          <div className="project-kpis">
            <section className="project-kpi is-score">
              <ScoreRing value={latest.overall_score} label="網站分數" />
              <div>
                <p className="project-kpi-label">與上次相比</p>
                <p className="project-kpi-value"><DeltaText delta={delta} />{delta === null && "—"}</p>
                <p className="project-kpi-hint">
                  {previous ? `上次 ${formatDate(previous.completed_at)}：${previous.overall_score ?? "—"} 分` : "第一次完成的掃描"}
                </p>
              </div>
            </section>
            <section className="project-kpi">
              <p className="project-kpi-label">目前問題</p>
              <p className="project-kpi-value">{latest.issues_count}</p>
              <p className="project-sev-row">
                {SEVERITY_ORDER.filter((sev) => data.severity_counts[sev]).map((sev) => (
                  <span key={sev}><SeverityChip severity={sev} /> {data.severity_counts[sev]}</span>
                ))}
              </p>
            </section>
            <section className="project-kpi">
              <p className="project-kpi-label">與上次掃描比較</p>
              {data.changes ? (
                <ul className="project-change-list">
                  <li><Link to={`${issuesPath}?change=new`}>新增 <strong>{data.changes.new}</strong></Link></li>
                  <li><Link to={`${issuesPath}?change=persisting`}>持續 <strong>{data.changes.persisting}</strong></Link></li>
                  <li><Link to={`${issuesPath}#missing`}>本次未出現 <strong>{data.changes.missing}</strong></Link></li>
                </ul>
              ) : (
                <p className="project-kpi-hint">再掃描一次後，這裡會列出新增、持續與未再出現的問題。</p>
              )}
            </section>
            <section className="project-kpi">
              <p className="project-kpi-label">最近一次完成</p>
              <p className="project-kpi-value is-small">{formatRelative(latest.completed_at)}</p>
              <p className="project-kpi-hint">
                {latest.pages_count} 頁 · {latest.categories.map((c) => CATEGORY_LABELS[c]).join("／")}
                {latest.scan_mode === "active" ? " · 主動測試" : ""}
              </p>
              <Link className="project-text-link" to={`/scans/${latest.id}`}>查看這次結果 →</Link>
            </section>
          </div>

          <div className="project-grid-2">
            <section className="panel">
              <div className="project-section-head">
                <h2 className="project-section-title">各維度分數與走勢</h2>
                <span className="project-section-hint">最近 {data.trend.length} 次完成的掃描</span>
              </div>
              <CategoryPanel latest={latest} trend={data.trend} />
            </section>
            <section className="panel">
              <h2 className="project-section-title">網站分數趨勢</h2>
              <LineChart
                data={data.trend.map((point) => ({ label: formatDate(point.completed_at).slice(5), value: point.overall_score }))}
                ariaLabel={`${project.name} 分數趨勢`}
              />
              {data.trend.length < 2 && <p className="hint-text">完成兩次以上掃描後即可看出趨勢。</p>}
            </section>
          </div>

          <div className="project-grid-3">
            <section className="panel">
              <SeverityBarChart severityTotals={data.severity_counts} title="問題嚴重度分布" />
            </section>
            <section className="panel">
              <h2 className="project-section-title">各維度問題數</h2>
              <CountBars
                items={CATEGORY_ORDER.filter((c) => latest.categories.includes(c)).map((c) => ({
                  key: c,
                  label: CATEGORY_LABELS[c],
                  value: latest.category_counts[c] || 0,
                }))}
                emptyText="這次掃描沒有發現問題。"
                linkFor={(item) => `${issuesPath}?category=${item.key}`}
              />
            </section>
            <section className="panel">
              <div className="project-section-head">
                <h2 className="project-section-title">AEO 問答檢測</h2>
                <Link className="project-text-link" to={projectPath(project.id, "aeo")}>逐題結果 →</Link>
              </div>
              <AeoSummary aeo={latest.aeo} />
            </section>
          </div>

          <div className="project-grid-2">
            <section className="panel">
              <div className="project-section-head">
                <h2 className="project-section-title">優先改善建議</h2>
                <Link className="project-text-link" to={issuesPath}>到問題分析 →</Link>
              </div>
              {latest.top_actions.length ? (
                <ol className="project-action-list">
                  {latest.top_actions.map((action) => (
                    <li key={`${action.category}-${action.title}`}>
                      <SeverityChip severity={action.severity} />
                      <span className="project-action-title">{action.title}</span>
                      <span className="project-action-cat">{CATEGORY_LABELS[action.category] || action.category}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="hint-text">這次沒有需要優先處理的項目。</p>
              )}
            </section>
            <section className="panel">
              <div className="project-section-head">
                <h2 className="project-section-title">本次掃描</h2>
                <Link className="project-text-link" to={projectPath(project.id, "pages")}>看每一頁 →</Link>
              </div>
              <ScanStatsList latest={latest} />
              <div className="project-section-head dash-recent-head">
                <h3 className="project-section-title">最近掃描</h3>
                <Link className="project-text-link" to={projectPath(project.id, "history")}>全部 →</Link>
              </div>
              <RecentScans scans={data.recent_scans} />
            </section>
          </div>
        </>
      )}

      {!data.domain_verified && (
        <p className="project-note">
          主動式資安測試需先驗證 {project.hostname} 的網域所有權。
          <Link className="project-text-link" to="/domains">前往網域驗證 →</Link>
        </p>
      )}
      <AnnouncementToast announcements={toasts} onDismiss={dismiss} />
    </div>
  );
}

// ============================================================
// 掃描
// ============================================================

function ProjectScansPage() {
  const { project } = useOutletContext();
  const fetchProjects = useArgusStore((s) => s.fetchProjects);
  const { scans, reload } = useProjectScans(project.id);

  function handleCreated() {
    reload();
    fetchProjects();
  }

  return (
    <div className="project-scans-page">
      <ScanJobForm project={project} onCreated={handleCreated} />
      {scans === null ? (
        <section className="panel"><p className="hint-text">載入掃描中…</p></section>
      ) : (
        <ScanList scans={scans} onRefresh={reload} />
      )}
    </div>
  );
}

// ============================================================
// 問題分析
// ============================================================

const CHANGE_LABELS = { new: "新增", persisting: "持續" };

function FilterChips({ label, options, value, onChange }) {
  return (
    <div className="project-filter" role="group" aria-label={label}>
      <span className="project-filter-label">{label}</span>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`project-chip ${value === option.value ? "active" : ""}`}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined ? ` ${option.count}` : ""}
        </button>
      ))}
    </div>
  );
}

/** 選擇要看哪一次完成的掃描（問題分析與頁面清單共用）；value 空字串＝最新一次。 */
function ScanSelect({ completed, current, value, onChange }) {
  return (
    <label className="project-scan-select">
      <span>掃描</span>
      <select className="input" value={value || String(current.id)} onChange={(event) => onChange(event.target.value)}>
        {completed.length === 0 && <option value={current.id}>{formatDateTime(current.completed_at)}</option>}
        {completed.map((scan, index) => (
          <option key={scan.id} value={scan.id}>
            {formatDateTime(scan.completed_at)}（{scan.overall_score ?? "—"} 分）{index === 0 ? " · 最新" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

const CSV_COLUMNS = [
  ["嚴重度", (issue) => SEVERITY_LABEL[issue.severity] || issue.severity],
  ["維度", (issue) => CATEGORY_LABELS[issue.category] || issue.category],
  ["問題", (issue) => issue.title],
  ["變化", (issue) => CHANGE_LABELS[issue.status] || ""],
  ["連續出現次數", (issue) => issue.streak ?? ""],
  ["受影響頁數", (issue) => issue.pages],
  ["受影響頁面", (issue) => (issue.urls || issue.sample_urls).join(" ")],
  ["怎麼修", (issue) => issue.remediation || ""],
  ["規則", (issue) => issue.rule_id || ""],
];

/** 問題清單轉 CSV（逗號、引號、換行都正確跳脫）；前置 BOM 讓 Excel 以 UTF-8 開啟中文。 */
export function issuesToCsv(issues) {
  const escape = (value) => {
    const text = String(value ?? "");
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const rows = [CSV_COLUMNS.map(([header]) => header)];
  for (const issue of issues) rows.push(CSV_COLUMNS.map(([, pick]) => pick(issue)));
  return `\uFEFF${rows.map((row) => row.map(escape).join(",")).join("\r\n")}`;
}

function downloadCsv(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** 單一問題：標題列＋可展開的說明、怎麼修與全部受影響頁面。 */
function IssueItem({ issue, scanId }) {
  const urls = issue.urls || issue.sample_urls;
  return (
    <li className="project-issue">
      <SeverityChip severity={issue.severity} />
      <div className="project-issue-body">
        <p className="project-issue-title">
          {issue.title}
          {issue.status && (
            <span className={`project-change-chip is-${issue.status}`}>{CHANGE_LABELS[issue.status]}</span>
          )}
          {issue.streak > 1 && (
            <span
              className={`project-streak-chip ${issue.streak >= 3 ? "is-long" : ""}`}
              title={`自 ${formatDate(issue.since)} 起，連續 ${issue.streak} 次完成的掃描都出現`}
            >
              連續 {issue.streak} 次
            </span>
          )}
        </p>
        <p className="project-issue-meta">
          {CATEGORY_LABELS[issue.category] || issue.category}
          {" · "}
          {issue.pages ? `${issue.pages} 頁` : "站台層級"}
          {issue.streak > 1 ? ` · 自 ${formatDate(issue.since)} 起` : ""}
        </p>
        <details className="project-issue-pages">
          <summary>說明與修補建議{urls.length ? `、受影響頁面（${issue.pages}）` : ""}</summary>
          {issue.description && (
            <div className="project-issue-detail">
              <h4>問題是什麼</h4>
              <p>{issue.description}</p>
            </div>
          )}
          {issue.remediation && (
            <div className="project-issue-detail">
              <h4>怎麼修</h4>
              <p>{issue.remediation}</p>
            </div>
          )}
          {urls.length > 0 && (
            <div className="project-issue-detail">
              <h4>受影響頁面{issue.pages > urls.length ? `（列出 ${urls.length}／${issue.pages}）` : ""}</h4>
              <ul>
                {urls.map((url) => <li key={url}>{url}</li>)}
              </ul>
            </div>
          )}
        </details>
      </div>
      <Link className="project-text-link" to={`/scans/${scanId}?finding=${issue.finding_id}`}>
        查看證據 →
      </Link>
    </li>
  );
}

function ProjectIssuesPage() {
  const { project } = useOutletContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const scanParam = searchParams.get("scan") || "";
  const category = searchParams.get("category") || "all";
  const severity = searchParams.get("severity") || "all";
  const change = searchParams.get("change") || "all";
  const grouped = searchParams.get("group") === "category";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const { scans } = useProjectScans(project.id);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    api
      .get(`/projects/${project.id}/issues/`, { params: scanParam ? { scan: scanParam } : {} })
      .then((response) => !cancelled && setData(response.data))
      .catch(() => !cancelled && setError("無法載入問題分析，這次掃描可能尚未完成。"));
    return () => {
      cancelled = true;
    };
  }, [project.id, scanParam]);

  // 篩選寫在網址上（可分享、重新整理不丟失），但用 replace，不污染上一頁
  function setParam(key, value) {
    const params = new URLSearchParams(searchParams);
    if (!value || value === "all") params.delete(key);
    else params.set(key, value);
    setSearchParams(params, { replace: true });
  }

  const completed = (scans || []).filter((scan) => scan.status === "completed");
  const issues = useMemo(() => data?.issues || [], [data]);
  const filtered = issues.filter(
    (issue) =>
      (category === "all" || issue.category === category) &&
      (severity === "all" || issue.severity === severity) &&
      (change === "all" || issue.status === change),
  );
  const countBy = (key, value) => issues.filter((issue) => issue[key] === value).length;

  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;
  if (!data) return <section className="panel"><p className="hint-text">載入問題分析中…</p></section>;
  if (!data.scan) {
    return (
      <section className="panel project-empty">
        <p className="project-empty-title">還沒有可分析的掃描</p>
        <p className="hint-text">完成一次掃描後，這裡會依規則合併列出問題，並與上一次掃描比較。</p>
        <Link className="primary-button" to={projectPath(project.id, "scans")}>建立掃描</Link>
      </section>
    );
  }

  return (
    <div className="project-page">
      <header className="project-page-head">
        <div>
          <p className="eyebrow">問題分析</p>
          <h1 className="project-page-title">{issues.length} 個問題</h1>
          {issues.some((issue) => issue.streak >= 3) && (
            <p className="project-page-alert">
              有 {issues.filter((issue) => issue.streak >= 3).length} 個問題已連續 3 次以上掃描都出現，建議優先處理。
            </p>
          )}
          <p className="project-page-sub">
            {data.compared_with
              ? `與 ${formatDateTime(data.compared_with.completed_at)} 的掃描比較。同一條規則出現在多頁只算一個問題。`
              : "這是此網站第一次完成的掃描，下次掃描起會標示新增與持續的問題。"}
          </p>
        </div>
        <ScanSelect
          completed={completed}
          current={data.scan}
          value={scanParam}
          onChange={(value) => setParam("scan", value)}
        />
      </header>

      <section className="panel project-filters">
        <div className="project-filter-toolbar">
          <FilterChips
            label="顯示"
            value={grouped ? "category" : "all"}
            onChange={(value) => setParam("group", value)}
            options={[
              { value: "all", label: "依嚴重度排序" },
              { value: "category", label: "依維度分組" },
            ]}
          />
          <button
            type="button"
            className="secondary-button"
            onClick={() => downloadCsv(`${project.hostname}-issues-scan-${data.scan.id}.csv`, issuesToCsv(filtered))}
            disabled={!filtered.length}
          >
            匯出 CSV（{filtered.length}）
          </button>
        </div>
        <FilterChips
          label="維度"
          value={category}
          onChange={(value) => setParam("category", value)}
          options={[
            { value: "all", label: "全部" },
            ...CATEGORY_ORDER.map((c) => ({ value: c, label: CATEGORY_LABELS[c], count: countBy("category", c) })),
          ]}
        />
        <FilterChips
          label="嚴重度"
          value={severity}
          onChange={(value) => setParam("severity", value)}
          options={[
            { value: "all", label: "全部" },
            ...SEVERITY_ORDER.map((s) => ({ value: s, label: SEVERITY_LABEL[s], count: countBy("severity", s) })),
          ]}
        />
        {data.compared_with && (
          <FilterChips
            label="變化"
            value={change}
            onChange={(value) => setParam("change", value)}
            options={[
              { value: "all", label: "全部" },
              { value: "new", label: "新增", count: countBy("status", "new") },
              { value: "persisting", label: "持續", count: countBy("status", "persisting") },
            ]}
          />
        )}
      </section>

      <section className="panel">
        {filtered.length === 0 ? (
          <p className="hint-text">{issues.length ? "沒有符合篩選條件的問題。" : "這次掃描沒有發現問題。"}</p>
        ) : grouped ? (
          CATEGORY_ORDER.filter((c) => filtered.some((issue) => issue.category === c)).map((c) => {
            const items = filtered.filter((issue) => issue.category === c);
            return (
              <div key={c} className="project-issue-group">
                <h2 className="project-issue-group-title">
                  {CATEGORY_LABELS[c]}<span>{items.length} 個問題</span>
                </h2>
                <ul className="project-issue-list">
                  {items.map((issue) => <IssueItem key={issue.key} issue={issue} scanId={data.scan.id} />)}
                </ul>
              </div>
            );
          })
        ) : (
          <ul className="project-issue-list">
            {filtered.map((issue) => <IssueItem key={issue.key} issue={issue} scanId={data.scan.id} />)}
          </ul>
        )}
      </section>

      {data.missing.length > 0 && (
        <section className="panel" id="missing">
          <h2 className="project-section-title">本次未出現（{data.missing.length}）</h2>
          <p className="hint-text">
            上一次掃描有、這次沒有出現的問題（只列這次仍有檢查的維度）。可能已修好，
            也可能是這次沒爬到相關頁面或頁面被阻擋，請到該頁確認。
          </p>
          <ul className="project-issue-list is-muted">
            {data.missing.map((issue) => (
              <li key={issue.key} className="project-issue">
                <SeverityChip severity={issue.severity} />
                <div className="project-issue-body">
                  <p className="project-issue-title">{issue.title}</p>
                  <p className="project-issue-meta">{CATEGORY_LABELS[issue.category] || issue.category}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ============================================================
// 頁面（每一頁的狀態、載入時間與問題）
// ============================================================

const SLOW_PAGE_MS = 3000;
const PAGE_FILTERS = {
  all: { label: "全部", test: () => true },
  issues: { label: "有問題", test: (page) => page.findings > 0 },
  errors: { label: "錯誤／被阻擋", test: (page) => Boolean(page.blocked_reason) || (page.status_code ?? 0) >= 400 },
  slow: { label: `載入慢（> ${SLOW_PAGE_MS / 1000} 秒）`, test: (page) => (page.load_time_ms ?? 0) > SLOW_PAGE_MS },
};
const PAGE_SORTS = {
  url: { label: "頁面", value: (page) => page.url },
  status: { label: "狀態", value: (page) => page.status_code ?? 999 },
  load: { label: "載入時間", value: (page) => page.load_time_ms ?? -1 },
  issues: { label: "問題", value: (page) => page.findings * 10 + (5 - (SEVERITY_ORDER.indexOf(page.max_severity) + 1 || 5)) },
};

function statusTone(page) {
  if (page.blocked_reason) return "is-bad";
  const code = page.status_code ?? 0;
  if (code >= 400 || code === 0) return "is-bad";
  if (code >= 300) return "is-warn";
  return "is-good";
}

/** 截圖預覽：展開時才用 API 取圖（需要登入，不能直接用 <img src>）。 */
function PageScreenshot({ scanId, pageId }) {
  const [src, setSrc] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url = null;
    let cancelled = false;
    api
      .get(`/scans/${scanId}/pages/${pageId}/screenshot/`, { responseType: "blob" })
      .then((response) => {
        if (cancelled) return;
        url = URL.createObjectURL(response.data);
        setSrc(url);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [scanId, pageId]);
  if (failed) return <p className="hint-text">截圖無法載入（可能已超過保留期限）。</p>;
  if (!src) return <p className="hint-text">載入截圖中…</p>;
  return <img className="project-page-shot" src={src} alt="此頁掃描當下的截圖" />;
}

/**
 * /projects/:id/aeo：AEO 問答檢測（原本塞在掃描詳情最下方）。
 * 依網站內容出題，逐題判定能否在網站上找到答案並附原文；可選看哪一次完成的掃描、依判定篩選。
 */
function ProjectAeoPage() {
  const { project } = useOutletContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const scanParam = searchParams.get("scan") || "";
  const { scans } = useProjectScans(project.id);
  const [scan, setScan] = useState(null);
  const [error, setError] = useState("");
  const completed = (scans || []).filter((item) => item.status === "completed");
  const targetId = scanParam || (completed[0] ? String(completed[0].id) : "");

  useEffect(() => {
    if (!targetId) return undefined;
    let cancelled = false;
    setScan(null);
    setError("");
    api
      .get(`/scans/${targetId}/`)
      .then((response) => !cancelled && setScan(response.data))
      .catch(() => !cancelled && setError("無法載入這次掃描的 AEO 結果。"));
    return () => {
      cancelled = true;
    };
  }, [targetId]);

  if (scans === null) return <section className="panel"><p className="hint-text">載入中…</p></section>;
  if (!completed.length) {
    return (
      <section className="panel project-empty">
        <p className="project-empty-title">還沒有完成的掃描</p>
        <p className="hint-text">勾選 AEO 維度完成一次掃描後，這裡會列出依網站內容建立的問題，以及每一題能否在網站上找到答案。</p>
        <Link className="primary-button" to={projectPath(project.id, "scans")}>建立掃描</Link>
      </section>
    );
  }
  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;

  const report = scan?.aeo_report;
  const checked = scan ? (scan.categories || []).includes("aeo") : true;
  const aeoScore = scan?.category_scores?.aeo;
  return (
    <div className="project-page">
      <header className="project-page-head">
        <div>
          <h1 className="project-page-title">AEO 問答檢測</h1>
          <p className="project-page-sub">
            AI 答案引擎（ChatGPT 搜尋、Perplexity、Google AI 摘要等）會從網站內容直接擷取答案。
            這裡依網站自己的內容出題，檢查每一題能否在已掃描的頁面找到明確答案並附原文；目前以可重現的規則判定。
          </p>
        </div>
        <ScanSelect
          completed={completed}
          current={completed[0]}
          value={targetId}
          onChange={(value) => {
            const params = new URLSearchParams(searchParams);
            if (value === String(completed[0].id)) params.delete("scan");
            else params.set("scan", value);
            setSearchParams(params, { replace: true });
          }}
        />
      </header>
      {!scan ? (
        <section className="panel"><p className="hint-text">載入中…</p></section>
      ) : !checked ? (
        <section className="panel project-empty">
          <p className="project-empty-title">這次掃描沒有勾選 AEO</p>
          <p className="hint-text">建立掃描時勾選 AEO 維度，才會進行問答檢測。</p>
        </section>
      ) : !report?.status ? (
        <section className="panel"><p className="hint-text">這次掃描沒有 AEO 問答檢測結果（可能是較早的掃描）。</p></section>
      ) : (
        <>
          {report.status === "evaluated" && (
            <dl className="project-portfolio">
              <div className="project-portfolio-item">
                <dt>AEO 分數</dt>
                <dd className={scoreToneClass(aeoScore)}>{aeoScore == null ? "—" : Math.round(aeoScore)}</dd>
              </div>
              <div className="project-portfolio-item">
                <dt>題目</dt>
                <dd>{report.questions_total}</dd>
              </div>
              <div className="project-portfolio-item">
                <dt>可從網站找到答案</dt>
                <dd>{report.answered_ratio == null ? "—" : `${Math.round(report.answered_ratio * 100)}%`}</dd>
              </div>
              <div className="project-portfolio-item">
                <dt>答案附有原文</dt>
                <dd>{report.evidence_ratio == null ? "—" : `${Math.round(report.evidence_ratio * 100)}%`}</dd>
              </div>
            </dl>
          )}
          <section className="panel">
            <AeoAnswerPanel report={report} withFilter />
          </section>
          <p className="project-note">
            「無答案」與「資訊不足」代表在這次已掃描的頁面中找不到明確答案；答案若在沒被掃到的頁面，
            請確認該頁可從首頁或選單連到，或已列在 sitemap。
          </p>
        </>
      )}
    </div>
  );
}

function scoreToneClass(score) {
  if (score === null || score === undefined) return "";
  return score >= 80 ? "is-good" : score >= 60 ? "is-medium" : "is-bad";
}

function ProjectPagesPage() {
  const { project } = useOutletContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const scanParam = searchParams.get("scan") || "";
  const filter = PAGE_FILTERS[searchParams.get("filter")] ? searchParams.get("filter") : "all";
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState({ key: "issues", desc: true });
  const [openId, setOpenId] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const { scans } = useProjectScans(project.id);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    api
      .get(`/projects/${project.id}/pages/`, { params: scanParam ? { scan: scanParam } : {} })
      .then((response) => !cancelled && setData(response.data))
      .catch(() => !cancelled && setError("無法載入頁面清單。"));
    return () => {
      cancelled = true;
    };
  }, [project.id, scanParam]);

  function setParam(key, value) {
    const params = new URLSearchParams(searchParams);
    if (!value || value === "all") params.delete(key);
    else params.set(key, value);
    setSearchParams(params, { replace: true });
  }

  function toggleSort(key) {
    setSort((current) => (current.key === key ? { key, desc: !current.desc } : { key, desc: key !== "url" }));
  }

  const pages = useMemo(() => data?.pages || [], [data]);
  const keyword = query.trim().toLowerCase();
  const visible = pages
    .filter(PAGE_FILTERS[filter].test)
    .filter((page) => !keyword || `${page.url} ${page.title}`.toLowerCase().includes(keyword))
    .sort((a, b) => {
      const pick = PAGE_SORTS[sort.key].value;
      const av = pick(a);
      const bv = pick(b);
      const order = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.desc ? -order : order;
    });
  const completed = (scans || []).filter((scan) => scan.status === "completed");

  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;
  if (!data) return <section className="panel"><p className="hint-text">載入頁面清單中…</p></section>;
  if (!data.scan) {
    return (
      <section className="panel project-empty">
        <p className="project-empty-title">還沒有完成的掃描</p>
        <p className="hint-text">完成一次掃描後，這裡會列出每個被檢查的頁面、狀態碼、載入時間與問題數。</p>
        <Link className="primary-button" to={projectPath(project.id, "scans")}>建立掃描</Link>
      </section>
    );
  }

  const avgLoad = (() => {
    const loads = pages.map((page) => page.load_time_ms).filter((ms) => typeof ms === "number");
    return loads.length ? Math.round(loads.reduce((a, b) => a + b, 0) / loads.length) : null;
  })();

  return (
    <div className="project-page">
      <header className="project-page-head">
        <div>
          <p className="eyebrow">頁面</p>
          <h1 className="project-page-title">{pages.length} 個頁面</h1>
          <p className="project-page-sub">
            這次掃描實際檢查的每一頁。平均載入 {avgLoad == null ? "—" : `${(avgLoad / 1000).toFixed(1)} 秒`}
            {data.site_level_findings ? `；另有 ${data.site_level_findings} 個站台層級的發現（不屬於特定頁面，見問題分析）。` : "。"}
          </p>
        </div>
        <ScanSelect completed={completed} current={data.scan} value={scanParam} onChange={(value) => setParam("scan", value)} />
      </header>

      <section className="panel project-filters">
        <FilterChips
          label="篩選"
          value={filter}
          onChange={(value) => setParam("filter", value)}
          options={Object.entries(PAGE_FILTERS).map(([value, item]) => ({
            value,
            label: item.label,
            count: pages.filter(item.test).length,
          }))}
        />
        <label className="project-search">
          <span className="project-sr-only">搜尋頁面</span>
          <input
            type="search"
            className="input"
            placeholder="搜尋網址或頁面標題"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </section>

      <section className="panel">
        {visible.length === 0 ? (
          <p className="hint-text">沒有符合條件的頁面。</p>
        ) : (
          <div className="project-table-wrap">
            <table className="project-table project-pages-table">
              <thead>
                <tr>
                  {Object.entries(PAGE_SORTS).map(([key, item]) => (
                    <th key={key} scope="col" aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
                      <button type="button" className="project-sort" onClick={() => toggleSort(key)}>
                        {item.label}
                        <span aria-hidden="true">{sort.key === key ? (sort.desc ? " ▾" : " ▴") : ""}</span>
                      </button>
                    </th>
                  ))}
                  <th scope="col"><span className="project-sr-only">操作</span></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((page) => {
                  const open = openId === page.id;
                  return (
                    <Fragment key={page.id}>
                      <tr className={open ? "is-open" : ""}>
                        <td className="project-page-cell">
                          <span className="project-page-title-text">{page.title || "（無標題）"}</span>
                          <span className="project-page-url">{page.url}</span>
                        </td>
                        <td>
                          <span className={`project-status ${statusTone(page)}`} title={page.blocked_reason || undefined}>
                            {page.blocked_reason ? "被阻擋" : page.status_code ?? "—"}
                          </span>
                        </td>
                        <td className={(page.load_time_ms ?? 0) > SLOW_PAGE_MS ? "project-slow" : ""}>
                          {page.load_time_ms == null ? "—" : `${(page.load_time_ms / 1000).toFixed(1)} 秒`}
                        </td>
                        <td>
                          {page.findings ? (
                            <span className="project-page-issues">
                              <SeverityChip severity={page.max_severity} /> {page.findings}
                              <small>
                                {CATEGORY_ORDER.filter((c) => page.by_category[c])
                                  .map((c) => `${CATEGORY_LABELS[c]} ${page.by_category[c]}`)
                                  .join("、")}
                              </small>
                            </span>
                          ) : (
                            <span className="project-page-clean">無</span>
                          )}
                        </td>
                        <td>
                          <div className="project-table-actions">
                            <Link className="project-text-link" to={`/scans/${data.scan.id}?page=${page.id}`}>看此頁問題</Link>
                            {page.has_screenshot && (
                              <button
                                type="button"
                                className="project-text-link"
                                aria-expanded={open}
                                onClick={() => setOpenId(open ? null : page.id)}
                              >
                                {open ? "收合截圖" : "截圖"}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                      {open && (
                        <tr className="project-page-preview">
                          <td colSpan={5}>
                            <PageScreenshot scanId={data.scan.id} pageId={page.id} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// ============================================================
// 歷史報告
// ============================================================

function ProjectHistoryPage() {
  const { project } = useOutletContext();
  const { scans } = useProjectScans(project.id);
  const [downloading, setDownloading] = useState(null);
  const [error, setError] = useState("");

  async function downloadReport(scan) {
    setDownloading(scan.id);
    setError("");
    try {
      const response = await api.get(`/scans/${scan.id}/report/`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `argus-scan-${scan.id}-report.docx`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("報告下載失敗，請稍後再試。");
    } finally {
      setDownloading(null);
    }
  }

  if (scans === null) return <section className="panel"><p className="hint-text">載入歷史中…</p></section>;

  const completed = scans.filter((scan) => scan.status === "completed");
  // 每次完成掃描與「前一次完成掃描」的分數差
  const deltaById = new Map();
  completed.forEach((scan, index) => {
    const older = completed[index + 1];
    if (older && scan.overall_score != null && older.overall_score != null) {
      deltaById.set(scan.id, scan.overall_score - older.overall_score);
    }
  });

  return (
    <div className="project-page">
      <header className="project-page-head">
        <div>
          <p className="eyebrow">歷史報告</p>
          <h1 className="project-page-title">歷次掃描</h1>
          <p className="project-page-sub">共 {scans.length} 次，其中 {completed.length} 次完成。完成的掃描可查看問題分析並下載 Word 報告。</p>
        </div>
      </header>
      {completed.length > 1 && (
        <section className="panel">
          <h2 className="project-section-title">分數趨勢</h2>
          <LineChart
            data={completed.slice().reverse().map((scan) => ({ label: formatDate(scan.completed_at).slice(5), value: scan.overall_score }))}
            ariaLabel={`${project.name} 歷次分數`}
          />
        </section>
      )}
      {error && <p className="error-text" role="alert">{error}</p>}
      <section className="panel">
        {scans.length === 0 ? (
          <p className="hint-text">還沒有掃描紀錄。</p>
        ) : (
          <div className="project-table-wrap">
            <table className="project-table">
              <thead>
                <tr>
                  <th scope="col">建立時間</th>
                  <th scope="col">狀態</th>
                  <th scope="col">分數</th>
                  <th scope="col">變化</th>
                  <th scope="col">頁數／發現</th>
                  <th scope="col"><span className="project-sr-only">操作</span></th>
                </tr>
              </thead>
              <tbody>
                {scans.map((scan) => {
                  const done = scan.status === "completed";
                  return (
                    <tr key={scan.id}>
                      <td>{formatDateTime(scan.created_at)}</td>
                      <td><ScanStatusBadge status={scan.status} /></td>
                      <td><ScoreBadge score={scan.overall_score} /></td>
                      <td>{deltaById.has(scan.id) ? <DeltaText delta={deltaById.get(scan.id)} /> : "—"}</td>
                      <td>{scan.pages_count} 頁 · {scan.findings_count} 項</td>
                      <td>
                        <div className="project-table-actions">
                          <Link className="project-text-link" to={`/scans/${scan.id}`}>查看結果</Link>
                          {done && (
                            <Link className="project-text-link" to={`${projectPath(project.id, "issues")}?scan=${scan.id}`}>問題分析</Link>
                          )}
                          {done && (
                            <button
                              type="button"
                              className="project-text-link"
                              onClick={() => downloadReport(scan)}
                              disabled={downloading === scan.id}
                            >
                              {downloading === scan.id ? "產生中…" : "下載報告"}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// ============================================================
// 專案設定
// ============================================================

const SCOPE_OPTIONS = [
  { value: "site", label: "整個網站", hint: "從起始網址爬同網站多頁" },
  { value: "single", label: "單一頁面", hint: "只檢查起始網址這一頁" },
];

/** 專案層級的預設掃描設定：「掃描」分頁的表單以此為初始值，每次掃描仍可調整。 */
function ScanDefaultsForm({ project, setProject }) {
  const [scope, setScope] = useState(project.default_scope);
  const [categories, setCategories] = useState(project.default_categories);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  function toggle(category) {
    const next = categories.includes(category)
      ? categories.filter((item) => item !== category)
      : [...categories, category];
    if (next.length) setCategories(next); // 至少保留一個維度
  }

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const response = await api.patch(`/projects/${project.id}/`, {
        default_scope: scope,
        default_categories: categories,
      });
      setProject(response.data);
      setMessage("已儲存。下次在「掃描」分頁建立掃描時會以此為預設。");
    } catch (err) {
      setError(apiErrorMessage(err, "儲存失敗。"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="panel project-settings-form" onSubmit={save}>
      <h2 className="project-section-title">預設掃描設定</h2>
      <fieldset className="project-fieldset">
        <legend>掃描範圍</legend>
        <div className="project-choice-row">
          {SCOPE_OPTIONS.map((option) => (
            <label key={option.value} className={`project-choice ${scope === option.value ? "active" : ""}`}>
              <input
                type="radio"
                name="default-scope"
                value={option.value}
                checked={scope === option.value}
                onChange={() => setScope(option.value)}
              />
              <span>
                <strong>{option.label}</strong>
                <small>{option.hint}</small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="project-fieldset">
        <legend>掃描維度（至少一項）</legend>
        <div className="project-choice-row">
          {CATEGORY_ORDER.map((category) => (
            <label key={category} className={`project-choice is-compact ${categories.includes(category) ? "active" : ""}`}>
              <input
                type="checkbox"
                checked={categories.includes(category)}
                onChange={() => toggle(category)}
              />
              <span><strong>{CATEGORY_LABELS[category]}</strong></span>
            </label>
          ))}
        </div>
      </fieldset>
      {error && <p className="error-text" role="alert">{error}</p>}
      {message && <p className="project-success" role="status">{message}</p>}
      <button type="submit" className="secondary-button" disabled={saving}>{saving ? "儲存中…" : "儲存預設"}</button>
    </form>
  );
}

function ProjectSettingsPage() {
  const { project, setProject } = useOutletContext();
  const navigate = useNavigate();
  const removeProject = useArgusStore((s) => s.removeProject);
  const { confirmDialog, dialogHost } = useConfirmDialogs();
  const [name, setName] = useState(project.name);
  const [startUrl, setStartUrl] = useState(project.start_url);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [domainVerified, setDomainVerified] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get(`/projects/${project.id}/overview/`)
      .then((response) => !cancelled && setDomainVerified(response.data.domain_verified))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const response = await api.patch(`/projects/${project.id}/`, { name, start_url: startUrl });
      setProject(response.data);
      setStartUrl(response.data.start_url);
      setMessage("已儲存。");
    } catch (err) {
      setError(apiErrorMessage(err, "儲存失敗。"));
    } finally {
      setSaving(false);
    }
  }

  async function archive() {
    const ok = await confirmDialog(
      `封存「${project.name}」？專案會從清單與切換器移除，掃描、報告與點數紀錄都會保留；之後新增同一個網站或再掃描它時會自動恢復。`,
      { danger: true },
    );
    if (!ok) return;
    try {
      await api.delete(`/projects/${project.id}/`);
      removeProject(project.id);
      navigate("/projects");
    } catch (err) {
      setError(apiErrorMessage(err, "封存失敗。"));
    }
  }

  return (
    <div className="project-page">
      <header className="project-page-head">
        <div>
          <p className="eyebrow">專案設定</p>
          <h1 className="project-page-title">{project.name}</h1>
          <p className="project-page-sub">{project.origin} · 建立於 {formatDate(project.created_at)}</p>
        </div>
      </header>
      <form className="panel project-settings-form" onSubmit={save}>
        <h2 className="project-section-title">基本資料</h2>
        <label className="project-field" htmlFor="project-setting-name">
          <span>專案名稱</span>
          <input id="project-setting-name" className="input" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label className="project-field" htmlFor="project-setting-url">
          <span>起始網址</span>
          <input id="project-setting-url" className="input" value={startUrl} onChange={(event) => setStartUrl(event.target.value)} required />
          <small>新掃描的預設網址，必須在 {project.origin} 內。網站換了網域請新增專案。</small>
        </label>
        {error && <p className="error-text" role="alert">{error}</p>}
        {message && <p className="project-success" role="status">{message}</p>}
        <button type="submit" className="primary-button" disabled={saving}>{saving ? "儲存中…" : "儲存變更"}</button>
      </form>

      <ScanDefaultsForm project={project} setProject={setProject} />

      <section className="panel">
        <h2 className="project-section-title">網域所有權</h2>
        {domainVerified === null ? (
          <p className="hint-text">檢查中…</p>
        ) : domainVerified ? (
          <p>已可對 {project.hostname} 進行主動式資安測試。</p>
        ) : (
          <p>
            尚未驗證 {project.hostname}，目前只能做被動檢查。
            <Link className="project-text-link" to="/domains">前往網域驗證 →</Link>
          </p>
        )}
      </section>

      {!project.archived_at && (
        <section className="panel project-danger-zone">
          <h2 className="project-section-title">封存專案</h2>
          <p className="hint-text">不會刪除任何掃描、報告或點數紀錄。</p>
          <button type="button" className="secondary-button project-danger-button" onClick={archive}>封存這個專案</button>
        </section>
      )}
      {dialogHost}
    </div>
  );
}

export {
  ProjectHistoryPage,
  ProjectIssuesPage,
  ProjectOverviewPage,
  ProjectPagesPage,
  ProjectAeoPage,
  ProjectScansPage,
  ProjectSettingsPage,
};
