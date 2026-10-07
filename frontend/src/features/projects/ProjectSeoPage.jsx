// SEO 分析分頁（/projects/:id/seo）：概覽、頁面與內容、連結、搜尋關鍵字。
// 後端：GET /api/projects/<id>/seo/?scan=、seo/pages/<頁面 id>/、POST seo/keywords/、gsc/*
// （backend/apps/scans/seo_views.py）。逐頁檢查由保存的 HTML 即時分析；連結狀態與站台檢查來自
// 掃描階段 seo_links。「可索引」是 Argus 依頁面判斷，「Google 已收錄」只由 Search Console 回答。
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";

import { api } from "../../api";
import ProjectHeader from "../../components/projects/ProjectHeader.jsx";
import { apiErrorMessage } from "../../shared/AppShared.jsx";
import { formatDate, formatDateTime } from "../../shared/formatters";
import { ExternalIcon, GlobeIcon, SearchIcon } from "../../shared/LineIcons";
import { FilterChips, ScanTimeCard, useProjectScans } from "./ProjectPages.jsx";
import { projectPath } from "./ProjectWorkspace.jsx";
import { keywordGap, untargetedQueries } from "./seoKeywordGap";

const TABS = [
  { key: "overview", label: "概覽" },
  { key: "pages", label: "頁面與內容" },
  { key: "links", label: "連結" },
  { key: "keywords", label: "搜尋關鍵字" },
];
const LEVEL_META = {
  critical: { label: "重大", tone: "is-bad" },
  warning: { label: "警告", tone: "is-warn" },
  notice: { label: "提示", tone: "is-info" },
  pass: { label: "通過", tone: "is-good" },
};
const LEVEL_ORDER = { critical: 0, warning: 1, notice: 2, pass: 3 };
const VERDICT_META = {
  broken: { label: "失效", tone: "is-bad" },
  loop: { label: "轉址過多", tone: "is-bad" },
  error: { label: "無法連線", tone: "is-warn" },
  restricted: { label: "對方限制檢查", tone: "is-info" },
  redirect: { label: "轉址後正常", tone: "is-good" },
  ok: { label: "正常", tone: "is-good" },
  other: { label: "其他", tone: "is-info" },
  unchecked: { label: "未檢查", tone: "is-muted" },
  skipped: { label: "未檢查（非公開位址）", tone: "is-muted" },
};
const LINK_TYPES = { internal: "站內", subdomain: "子網域", external: "站外" };
const PAGE_FILTERS = {
  all: { label: "全部", test: () => true },
  problems: { label: "有問題", test: (page) => worstLevel(page.checks) !== "pass" },
  not_indexable: { label: "不可索引", test: (page) => !page.indexable },
  description: { label: "Description", test: (page) => levelOf(page, "description") !== "pass" },
  h1: { label: "H1", test: (page) => levelOf(page, "h1") !== "pass" },
  images: { label: "圖片 alt", test: (page) => page.images_missing_alt > 0 },
  slow: { label: "載入慢", test: (page) => levelOf(page, "speed") === "warning" || levelOf(page, "speed") === "notice" },
};
const LINK_FILTERS = {
  all: { label: "全部", test: () => true },
  broken: { label: "失效", test: (row) => row.verdict === "broken" || row.verdict === "loop" },
  redirect: { label: "轉址", test: (row) => row.verdict === "redirect" },
  uncertain: { label: "無法確認", test: (row) => ["error", "restricted", "other"].includes(row.verdict) },
  unchecked: { label: "未檢查", test: (row) => row.verdict === "unchecked" || row.verdict === "skipped" },
};
const GSC_DAYS = [7, 28, 90];
const MAX_KEYWORDS = 20; // 與後端 seo/keywords.MAX_KEYWORDS 一致
const RANK_BAND = {
  first: { label: "第 1 頁", tone: "is-good" },
  second: { label: "第 2 頁", tone: "is-warn" },
  beyond: { label: "第 3 頁以後", tone: "is-info" },
  none: { label: "沒有曝光", tone: "is-muted" },
};
const numberFormat = new Intl.NumberFormat("zh-TW");

function worstLevel(checks = []) {
  return checks.reduce((worst, check) => (LEVEL_ORDER[check.level] < LEVEL_ORDER[worst] ? check.level : worst), "pass");
}

function levelOf(page, key) {
  return page.checks.find((check) => check.key === key)?.level || "pass";
}

function LevelChip({ level }) {
  const meta = LEVEL_META[level] || LEVEL_META.notice;
  return <span className={`seo-chip ${meta.tone}`}>{meta.label}</span>;
}

function VerdictChip({ verdict }) {
  const meta = VERDICT_META[verdict] || VERDICT_META.other;
  return <span className={`seo-chip ${meta.tone}`}>{meta.label}</span>;
}

/** 跳轉鏈：302 → 200 OK。 */
function chainText(chain = []) {
  if (!chain.length) return "—";
  const parts = chain.map((hop) => (hop.status == null ? "—" : String(hop.status)));
  const last = chain[chain.length - 1].status;
  return `${parts.join(" → ")}${last >= 200 && last < 300 ? " OK" : ""}`;
}

function pct(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function matchesQuery(keyword, ...texts) {
  return !keyword || texts.some((text) => (text || "").toLowerCase().includes(keyword));
}

// ============================================================
// 主頁面
// ============================================================

function ProjectSeoPage() {
  const { project } = useOutletContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const scanParam = searchParams.get("scan") || "";
  const tab = TABS.some((item) => item.key === searchParams.get("tab")) ? searchParams.get("tab") : "overview";
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState(null);
  const [version, setVersion] = useState(0);
  const { scans } = useProjectScans(project.id);
  const gscFlash = searchParams.get("gsc");

  useEffect(() => {
    let cancelled = false;
    setError("");
    api
      .get(`/projects/${project.id}/seo/`, { params: scanParam ? { scan: scanParam } : {} })
      .then((response) => !cancelled && setData(response.data))
      .catch(() => !cancelled && setError("無法載入 SEO 分析。"));
    return () => {
      cancelled = true;
    };
  }, [project.id, scanParam, version]);

  const gsc = data?.gsc;
  const performance = useGscPerformance(project.id, gsc?.connected && gsc?.property ? gsc.property : "");

  function setParam(key, value) {
    const params = new URLSearchParams(searchParams);
    if (!value || value === "all") params.delete(key);
    else params.set(key, value);
    setSearchParams(params, { replace: true });
  }

  function dismissFlash() {
    const params = new URLSearchParams(searchParams);
    params.delete("gsc");
    params.delete("reason");
    params.delete("verified");
    setSearchParams(params, { replace: true });
  }

  const keyword = query.trim().toLowerCase();
  const completed = (scans || []).filter((scan) => scan.status === "completed");

  if (error) return <section className="panel"><p className="error-text">{error}</p></section>;
  if (!data) return <section className="panel"><p className="hint-text">載入 SEO 分析中…</p></section>;
  const gscNotice = gscFlash && (
    <div className={`seo-flash ${gscFlash === "connected" ? "is-good" : "is-bad"}`} role="status">
      <span>
        {gscFlash === "connected"
          ? gsc?.property
            ? `已連接 Google Search Console，並自動選擇資源 ${gsc.property}。`
            : "已連接 Google Search Console，請選擇要對應的資源。"
          : searchParams.get("reason") || "Search Console 連接失敗。"}
        {gscFlash === "connected" && searchParams.get("verified") && (
          <> 你是 Search Console 的擁有者，已自動完成網域驗證（{searchParams.get("verified")}），可以使用主動式資安測試。</>
        )}
      </span>
      <button type="button" className="project-text-link" onClick={dismissFlash}>知道了</button>
    </div>
  );
  if (!data.scan) {
    return (
      <div className="project-page seo-page">
        {gscNotice}
        <section className="panel project-empty">
          <p className="project-empty-title">還沒有完成的掃描</p>
          <p className="hint-text">完成一次勾選「SEO」的掃描後，這裡會列出每頁的 Title、Description、H1–H6、canonical、robots 與連結狀態。</p>
          <Link className={gsc?.enabled ? "secondary-button" : "primary-button"} to={projectPath(project.id, "scans")}>建立掃描</Link>
        </section>
        {gsc?.enabled && (
          <GscPanel project={project} gsc={gsc} performance={performance} keyword={keyword} onChanged={() => setVersion((value) => value + 1)} />
        )}
      </div>
    );
  }

  const googleIndexed = performance.data
    ? new Set(performance.data.pages.filter((row) => row.impressions > 0).map((row) => row.url))
    : null;

  return (
    <div className="project-page seo-page">
      <ProjectHeader
        project={project}
        section="SEO 分析"
        description={`彙整這次掃描的 ${data.overview.pages_scanned} 個頁面：頁面內容、連結狀態與搜尋關鍵字。每項結論都附受影響網址、檢測時間與證據。`}
        aside={<ScanTimeCard completed={completed} current={{ id: data.scan.id, completed_at: data.scan.completed_at }} value={scanParam} onChange={(value) => setParam("scan", value)} />}
      />

      {gscNotice}
      {!data.scan.seo_checked && (
        <p className="seo-note">這次掃描沒有勾選 SEO 維度：頁面內容仍可分析，但沒有連結狀態與站台層級檢查。</p>
      )}

      <section className="panel seo-toolbar">
        <div className="seo-tabs" role="tablist" aria-label="SEO 分析區塊">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={tab === item.key}
              className={`seo-tab ${tab === item.key ? "is-active" : ""}`}
              onClick={() => setParam("tab", item.key === "overview" ? "" : item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="project-search seo-search">
          <span className="project-sr-only">篩選網址</span>
          <input
            type="search"
            className="input"
            placeholder="篩選網址或標題"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setParam("q", event.target.value);
            }}
          />
        </label>
      </section>

      {tab === "overview" && (
        <OverviewTab data={data} keyword={keyword} googleIndexed={googleIndexed} gsc={gsc} onOpenPage={setDetail} />
      )}
      {tab === "pages" && (
        <PagesTab
          data={data}
          keyword={keyword}
          projectId={project.id}
          gsc={gsc}
          googleIndexed={googleIndexed}
          onOpenPage={setDetail}
          filter={PAGE_FILTERS[searchParams.get("filter")] ? searchParams.get("filter") : "all"}
          setFilter={(value) => setParam("filter", value)}
        />
      )}
      {tab === "links" && <LinksTab data={data} keyword={keyword} onOpenPage={setDetail} />}
      {tab === "keywords" && (
        <KeywordsTab
          project={project}
          data={data}
          keyword={keyword}
          gsc={gsc}
          performance={performance}
          onChanged={() => setVersion((value) => value + 1)}
          onOpenPage={setDetail}
        />
      )}

      {detail && (
        <PageDetailDialog
          projectId={project.id}
          scanId={data.scan.id}
          scanParam={scanParam}
          pageId={detail}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}

// ============================================================
// 概覽
// ============================================================

function OverviewTab({ data, keyword, googleIndexed, gsc, onOpenPage }) {
  const { overview } = data;
  const [openKey, setOpenKey] = useState(null);
  const issues = data.issues
    .map((issue) => ({ ...issue, pages: issue.pages.filter((page) => matchesQuery(keyword, page.url, page.value)) }))
    .filter((issue) => !keyword || issue.pages.length);
  const indexedCount = googleIndexed
    ? data.pages.filter((page) => googleIndexed.has(page.url)).length
    : null;

  return (
    <>
      <section className="seo-kpis" aria-label="SEO 概覽">
        <Kpi label="掃描頁數" value={overview.pages_scanned} hint={`檢測時間 ${formatDateTime(data.scan.completed_at)}`} />
        <Kpi label="受影響頁數" value={overview.pages_affected} hint={`有重大或警告問題的頁面，共 ${overview.pages_scanned} 頁`} />
        <Kpi label="重大問題" value={overview.critical} tone={overview.critical ? "is-bad" : ""} hint={`另有警告 ${overview.warnings}、提示 ${overview.notices}`} />
        <Kpi label="可索引（Argus 判斷）" value={`${overview.indexable} / ${overview.pages_scanned}`} hint="HTTP 200、沒有 noindex、canonical 指向自己、robots.txt 未阻擋" />
        <Kpi
          label="Google 已收錄"
          value={indexedCount == null ? "—" : `${indexedCount} / ${overview.pages_scanned}`}
          hint={
            indexedCount == null
              ? gsc?.connected ? "選擇 Search Console 資源後顯示" : "連接 Search Console 後顯示（搜尋關鍵字分頁）"
              : "期間內在 Google 有曝光的頁面；其餘可在頁面分頁逐頁檢查"
          }
        />
        <Kpi label="失效連結" value={overview.broken_links} tone={overview.broken_links ? "is-bad" : ""} hint={data.links.checked_at ? `檢查時間 ${formatDateTime(data.links.checked_at)}` : "這次掃描沒有連結檢查"} />
      </section>

      <section className="panel">
        <h2 className="project-section-title">優先修復事項</h2>
        {overview.priorities.length === 0 ? (
          <p className="hint-text">沒有重大或警告等級的問題。</p>
        ) : (
          <ol className="seo-priorities">
            {overview.priorities.map((item) => (
              <li key={`${item.key}-${item.title}`}>
                <LevelChip level={item.level} />
                <div>
                  <p className="seo-priority-title">{item.title}<span className="seo-count">{item.count} 處</span></p>
                  <p className="seo-muted">{item.advice}</p>
                  {item.example && (
                    <p className="seo-muted">
                      例：
                      {item.example.page_id ? (
                        <button type="button" className="project-text-link" onClick={() => onOpenPage(item.example.page_id)}>{item.example.url}</button>
                      ) : (
                        <span>{item.example.url}</span>
                      )}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="panel">
        <h2 className="project-section-title">全部問題</h2>
        {issues.length === 0 ? (
          <p className="hint-text">{keyword ? "沒有符合篩選的問題。" : "沒有發現問題。"}</p>
        ) : (
          <ul className="seo-issue-list">
            {issues.map((issue) => {
              const key = `${issue.key}-${issue.level}-${issue.title}`;
              const open = openKey === key;
              return (
                <li key={key} className={`seo-issue ${open ? "is-open" : ""}`}>
                  <button type="button" className="seo-issue-head" aria-expanded={open} onClick={() => setOpenKey(open ? null : key)}>
                    <LevelChip level={issue.level} />
                    <span className="seo-issue-title">{issue.title}</span>
                    <span className="seo-count">{issue.count} 處</span>
                    <span className="seo-muted seo-issue-source">{issue.source === "site" ? "站台" : issue.source === "links" ? "連結" : "頁面"}</span>
                  </button>
                  {open && (
                    <div className="seo-issue-body">
                      {issue.advice && <p className="seo-advice">怎麼修：{issue.advice}</p>}
                      <EvidenceTable rows={issue.pages} onOpenPage={onOpenPage} />
                      {issue.count > issue.pages.length && <p className="seo-muted">只列出前 {issue.pages.length} 處。</p>}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <SiteChecks checks={data.site_checks} checkedAt={data.links.checked_at} />
    </>
  );
}

function Kpi({ label, value, hint, tone = "" }) {
  return (
    <div className="project-kpi seo-kpi">
      <span className="project-kpi-label">{label}</span>
      <span className={`project-kpi-value ${tone}`}>{typeof value === "number" ? numberFormat.format(value) : value}</span>
      {hint && <span className="project-kpi-hint">{hint}</span>}
    </div>
  );
}

/** 證據表：受影響網址、原始值或跳轉鏈、檢測時間。 */
function EvidenceTable({ rows, onOpenPage }) {
  return (
    <div className="project-table-wrap">
      <table className="project-table seo-evidence-table">
        <thead>
          <tr>
            <th scope="col">受影響網址</th>
            <th scope="col">證據</th>
            <th scope="col">檢測時間</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.url}-${index}`}>
              <td className="seo-url-cell">
                {row.page_id ? (
                  <button type="button" className="project-text-link seo-url" onClick={() => onOpenPage(row.page_id)}>{row.url}</button>
                ) : (
                  <span className="seo-url">{row.url || "（站台層級）"}</span>
                )}
              </td>
              <td className="seo-evidence">
                {row.value || "—"}
                {row.evidence?.chain?.length > 0 && <span className="seo-muted"> 跳轉鏈：{chainText(row.evidence.chain)}</span>}
              </td>
              <td className="seo-nowrap">{row.detected_at ? formatDateTime(row.detected_at) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SiteChecks({ checks, checkedAt }) {
  return (
    <section className="panel">
      <h2 className="project-section-title">網址與站台檢查</h2>
      {checks.length === 0 ? (
        <p className="hint-text">這次掃描沒有站台層級檢查（未勾選 SEO，或是功能上線前的掃描）。</p>
      ) : (
        <div className="project-table-wrap">
          <table className="project-table">
            <thead>
              <tr>
                <th scope="col">項目</th>
                <th scope="col">結果</th>
                <th scope="col">證據</th>
                <th scope="col">建議</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((check) => (
                <tr key={check.key}>
                  <td className="seo-nowrap">{check.label}</td>
                  <td><LevelChip level={check.level} /></td>
                  <td className="seo-evidence">
                    {check.value}
                    {check.evidence?.requested && <span className="seo-muted seo-block">檢查網址：{check.evidence.requested}</span>}
                  </td>
                  <td className="seo-muted">{check.advice || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {checkedAt && <p className="seo-muted">檢測時間 {formatDateTime(checkedAt)}</p>}
    </section>
  );
}

// ============================================================
// 頁面與內容
// ============================================================

function PagesTab({ data, keyword, projectId, gsc, googleIndexed, onOpenPage, filter, setFilter }) {
  const pages = data.pages.filter((page) => matchesQuery(keyword, page.url, page.title));
  const visible = pages.filter(PAGE_FILTERS[filter].test);
  return (
    <>
      <section className="panel project-filters">
        <FilterChips
          label="篩選"
          value={filter}
          onChange={setFilter}
          options={Object.entries(PAGE_FILTERS).map(([value, item]) => ({ value, label: item.label, count: pages.filter(item.test).length }))}
        />
      </section>
      <section className="panel">
        <p className="seo-muted seo-legend">
          「可索引」是 Argus 依頁面本身判斷（狀態碼、noindex、canonical、robots.txt）；「Google 收錄」需連接 Search Console，兩者不一定相同。
          長度以顯示寬度計算（中文字算 2），不直接套用英文字數門檻。
        </p>
        {visible.length === 0 ? (
          <p className="hint-text">沒有符合條件的頁面。</p>
        ) : (
          <div className="project-table-wrap">
            <table className="project-table seo-pages-table">
              <thead>
                <tr>
                  <th scope="col">頁面</th>
                  <th scope="col">HTTP</th>
                  <th scope="col">可索引</th>
                  <th scope="col">Google 收錄</th>
                  <th scope="col">Title</th>
                  <th scope="col">Description</th>
                  <th scope="col">H1</th>
                  <th scope="col">標題結構</th>
                  <th scope="col">正文</th>
                  <th scope="col">圖片 alt</th>
                  <th scope="col">載入</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((page) => (
                  <tr key={page.page_id}>
                    <td className="project-page-cell">
                      <button type="button" className="project-text-link seo-page-link" onClick={() => onOpenPage(page.page_id)}>
                        {page.title || "（無標題）"}
                      </button>
                      <span className="project-page-url">{page.url}</span>
                    </td>
                    <td><span className={`project-status ${page.status_code === 200 ? "is-good" : page.status_code >= 400 ? "is-bad" : "is-warn"}`}>{page.status_code ?? "—"}</span></td>
                    <td>
                      {page.indexable ? (
                        <span className="seo-chip is-good">可索引</span>
                      ) : (
                        <span className="seo-chip is-warn" title={page.not_indexable_reasons.join("、")}>否</span>
                      )}
                      {!page.indexable && <span className="seo-muted seo-block">{page.not_indexable_reasons.join("、")}</span>}
                    </td>
                    <td><GoogleIndexCell projectId={projectId} gsc={gsc} googleIndexed={googleIndexed} url={page.url} /></td>
                    <td><LevelChip level={levelOf(page, "title")} /></td>
                    <td><LevelChip level={levelOf(page, "description")} /></td>
                    <td>
                      <LevelChip level={levelOf(page, "h1")} />
                      <span className="seo-muted seo-block">{page.h1.length} 個</span>
                    </td>
                    <td className="seo-nowrap seo-muted">
                      {Object.entries(page.heading_counts).filter(([, count]) => count).map(([tag, count]) => `${tag.toUpperCase()}×${count}`).join(" ") || "無"}
                    </td>
                    <td className="seo-nowrap">{page.content.word_equivalent} 詞</td>
                    <td className="seo-nowrap">{page.images_missing_alt ? <span className="seo-chip is-warn">缺 {page.images_missing_alt}</span> : `${page.image_total} 張`}</td>
                    <td className="seo-nowrap">{page.load_time_ms == null ? "—" : `${(page.load_time_ms / 1000).toFixed(1)} 秒`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

/** Google 收錄：期間內有曝光＝已收錄；否則可呼叫網址檢查 API 逐頁確認。 */
function GoogleIndexCell({ projectId, gsc, googleIndexed, url }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  if (!gsc?.connected || !gsc.property) return <span className="seo-muted">未連接</span>;
  if (googleIndexed?.has(url)) return <span className="seo-chip is-good">有曝光</span>;
  if (result) {
    if (result.error) return <span className="seo-muted">{result.error}</span>;
    const indexed = result.verdict === "PASS";
    return (
      <span title={result.coverage_state}>
        <span className={`seo-chip ${indexed ? "is-good" : "is-warn"}`}>{indexed ? "已收錄" : "未收錄"}</span>
        <span className="seo-muted seo-block">{result.coverage_state}</span>
      </span>
    );
  }
  async function inspect() {
    setBusy(true);
    try {
      const response = await api.post(`/projects/${projectId}/gsc/inspect/`, { url });
      setResult(response.data);
    } catch (err) {
      setResult({ error: apiErrorMessage(err, "檢查失敗") });
    } finally {
      setBusy(false);
    }
  }
  return (
    <button type="button" className="project-text-link" disabled={busy} onClick={inspect}>
      {busy ? "檢查中…" : "網址檢查"}
    </button>
  );
}

// ============================================================
// 單頁證據
// ============================================================

function PageDetailDialog({ projectId, scanId, scanParam, pageId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    api
      .get(`/projects/${projectId}/seo/pages/${pageId}/`, { params: scanParam ? { scan: scanParam } : {} })
      .then((response) => !cancelled && setDetail(response.data))
      .catch(() => !cancelled && setError("無法載入這一頁的證據。"));
    return () => {
      cancelled = true;
    };
  }, [projectId, pageId, scanParam]);

  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="seo-drawer-backdrop" role="presentation" onPointerDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="seo-drawer" role="dialog" aria-modal="true" aria-label="單頁 SEO 證據">
        <div className="seo-drawer-head">
          <div>
            <p className="seo-eyebrow">單頁證據</p>
            <h2 className="seo-drawer-title">{detail?.title || "（無標題）"}</h2>
            {detail && <p className="seo-url seo-muted">{detail.url}</p>}
          </div>
          <button type="button" className="secondary-button" onClick={onClose}>關閉</button>
        </div>
        {error && <p className="error-text">{error}</p>}
        {!detail && !error && <p className="hint-text">載入中…</p>}
        {detail && <PageDetail detail={detail} scanId={scanId} />}
      </aside>
    </div>
  );
}

function PageDetail({ detail, scanId }) {
  return (
    <div className="seo-drawer-body">
      <p className="seo-muted">
        檢測時間 {formatDateTime(detail.detected_at)}・HTTP {detail.status_code ?? "—"}・原始碼 {(detail.html_bytes / 1024).toFixed(0)} KB
        {detail.load_time_ms != null && `・載入 ${(detail.load_time_ms / 1000).toFixed(1)} 秒`}
      </p>
      <div className="seo-drawer-actions">
        <Link className="project-text-link" to={`/scans/${scanId}?page=${detail.page_id}`}>在掃描詳情查看此頁問題</Link>
        <a className="project-text-link" href={detail.url} target="_blank" rel="noreferrer noopener">
          開啟頁面 <ExternalIcon />
        </a>
      </div>

      <section className="seo-preview" aria-label="Google 搜尋結果預覽（示意）">
        <p className="seo-preview-url">{detail.url}</p>
        <p className="seo-preview-title">{detail.title || "（無標題）"}</p>
        <p className="seo-preview-desc">{detail.description || "（沒有 meta description，Google 會自行從內文擷取）"}</p>
        <p className="seo-muted">示意：實際顯示由 Google 決定，可能改寫標題或摘要。</p>
      </section>

      <h3 className="seo-drawer-subtitle">檢查結果</h3>
      <ul className="seo-checks">
        {detail.checks.map((check) => (
          <li key={check.key}>
            <LevelChip level={check.level} />
            <div>
              <p className="seo-check-label">{check.label}</p>
              <p className="seo-evidence">{check.value || "（空）"}</p>
              {check.advice && <p className="seo-muted">{check.advice}</p>}
            </div>
          </li>
        ))}
      </ul>

      <h3 className="seo-drawer-subtitle">索引與標記</h3>
      <dl className="seo-facts">
        <dt>可索引（Argus 判斷）</dt>
        <dd>{detail.indexable ? "是" : `否：${detail.not_indexable_reasons.join("、")}`}</dd>
        <dt>Canonical</dt>
        <dd className="seo-url">{detail.canonical || "（未設定）"}</dd>
        <dt>Robots／X-Robots-Tag</dt>
        <dd>{Object.keys(detail.robots).length ? Object.entries(detail.robots).map(([key, source]) => `${key}（${source}）`).join("、") : "無限制"}</dd>
        <dt>語言</dt>
        <dd>{detail.lang || "（html 未標示 lang）"}</dd>
        <dt>Hreflang</dt>
        <dd>{detail.hreflang.length ? detail.hreflang.map((item) => `${item.lang} → ${item.href}`).join("；") : "無"}</dd>
        <dt>Open Graph</dt>
        <dd>{Object.keys(detail.open_graph).length ? Object.entries(detail.open_graph).map(([key, value]) => `${key}: ${value}`).join("；") : "無"}</dd>
        <dt>Favicon／Viewport</dt>
        <dd>{detail.has_favicon ? "有 favicon" : "沒有宣告 favicon"}・{detail.has_viewport ? "有 viewport" : "沒有 viewport"}</dd>
        <dt>正文</dt>
        <dd>約 {detail.content.word_equivalent} 詞（中文字 {detail.content.cjk_chars}、英文詞 {detail.content.latin_words}）；文字佔原始碼 {pct(detail.content.text_ratio)}</dd>
      </dl>
      {detail.excerpt && <blockquote className="seo-excerpt">{detail.excerpt}…</blockquote>}

      <h3 className="seo-drawer-subtitle">H1–H6 結構（{detail.headings.length}）</h3>
      {detail.headings.length === 0 ? (
        <p className="hint-text">沒有標題。</p>
      ) : (
        <ol className="seo-outline">
          {detail.headings.map((heading, index) => (
            <li key={index} className={`seo-outline-h${heading.level}`}>
              <span className="seo-outline-tag">H{heading.level}</span>
              {heading.text || <em className="seo-muted">（沒有文字）</em>}
            </li>
          ))}
        </ol>
      )}

      <h3 className="seo-drawer-subtitle">圖片（{detail.image_total}）</h3>
      {detail.images.length === 0 ? (
        <p className="hint-text">沒有圖片。</p>
      ) : (
        <div className="project-table-wrap">
          <table className="project-table">
            <thead>
              <tr><th scope="col">圖片</th><th scope="col">alt</th><th scope="col">title</th></tr>
            </thead>
            <tbody>
              {detail.images.map((image, index) => (
                <tr key={`${image.src}-${index}`}>
                  <td className="seo-url">{image.src || "（無 src）"}</td>
                  <td>{image.alt === null ? <span className="seo-chip is-warn">缺 alt</span> : image.alt || <span className="seo-muted">空（裝飾用）</span>}</td>
                  <td>{image.title || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="seo-drawer-subtitle">連結（{detail.link_total}）</h3>
      {detail.links.length === 0 ? (
        <p className="hint-text">沒有連結。</p>
      ) : (
        <div className="project-table-wrap">
          <table className="project-table">
            <thead>
              <tr><th scope="col">錨文字</th><th scope="col">目標</th><th scope="col">類型</th><th scope="col">狀態</th></tr>
            </thead>
            <tbody>
              {detail.links.map((link, index) => (
                <tr key={`${link.url}-${index}`}>
                  <td>{link.anchor || <span className="seo-chip is-warn">沒有文字</span>}</td>
                  <td className="seo-url">{link.url}{link.nofollow && <span className="seo-muted">（nofollow）</span>}</td>
                  <td className="seo-nowrap">{LINK_TYPES[link.type]}</td>
                  <td className="seo-nowrap"><VerdictChip verdict={link.verdict} /> <span className="seo-muted">{chainText(link.chain)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================
// 連結
// ============================================================

function LinksTab({ data, keyword, onOpenPage }) {
  const [type, setType] = useState("all");
  const [verdict, setVerdict] = useState("all");
  const [openUrl, setOpenUrl] = useState(null);
  const { links } = data;
  const rows = links.rows.filter(
    (row) => matchesQuery(keyword, row.url, ...row.sources.map((s) => s.url)) && (type === "all" || row.type === type),
  );
  const visible = rows.filter(LINK_FILTERS[verdict].test);
  const anchorIssues = links.anchor_issues.filter((item) => matchesQuery(keyword, item.source_url, item.target));

  return (
    <>
      <section className="panel project-filters">
        <FilterChips
          label="類型"
          value={type}
          onChange={setType}
          options={[
            { value: "all", label: "全部", count: links.rows.length },
            ...Object.entries(LINK_TYPES).map(([value, label]) => ({ value, label, count: links.counts[value] })),
          ]}
        />
        <FilterChips
          label="狀態"
          value={verdict}
          onChange={setVerdict}
          options={Object.entries(LINK_FILTERS).map(([value, item]) => ({ value, label: item.label, count: rows.filter(item.test).length }))}
        />
      </section>
      <section className="panel">
        <p className="seo-muted seo-legend">
          {links.checked_at
            ? `檢查時間 ${formatDateTime(links.checked_at)}；最多檢查 ${links.limit} 個不重複連結${links.unchecked ? `，另有 ${links.unchecked} 個未檢查` : ""}。`
            : "這次掃描沒有連結狀態檢查；站內已爬到的頁面以爬蟲結果顯示。"}
          302 → 200 這類「轉址後正常」不算失效；401／403／429 代表對方拒絕自動檢查，標為無法確認。
        </p>
        {visible.length === 0 ? (
          <p className="hint-text">沒有符合條件的連結。</p>
        ) : (
          <div className="project-table-wrap">
            <table className="project-table seo-links-table">
              <thead>
                <tr>
                  <th scope="col">目標網址</th>
                  <th scope="col">類型</th>
                  <th scope="col">狀態與跳轉鏈</th>
                  <th scope="col">來源頁</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => {
                  const open = openUrl === row.url;
                  return (
                    <Fragment key={row.url}>
                      <tr>
                        <td className="seo-url">{row.url}{row.nofollow && <span className="seo-muted">（nofollow）</span>}</td>
                        <td className="seo-nowrap">{LINK_TYPES[row.type]}</td>
                        <td>
                          <VerdictChip verdict={row.verdict} />
                          <span className="seo-muted seo-block">{chainText(row.chain)}{row.note ? `；${row.note}` : ""}</span>
                        </td>
                        <td className="seo-nowrap">
                          <button type="button" className="project-text-link" aria-expanded={open} onClick={() => setOpenUrl(open ? null : row.url)}>
                            {row.source_count} 處{open ? "（收合）" : ""}
                          </button>
                        </td>
                      </tr>
                      {open && (
                        <tr className="seo-subrow">
                          <td colSpan={4}>
                            <ul className="seo-sources">
                              {row.sources.map((source, index) => (
                                <li key={`${source.page_id}-${index}`}>
                                  <button type="button" className="project-text-link seo-url" onClick={() => onOpenPage(source.page_id)}>{source.url}</button>
                                  <span className="seo-muted">錨文字：{source.anchor || "（沒有文字）"}</span>
                                </li>
                              ))}
                            </ul>
                            {row.source_count > row.sources.length && <p className="seo-muted">只列出前 {row.sources.length} 處。</p>}
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

      <section className="panel">
        <h2 className="project-section-title">難以理解的連結文字</h2>
        <p className="seo-muted">沒有文字（含純圖片連結缺 alt），或是「點此」「更多」這類看不出目的地的文字。</p>
        {anchorIssues.length === 0 ? (
          <p className="hint-text">沒有發現。</p>
        ) : (
          <div className="project-table-wrap">
            <table className="project-table">
              <thead>
                <tr><th scope="col">來源頁</th><th scope="col">錨文字</th><th scope="col">目標</th></tr>
              </thead>
              <tbody>
                {anchorIssues.map((item, index) => (
                  <tr key={`${item.page_id}-${item.target}-${index}`}>
                    <td><button type="button" className="project-text-link seo-url" onClick={() => onOpenPage(item.page_id)}>{item.source_url}</button></td>
                    <td>{item.anchor ? `「${item.anchor}」` : <span className="seo-chip is-warn">沒有文字</span>}</td>
                    <td className="seo-url">{item.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

// ============================================================
// 搜尋關鍵字（目標關鍵字＋Google Search Console）
// ============================================================

function useGscPerformance(projectId, property) {
  const [days, setDays] = useState(28);
  const [state, setState] = useState({ data: null, error: "", loading: false });
  useEffect(() => {
    if (!property) {
      setState({ data: null, error: "", loading: false });
      return undefined;
    }
    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: "" }));
    api
      .get(`/projects/${projectId}/gsc/performance/`, { params: { days } })
      .then((response) => !cancelled && setState({ data: response.data, error: "", loading: false }))
      .catch((err) => !cancelled && setState({ data: null, error: apiErrorMessage(err, "無法取得 Search Console 資料。"), loading: false }));
    return () => {
      cancelled = true;
    };
  }, [projectId, property, days]);
  return { ...state, days, setDays };
}

function KeywordsTab({ project, data, keyword, gsc, performance, onChanged, onOpenPage }) {
  return (
    <>
      <GscPanel project={project} gsc={gsc} performance={performance} keyword={keyword} onChanged={onChanged} />
      <TargetKeywords project={project} data={data} performance={performance} onChanged={onChanged} onOpenPage={onOpenPage} />
    </>
  );
}

function GscPanel({ project, gsc, performance, keyword, onChanged }) {
  const [properties, setProperties] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadProperties = useCallback(async () => {
    try {
      const response = await api.get(`/projects/${project.id}/gsc/properties/`);
      setProperties(response.data.properties);
    } catch (err) {
      setError(apiErrorMessage(err, "無法取得 Search Console 資源。"));
    }
  }, [project.id]);

  useEffect(() => {
    if (gsc?.connected && !gsc.property) loadProperties();
  }, [gsc?.connected, gsc?.property, loadProperties]);

  async function connect() {
    setBusy(true);
    setError("");
    try {
      const response = await api.post(`/projects/${project.id}/gsc/connect/`);
      window.location.assign(response.data.authorization_url);
    } catch (err) {
      setError(apiErrorMessage(err, "無法開始連接。"));
      setBusy(false);
    }
  }

  async function choose(property) {
    setBusy(true);
    setError("");
    try {
      await api.patch(`/projects/${project.id}/gsc/`, { property });
      onChanged();
    } catch (err) {
      setError(apiErrorMessage(err, "無法選擇這個資源。"));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      await api.delete(`/projects/${project.id}/gsc/`);
      setProperties(null);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  if (!gsc?.enabled) {
    return (
      <section className="panel">
        <h2 className="project-section-title">Google Search Console</h2>
        <p className="hint-text">管理員尚未設定 Search Console 串接；可先用下方的目標關鍵字檢查頁面內容。</p>
      </section>
    );
  }

  if (!gsc.connected || gsc.needs_reconnect) {
    return (
      <section className="panel seo-gsc-connect">
        <div className="seo-gsc-icon" aria-hidden="true"><GlobeIcon /></div>
        <div>
          <h2 className="project-section-title">連接 Google Search Console</h2>
          <p className="seo-muted">
            {gsc.needs_reconnect ? `${gsc.error} ` : ""}
            連接後可看到網站在 Google 的實際搜尋詞：曝光、點擊、點閱率、平均排名、趨勢與對應頁面，並可逐頁確認是否已被收錄。
            Argus 只申請唯讀權限，可隨時中斷連線。
          </p>
          {project.is_demo ? (
            <p className="hint-text">示範專案是虛構網站，無法連接。</p>
          ) : (
            <button type="button" className="primary-button" disabled={busy} onClick={connect}>
              {busy ? "前往 Google…" : gsc.needs_reconnect ? "重新連接" : "連接 Search Console"}
            </button>
          )}
          {error && <p className="error-text" role="alert">{error}</p>}
        </div>
      </section>
    );
  }

  if (!gsc.property) {
    return (
      <section className="panel">
        <h2 className="project-section-title">選擇 Search Console 資源</h2>
        <p className="seo-muted">選擇與 {project.origin} 對應的資源（網域資源或網址前置字元資源）。</p>
        {error && <p className="error-text" role="alert">{error}</p>}
        {properties == null ? (
          <p className="hint-text">載入中…</p>
        ) : properties.length === 0 ? (
          <p className="hint-text">這個 Google 帳號沒有任何已驗證的資源。請先在 Search Console 新增並驗證網站。</p>
        ) : (
          <ul className="seo-property-list">
            {properties.map((item) => (
              <li key={item.site_url}>
                <span className="seo-url">{item.site_url}</span>
                {item.matches && <span className="seo-chip is-good">符合此網站</span>}
                <button type="button" className="secondary-button" disabled={busy} onClick={() => choose(item.site_url)}>選擇</button>
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="project-text-link" disabled={busy} onClick={disconnect}>中斷連線</button>
      </section>
    );
  }

  const perf = performance.data;
  const queries = (perf?.queries || []).filter((row) => matchesQuery(keyword, row.query, row.page));
  return (
    <section className="panel">
      <div className="seo-gsc-head">
        <div>
          <h2 className="project-section-title">實際搜尋詞（Google Search Console）</h2>
          <p className="seo-muted">
            資源 {gsc.property}
            {!gsc.property_matches && "（與此網站網址不符，請確認）"}
            {perf && `・期間 ${formatDate(perf.start)}–${formatDate(perf.end)}（Search Console 資料約延遲 2–3 天）`}
          </p>
        </div>
        <div className="seo-gsc-actions">
          <FilterChips label="期間" value={performance.days} onChange={performance.setDays} options={GSC_DAYS.map((days) => ({ value: days, label: `${days} 天` }))} />
          <button type="button" className="project-text-link" disabled={busy} onClick={() => choose("")}>更換資源</button>
          <button type="button" className="project-text-link" disabled={busy} onClick={disconnect}>中斷連線</button>
        </div>
      </div>
      {performance.loading && <p className="hint-text">載入 Search Console 資料中…</p>}
      {performance.error && <p className="error-text" role="alert">{performance.error}</p>}
      {perf && (
        <>
          <div className="seo-kpis">
            <Kpi label="點擊" value={perf.totals.clicks} />
            <Kpi label="曝光" value={perf.totals.impressions} />
            <Kpi label="點閱率（CTR）" value={pct(perf.totals.ctr)} />
            <Kpi label="搜尋詞數" value={perf.queries.length} hint="最多列出 200 個" />
          </div>
          <div className="seo-trends">
            <TrendChart rows={perf.trend} field="clicks" label="每日點擊" />
            <TrendChart rows={perf.trend} field="impressions" label="每日曝光" />
          </div>
          <p className="seo-muted seo-legend">平均排名是期間內所有曝光的平均統計值，不是某一刻的即時名次；變化是與前一個同長度期間比較。</p>
          {queries.length === 0 ? (
            <p className="hint-text">期間內沒有搜尋資料{keyword ? "符合篩選" : ""}。</p>
          ) : (
            <div className="project-table-wrap">
              <table className="project-table seo-gsc-table">
                <thead>
                  <tr>
                    <th scope="col">搜尋詞</th>
                    <th scope="col">點擊</th>
                    <th scope="col">曝光</th>
                    <th scope="col">CTR</th>
                    <th scope="col">平均排名（期間統計）</th>
                    <th scope="col">對應頁面</th>
                  </tr>
                </thead>
                <tbody>
                  {queries.map((row) => (
                    <tr key={row.query}>
                      <td>{row.query}</td>
                      <td className="seo-nowrap">
                        {numberFormat.format(row.clicks)}
                        {row.clicks_change != null && row.clicks_change !== 0 && (
                          <span className={`seo-delta ${row.clicks_change > 0 ? "is-up" : "is-down"}`}>{row.clicks_change > 0 ? "+" : ""}{row.clicks_change}</span>
                        )}
                      </td>
                      <td className="seo-nowrap">{numberFormat.format(row.impressions)}</td>
                      <td className="seo-nowrap">{pct(row.ctr)}</td>
                      <td className="seo-nowrap">
                        {row.position.toFixed(1)}
                        {row.position_change != null && row.position_change !== 0 && (
                          <span className={`seo-delta ${row.position_change > 0 ? "is-up" : "is-down"}`}>
                            {row.position_change > 0 ? "↑" : "↓"}{Math.abs(row.position_change).toFixed(1)}
                          </span>
                        )}
                      </td>
                      <td className="seo-url">{row.page || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** 每日趨勢（單一指標一張圖；點擊與曝光量級不同，不放在同一個座標軸）。 */
function TrendChart({ rows, field, label }) {
  const [hover, setHover] = useState(null);
  const width = 360;
  const height = 120;
  const pad = { top: 10, right: 8, bottom: 20, left: 36 };
  const max = Math.max(1, ...rows.map((row) => row[field]));
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const x = (index) => pad.left + (rows.length > 1 ? (index / (rows.length - 1)) * plotW : plotW / 2);
  const y = (value) => pad.top + plotH - (value / max) * plotH;
  const points = rows.map((row, index) => `${x(index)},${y(row[field])}`).join(" ");
  const active = hover == null ? null : rows[hover];
  return (
    <figure className="seo-trend">
      <figcaption className="seo-trend-label">
        {label}
        <span className="seo-muted">{active ? `${formatDate(active.date)}：${numberFormat.format(active[field])}` : `最高 ${numberFormat.format(max)}`}</span>
      </figcaption>
      {rows.length === 0 ? (
        <p className="hint-text">無資料</p>
      ) : (
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label={`${label}趨勢`} onMouseLeave={() => setHover(null)}>
          <line x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} className="seo-trend-axis" />
          <line x1={pad.left} x2={width - pad.right} y1={y(max)} y2={y(max)} className="seo-trend-grid" />
          <text x={pad.left - 6} y={y(max) + 4} textAnchor="end" className="seo-trend-tick">{numberFormat.format(max)}</text>
          <text x={pad.left - 6} y={y(0) + 4} textAnchor="end" className="seo-trend-tick">0</text>
          <text x={pad.left} y={height - 4} className="seo-trend-tick">{formatDate(rows[0].date).slice(5)}</text>
          <text x={width - pad.right} y={height - 4} textAnchor="end" className="seo-trend-tick">{formatDate(rows[rows.length - 1].date).slice(5)}</text>
          <polyline points={points} className="seo-trend-line" />
          {active && <circle cx={x(hover)} cy={y(active[field])} r="4" className="seo-trend-dot" />}
          {rows.map((row, index) => (
            <rect
              key={row.date}
              x={x(index) - plotW / Math.max(rows.length, 1) / 2}
              y={pad.top}
              width={plotW / Math.max(rows.length, 1)}
              height={plotH}
              className="seo-trend-hit"
              onMouseEnter={() => setHover(index)}
            />
          ))}
        </svg>
      )}
    </figure>
  );
}

function TargetKeywords({ project, data, performance, onChanged, onOpenPage }) {
  const [draft, setDraft] = useState("");
  const [keywords, setKeywords] = useState(data.keywords);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setKeywords(data.keywords), [data.keywords]);

  // Search Console 落差：每個目標關鍵字的相關搜尋詞表現，以及有曝光但還不是目標的字詞
  const queries = performance.data?.queries;
  const gapByKeyword = useMemo(
    () => new Map(keywordGap(data.keyword_report, queries).map((gap) => [gap.keyword, gap])),
    [data.keyword_report, queries],
  );
  const opportunities = useMemo(() => untargetedQueries(keywords, queries), [keywords, queries]);

  async function save(next) {
    setSaving(true);
    setError("");
    try {
      const response = await api.post(`/projects/${project.id}/seo/keywords/`, { keywords: next });
      setKeywords(response.data.keywords);
      onChanged();
    } catch (err) {
      setError(apiErrorMessage(err, "無法儲存關鍵字。"));
    } finally {
      setSaving(false);
    }
  }

  function add(event) {
    event.preventDefault();
    const items = draft.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean);
    if (!items.length) return;
    setDraft("");
    save([...keywords, ...items]);
  }

  return (
    <section className="panel">
      <h2 className="project-section-title">目標關鍵字</h2>
      <p className="seo-muted">設定希望被搜尋到的關鍵字，Argus 會檢查它們有沒有出現在頁面的 Title、H1、Description、小標、網址與正文（字面比對，中文不斷詞）。</p>
      <form className="seo-keyword-form" onSubmit={add}>
        <label className="project-sr-only" htmlFor="seo-keyword-input">新增關鍵字</label>
        <input
          id="seo-keyword-input"
          className="input"
          placeholder="輸入關鍵字，多個以逗號分隔"
          value={draft}
          maxLength={200}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" className="secondary-button" disabled={saving || !draft.trim()}>新增</button>
      </form>
      {error && <p className="error-text" role="alert">{error}</p>}
      {keywords.length > 0 && (
        <ul className="seo-keyword-chips">
          {keywords.map((item) => (
            <li key={item}>
              <span>{item}</span>
              <button type="button" aria-label={`移除 ${item}`} disabled={saving} onClick={() => save(keywords.filter((k) => k !== item))}>×</button>
            </li>
          ))}
        </ul>
      )}
      {data.keyword_report.length === 0 ? (
        <p className="hint-text">尚未設定關鍵字。</p>
      ) : (
        <div className="project-table-wrap">
          <table className="project-table seo-keyword-table">
            <thead>
              <tr>
                <th scope="col">關鍵字</th>
                <th scope="col">出現頁數</th>
                <th scope="col">最相關頁面與出現位置</th>
                <th scope="col">Search Console</th>
                <th scope="col">建議</th>
              </tr>
            </thead>
            <tbody>
              {data.keyword_report.map((row) => {
                const gap = performance.data ? gapByKeyword.get(row.keyword) : null;
                return (
                  <tr key={row.keyword}>
                    <td><SearchIcon /> {row.keyword}</td>
                    <td>{row.pages_found}</td>
                    <td>
                      {row.best_page ? (
                        <>
                          <button type="button" className="project-text-link seo-url" onClick={() => onOpenPage(row.best_page.page_id)}>{row.best_page.url}</button>
                          <span className="seo-muted seo-block">{row.best_page.places.join("、")}・正文出現 {row.best_page.body_count} 次</span>
                        </>
                      ) : (
                        <span className="seo-muted">沒有頁面提到</span>
                      )}
                    </td>
                    <td>
                      {gap ? <KeywordGapCell gap={gap} /> : "—"}
                    </td>
                    <td className="seo-muted">
                      {[row.advice, gap?.advice].filter(Boolean).join(" ") || "已出現在重要位置"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="seo-muted">
        依掃描當時保存的頁面內容比對；修改網站後重新掃描才會更新。Search Console 欄位統計包含這個關鍵字的
        搜尋詞（期間內點擊最多的前 200 個），排名是期間平均。
      </p>
      {performance.data && opportunities.length > 0 && (
        <>
          <h3 className="seo-subtitle">有曝光但還不是目標的搜尋詞</h3>
          <p className="seo-muted">這些搜尋詞已經讓網站出現在 Google，但不在目標關鍵字裡；值得經營的可以設為目標，追蹤頁面有沒有好好回應。</p>
          <div className="project-table-wrap">
            <table className="project-table seo-keyword-table">
              <thead>
                <tr>
                  <th scope="col">搜尋詞</th>
                  <th scope="col">曝光</th>
                  <th scope="col">點擊</th>
                  <th scope="col">平均排名</th>
                  <th scope="col">Google 帶到的頁面</th>
                  <th scope="col"><span className="project-sr-only">動作</span></th>
                </tr>
              </thead>
              <tbody>
                {opportunities.map((row) => (
                  <tr key={row.query}>
                    <td>{row.query}</td>
                    <td>{numberFormat.format(row.impressions)}</td>
                    <td>{numberFormat.format(row.clicks)}</td>
                    <td>{row.position.toFixed(1)}</td>
                    <td className="seo-url">{row.page || "—"}</td>
                    <td>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={saving || keywords.length >= MAX_KEYWORDS}
                        title={keywords.length >= MAX_KEYWORDS ? `最多 ${MAX_KEYWORDS} 個目標關鍵字` : undefined}
                        onClick={() => save([...keywords, row.query])}
                      >
                        設為目標
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

/** Search Console 欄：相關搜尋詞的曝光、點擊、最佳平均排名（分段徽章附文字），以及 Google 帶到的頁面。 */
function KeywordGapCell({ gap }) {
  const band = RANK_BAND[gap.status];
  if (gap.status === "none") {
    return <span className={`seo-chip ${band.tone}`}>{band.label}</span>;
  }
  return (
    <>
      <span className={`seo-chip ${band.tone}`}>{band.label}</span>
      <span className="seo-block">
        {gap.queries} 個相關搜尋詞・曝光 {numberFormat.format(gap.impressions)}・點擊 {numberFormat.format(gap.clicks)}
      </span>
      <span className="seo-muted seo-block">最佳平均排名 {gap.bestPosition.toFixed(1)}（「{gap.bestQuery}」）</span>
      {gap.landingMismatch && (
        <span className="seo-muted seo-block">Google 帶到：<span className="seo-url">{gap.landingMismatch}</span></span>
      )}
    </>
  );
}

export { ProjectSeoPage };
