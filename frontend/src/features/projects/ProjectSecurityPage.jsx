/**
 * 資安分析分頁（2026-10-08）：一次掃描的資安分數、安全標頭等第、問題依類型、
 * 改一處就能一起解決的組合、做得好的地方與本次未出現的問題。
 * 資料 GET /api/projects/<id>/security/?scan=（後端 projects.project_security，沿用問題分析的合併與比較）。
 */
import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { scoreGrade, scoreTone } from "../../components/projects/DashboardWidgets.jsx";
import ProjectHeader from "../../components/projects/ProjectHeader.jsx";
import { ObservatoryGrade, SiteStrengths } from "../../components/scans/SiteProfilePanel.jsx";
import { ScanTimeCard, SeverityChip, useProjectScans } from "./ProjectPages.jsx";
import { projectPath } from "./ProjectWorkspace.jsx";
import PageLoader from "../../shared/PageLoader.jsx";

// 由重到輕：已驗證弱點最需要處理，設定建議是加強防護
const KIND_ORDER = ["verified", "suspected", "exposure", "config"];
const CHANGE_LABELS = { new: "新增", persisting: "持續" };

function issueLink(projectId, scanId, title) {
  const params = new URLSearchParams({ category: "security", q: title });
  if (scanId) params.set("scan", scanId);
  return `${projectPath(projectId, "issues")}?${params}`;
}

export function ProjectSecurityPage() {
  const { project } = useOutletContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const scanParam = searchParams.get("scan") || "";
  const kindFilter = searchParams.get("kind") || "";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const { scans } = useProjectScans(project.id);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    api
      .get(`/projects/${project.id}/security/`, { params: scanParam ? { scan: scanParam } : {} })
      .then((response) => !cancelled && setData(response.data))
      .catch(() => !cancelled && setError("無法載入資安分析，這次掃描可能尚未完成。"));
    return () => {
      cancelled = true;
    };
  }, [project.id, scanParam]);

  function setParam(key, value) {
    const params = new URLSearchParams(searchParams);
    if (value) params.set(key, value);
    else params.delete(key);
    setSearchParams(params, { replace: true });
  }

  const completed = (scans || []).filter((scan) => scan.status === "completed");
  const header = (aside) => (
    <ProjectHeader
      project={project}
      section="資安分析"
      description="這次掃描的資安狀態：分數、安全標頭等第、問題依類型分組，以及改一處就能一起解決的設定。"
      aside={aside}
    />
  );

  if (error) return <div className="project-page">{header(null)}<section className="panel"><p className="error-text">{error}</p></section></div>;
  if (!data) return <div className="project-page">{header(null)}<section className="panel"><PageLoader label="載入資安分析中…" /></section></div>;
  if (!data.scan) {
    return (
      <div className="project-page">
        {header(null)}
        <section className="panel project-empty">
          <p className="project-empty-title">還沒有可分析的掃描</p>
          <p className="hint-text">完成一次勾選「資安」的掃描後，這裡會整理這個網站的資安狀態。</p>
          <Link className="primary-button" to={projectPath(project.id, "scans")}>建立掃描</Link>
        </section>
      </div>
    );
  }

  const timeCard = (
    <ScanTimeCard completed={completed} current={data.scan} value={scanParam} onChange={(value) => setParam("scan", value)} />
  );
  if (!data.checked) {
    return (
      <div className="project-page">
        {header(timeCard)}
        <section className="panel project-empty">
          <p className="project-empty-title">這次掃描沒有勾選「資安」</p>
          <p className="hint-text">下次建立掃描時勾選資安，或在上方選擇其他有檢查資安的掃描。</p>
          <Link className="primary-button" to={projectPath(project.id, "scans")}>建立掃描</Link>
        </section>
      </div>
    );
  }

  const kinds = KIND_ORDER.map((kind) => data.kinds.find((item) => item.kind === kind)).filter(Boolean);
  const issues = kindFilter ? data.issues.filter((issue) => issue.security_kind === kindFilter) : data.issues;
  const titleByKey = Object.fromEntries(data.issues.map((issue) => [issue.key, issue.title]));
  const scanId = scanParam || data.scan.id;

  return (
    <div className="project-page security-page">
      {header(timeCard)}

      {(data.coverage === "partial" || data.incomplete_checks.length > 0) && (
        <p className="security-notice" role="note">
          這次的資安檢查沒有全部完成
          {data.incomplete_checks.length > 0 && `（${data.incomplete_checks.join("、")}）`}
          ，分數只反映有完成的部分，沒列出的問題不代表不存在。
        </p>
      )}

      <div className="project-kpis">
        <section className="project-kpi">
          <p className="project-kpi-label">資安分數</p>
          {data.score === null || data.score === undefined ? (
            <p className="project-kpi-value is-small">未評估</p>
          ) : (
            <p className="project-kpi-value">
              {data.score}
              <small>/100</small>
              <span className={`project-grade tone-${scoreTone(data.score)}`}>{scoreGrade(data.score)}</span>
            </p>
          )}
          <p className="project-kpi-hint">Argus 依資安問題的嚴重度計算</p>
        </section>
        <section className="project-kpi">
          <p className="project-kpi-label">安全標頭參考等第</p>
          <p className="project-kpi-value">
            {data.observatory?.grade || "—"}
            {data.observatory && <small>{data.observatory.score} 分</small>}
          </p>
          <p className="project-kpi-hint">依 Mozilla Observatory 公開規則離線計算，非官方、不計入分數</p>
        </section>
        <section className="project-kpi">
          <p className="project-kpi-label">資安問題</p>
          <p className="project-kpi-value">{data.issues.length}<small>個問題</small></p>
          <p className="project-kpi-hint">
            {data.compared_with
              ? `新增 ${data.issues.filter((i) => i.status === "new").length}、持續 ${data.issues.filter((i) => i.status === "persisting").length}`
              : "下次掃描起會標示新增與持續"}
          </p>
        </section>
        <section className="project-kpi">
          <p className="project-kpi-label">CDN／反向代理</p>
          <p className="project-kpi-value is-small">{data.edge?.provider || "未偵測到"}</p>
          <p className="project-kpi-hint">
            {data.edge ? "主機與連接埠資訊反映的是邊緣節點，不是原始主機" : "流量看起來直接到網站主機"}
          </p>
        </section>
      </div>

      <section className="panel">
        <h2 className="project-section-title">問題類型</h2>
        <p className="hint-text">點一個類型只看該類問題；類型說明的是問題的性質，不影響分數。</p>
        <div className="security-kinds" role="group" aria-label="依類型篩選">
          {kinds.map((item) => (
            <button
              key={item.kind}
              type="button"
              className={`security-kind-card ${kindFilter === item.kind ? "active" : ""}`}
              aria-pressed={kindFilter === item.kind}
              onClick={() => setParam("kind", kindFilter === item.kind ? "" : item.kind)}
            >
              <span className={`security-kind-chip is-${item.kind}`}>{item.label}</span>
              <b>{item.count}</b>
              <span className="security-kind-desc">{item.description}</span>
            </button>
          ))}
        </div>
      </section>

      {data.root_causes.length > 0 && (
        <section className="panel">
          <h2 className="project-section-title">改一處就能一起解決</h2>
          <ul className="security-causes">
            {data.root_causes.map((cause) => (
              <li key={cause.id}>
                <p className="security-cause-title">{cause.title}<span>{cause.count} 個問題</span></p>
                <p className="security-cause-where">在哪裡修：{cause.where}</p>
                <p className="security-cause-items">{cause.issues.map((key) => titleByKey[key]).filter(Boolean).join("、")}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel">
        <h2 className="project-section-title">
          資安問題{kindFilter && `：${data.kinds.find((item) => item.kind === kindFilter)?.label}`}（{issues.length}）
        </h2>
        {issues.length === 0 ? (
          <p className="hint-text">{data.issues.length ? "這個類型沒有問題。" : "這次掃描沒有發現資安問題。"}</p>
        ) : (
          <ul className="security-issues">
            {issues.map((issue) => (
              <li key={issue.key}>
                <SeverityChip severity={issue.severity} />
                <div className="security-issue-body">
                  <p className="security-issue-title">
                    {issue.title}
                    {issue.security_kind_label && (
                      <span className={`security-kind-chip is-${issue.security_kind}`}>{issue.security_kind_label}</span>
                    )}
                    {CHANGE_LABELS[issue.status] && <span className="security-issue-change">{CHANGE_LABELS[issue.status]}</span>}
                  </p>
                  {issue.remediation && <p className="security-issue-fix">建議：{issue.remediation}</p>}
                </div>
                <Link className="project-text-link" to={issueLink(project.id, scanId, issue.title)}>查看詳情 →</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {data.observatory && (
        <section className="panel">
          <ObservatoryGrade observatory={data.observatory} />
        </section>
      )}

      {data.strengths.length > 0 && <SiteStrengths profile={{ strengths: data.strengths }} />}

      {data.missing.length > 0 && (
        <section className="panel">
          <h2 className="project-section-title">本次未出現（{data.missing.length}）</h2>
          <p className="hint-text">只有同一項檢查這次完整跑完，才標示「已修好」。</p>
          <ul className="project-issue-list is-muted">
            {data.missing.map((issue) => (
              <li key={issue.key} className="project-issue">
                <SeverityChip severity={issue.severity} />
                <div className="project-issue-body"><p className="project-issue-title">{issue.title}</p></div>
                {issue.status_label && <span className={`project-change-chip is-${issue.status}`}>{issue.status_label}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
