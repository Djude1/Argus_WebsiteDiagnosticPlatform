// 網站專案的五個分頁：總覽、掃描、問題分析、歷史報告、專案設定（外框見 ProjectWorkspace.jsx）。
// 後端：/api/projects/<id>/（overview／issues）與 /api/scans/?project=<id>。
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useOutletContext, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { AnnouncementToast, ScoreRing } from "../../components/projects/OverviewWidgets.jsx";
import { ScanStatusBadge, ScoreBadge } from "../../components/scans/ScanBadges.jsx";
import {
  CATEGORY_LABELS,
  LineChart,
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  apiErrorMessage,
  isInProgress,
  useConfirmDialogs,
} from "../../shared/AppShared.jsx";
import { formatDate, formatDateTime, formatRelative } from "../../shared/formatters";
import { useArgusStore } from "../../store";
import { ScanJobForm, ScanList, scanProgress } from "../scans/ScanExperience.jsx";
import { projectPath } from "./ProjectWorkspace.jsx";

const CATEGORY_ORDER = ["seo", "aeo", "geo", "ux", "security"];
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

function CategoryScores({ latest }) {
  const scores = latest.category_scores || {};
  return (
    <ul className="project-category-list">
      {CATEGORY_ORDER.map((category) => {
        const checked = latest.categories.includes(category);
        const score = scores[category];
        let note = "";
        if (!checked) note = "本次未勾選";
        else if (score === undefined || score === null) {
          note = category === "aeo" && latest.aeo_status === "insufficient" ? "未評估（內容不足）" : "未評估";
        }
        const tone = score >= 80 ? "good" : score >= 60 ? "medium" : "bad";
        return (
          <li key={category} className="project-category-row">
            <span className="project-category-name">{CATEGORY_LABELS[category]}</span>
            <span className="project-category-bar" aria-hidden="true">
              {!note && (
                <span className={`project-category-fill tone-${tone}`} style={{ width: `${score}%` }} />
              )}
            </span>
            <span className="project-category-score">{note || Math.round(score)}</span>
          </li>
        );
      })}
    </ul>
  );
}

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
  const navigate = useNavigate();
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
      <header className="project-page-head">
        <div>
          <p className="eyebrow">總覽</p>
          <h1 className="project-page-title">{project.name}</h1>
          <p className="project-page-sub">{project.origin} · 共 {data.scans_count} 次掃描</p>
        </div>
        <button type="button" className="primary-button" onClick={() => navigate(projectPath(project.id, "scans"))}>
          開始新掃描
        </button>
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
              <h2 className="project-section-title">各維度分數</h2>
              <CategoryScores latest={latest} />
            </section>
            <section className="panel">
              <h2 className="project-section-title">分數趨勢</h2>
              <LineChart
                data={data.trend.map((point) => ({ label: formatDate(point.completed_at).slice(5), value: point.overall_score }))}
                ariaLabel={`${project.name} 分數趨勢`}
              />
              {data.trend.length < 2 && <p className="hint-text">完成兩次以上掃描後即可看出趨勢。</p>}
            </section>
          </div>

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

function ProjectIssuesPage() {
  const { project } = useOutletContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const scanParam = searchParams.get("scan") || "";
  const category = searchParams.get("category") || "all";
  const severity = searchParams.get("severity") || "all";
  const change = searchParams.get("change") || "all";
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
        <label className="project-scan-select">
          <span>掃描</span>
          <select className="input" value={scanParam || String(data.scan.id)} onChange={(event) => setParam("scan", event.target.value)}>
            {completed.length === 0 && <option value={data.scan.id}>{formatDateTime(data.scan.completed_at)}</option>}
            {completed.map((scan, index) => (
              <option key={scan.id} value={scan.id}>
                {formatDateTime(scan.completed_at)}（{scan.overall_score ?? "—"} 分）{index === 0 ? " · 最新" : ""}
              </option>
            ))}
          </select>
        </label>
      </header>

      <section className="panel project-filters">
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
        ) : (
          <ul className="project-issue-list">
            {filtered.map((issue) => (
              <li key={issue.key} className="project-issue">
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
                  {issue.sample_urls.length > 0 && (
                    <details className="project-issue-pages">
                      <summary>受影響頁面{issue.pages > issue.sample_urls.length ? `（列出 ${issue.sample_urls.length}／${issue.pages}）` : ""}</summary>
                      <ul>
                        {issue.sample_urls.map((url) => <li key={url}>{url}</li>)}
                      </ul>
                    </details>
                  )}
                </div>
                <Link className="project-text-link" to={`/scans/${data.scan.id}?finding=${issue.finding_id}`}>
                  查看證據 →
                </Link>
              </li>
            ))}
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
  ProjectScansPage,
  ProjectSettingsPage,
};
