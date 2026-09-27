import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";

import {
  adminCancelScan,
  adminRequeueScan,
  fetchAdminScanDetail,
  fetchAdminScans,
} from "../../api";
import { activateAdminRow } from "../../components/admin/activateAdminRow";
import {
  AdminAlertIcon,
  AdminOrdersIcon,
  AdminScansIcon,
  AdminTrendIcon,
} from "../../components/admin/AdminIcons.jsx";
import { AdminPagination } from "../../components/admin/AdminPagination";
import { AdminSortableTh } from "../../components/admin/AdminSortableTh";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { useConfirmDialogs } from "../../shared/AppShared.jsx";
import type {
  AdminScanDetailResponse,
  AdminScanListParams,
  AdminScanListResponse,
} from "../../shared/apiContracts";
import { formatDateTime, formatDuration } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery";
import { STATUS_OPTIONS, errorDetail, statusLabel, toAllowed, toPositiveInt } from "./adminHelpers";

// 後台掃描列表與掃描詳情。
//
// 從 AdminPages.jsx 拆出並轉成 TypeScript，因為這裡正是後台兩次「靜默失效」
// 的現場：`?user=` 沒宣告導致列表不篩選、`user_id` 沒進 serializer 導致
// 「查看使用者」連結永遠不出現。兩者現在都由產生的 API 型別在編譯期擋下，
// 並由 AdminScansPages.test.tsx 在畫面層再鎖一次。

type ScanOrdering = NonNullable<AdminScanListParams["ordering"]>;

// 網址上的 ordering 可能是任何字串；只把白名單內的值送給後端（見 adminHelpers.toAllowed）。
// `satisfies` 確保這裡不會拼錯——拼錯是編譯錯誤。
const SCAN_ORDERINGS = [
  "created_at", "-created_at",
  "overall_score", "-overall_score",
  "pages_count", "-pages_count",
  "findings_count", "-findings_count",
] as const satisfies readonly ScanOrdering[];

const SCANS_QUERY_DEFAULTS = { page: 1, q: "", status: "", user: "", ordering: "-created_at" };

export function AdminScansPage() {
  const navigate = useNavigate();
  const { params, setParam, setParams, resetFilters, hasFilters } = useListQuery(SCANS_QUERY_DEFAULTS);
  const { page, q, status: statusFilter, user: userFilter, ordering } = params;
  const [data, setData] = useState<AdminScanListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchDraft, setSearchDraft] = useState(q);

  useEffect(() => { setSearchDraft(q); }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAdminScans({
        q: q || undefined,
        status: statusFilter || undefined,
        user: toPositiveInt(userFilter),
        page,
        ordering: toAllowed(ordering, SCAN_ORDERINGS),
      }));
    } catch (err) {
      setError(errorDetail(err, "無法載入掃描任務"));
    } finally {
      setLoading(false);
    }
  }, [q, statusFilter, userFilter, page, ordering]);
  useEffect(() => { load(); }, [load]);

  function handleSearchSubmit(e: FormEvent) {
    e.preventDefault();
    setParams({ q: searchDraft.trim() });
  }

  const setOrdering = (o: string) => setParam("ordering", o);

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>掃描</h1>
        <p>所有使用者的掃描任務</p>
      </header>

      <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
        <input
          className="admin-input"
          placeholder="搜尋網址或使用者"
          aria-label="搜尋掃描"
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
        />
        <select
          className="admin-input"
          aria-label="掃描狀態"
          value={statusFilter}
          onChange={(e) => setParam("status", e.target.value)}
        >
          <option value="">全部狀態</option>
          {STATUS_OPTIONS.map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
        <button className="admin-btn" type="submit">搜尋</button>
        {hasFilters && (
          <button type="button" className="admin-btn ghost" onClick={resetFilters}>清除篩選</button>
        )}
      </form>

      {userFilter && (
        <div className="admin-scope-note">
          <span>目前只顯示單一使用者的掃描</span>
          <button type="button" className="admin-btn ghost" onClick={() => setParam("user", "")}>
            顯示全部使用者
          </button>
        </div>
      )}

      {error && <AdminErrorState message="無法載入掃描任務" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入掃描中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <AdminSortableTh field="created_at" ordering={ordering} onChange={setOrdering}>時間</AdminSortableTh>
                <th>使用者</th><th>網址</th>
                <th>狀態</th><th>模式</th>
                <AdminSortableTh field="overall_score" ordering={ordering} onChange={setOrdering} numeric>分數</AdminSortableTh>
                <AdminSortableTh field="pages_count" ordering={ordering} onChange={setOrdering} numeric>頁數</AdminSortableTh>
                <AdminSortableTh field="findings_count" ordering={ordering} onChange={setOrdering} numeric>問題</AdminSortableTh>
                {/* 耗時不可排序：duration_sec 是 serializer 由 started_at/completed_at 現算的，資料庫無此欄位 */}
                <th className="num">耗時</th>
              </tr>
            </thead>
            <tbody>
              {data.scans.map((s) => (
                <tr
                  key={s.id}
                  className="clickable"
                  role="link"
                  tabIndex={0}
                  onClick={() => navigate(`/admin/scans/${s.id}`)}
                  onKeyDown={(event) => activateAdminRow(
                    event,
                    () => navigate(`/admin/scans/${s.id}`),
                  )}
                >
                  <td>{formatDateTime(s.created_at)}</td>
                  <td>{s.username}</td>
                  <td className="truncate" title={s.origin}>{s.origin}</td>
                  <td><span className={`admin-status ${s.status}`}>{statusLabel(s.status)}</span></td>
                  <td>{s.scan_mode === "active" ? "主動" : "被動"}</td>
                  <td className="num">{s.overall_score ?? "—"}</td>
                  <td className="num">{s.pages_count}</td>
                  <td className="num">{s.findings_count}</td>
                  <td className="num">{formatDuration(s.duration_sec)}</td>
                </tr>
              ))}
              {data.scans.length === 0 && (
                <tr><td colSpan={9} className="admin-empty">沒有符合的掃描</td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />
        </>
      )}
    </div>
  );
}

// ---- 以下 JSON 欄位在後端是 JSONField，schema 只能給 unknown；結構依產生端描述 ----

/** 來源：apps/scans/scanners.py 計算 top_actions 處（依 priority_score 降冪取前 5） */
type TopAction = {
  title: string;
  category: string;
  severity: string;
  priority_score?: number | null;
};

type WarningRow = string | { url?: string; reason?: string };

/** 來源：apps/scans/crawler.py 的 warning_summary */
type WarningSummary = {
  blocked_urls?: WarningRow[];
  failed_urls?: WarningRow[];
  screenshot_failures?: WarningRow[];
  tech_stack?: unknown[];
};

const WARNING_GROUPS = [
  { key: "blocked_urls", label: "被阻擋的 URL", hint: "robots.txt / 403 / 429", tone: "warn" },
  { key: "failed_urls", label: "抓取失敗的 URL", hint: "連線或解析失敗", tone: "bad" },
  { key: "screenshot_failures", label: "截圖失敗", hint: "頁面有抓到，但截圖沒成功", tone: "warn" },
] as const;

// 爬取警告面板。清單可能很長，預設收合只顯示筆數，展開才列出明細。
function AdminScanWarnings({ summary }: { summary: WarningSummary | null | undefined }) {
  const present = WARNING_GROUPS.filter((g) => (summary?.[g.key] || []).length > 0);
  const techStack = summary?.tech_stack || [];
  if (present.length === 0 && techStack.length === 0) return null;

  return (
    <section className="admin-panel">
      <h3><span className="admin-panel-icon-chip"><AdminAlertIcon /></span>爬取警告</h3>

      {techStack.length > 0 && (
        <div className="admin-tech-stack">
          <span className="admin-cell-secondary">偵測到的技術棧：</span>
          {techStack.map((tech, index) => (
            <span className="admin-tech-chip" key={`${String(tech)}-${index}`}>
              {typeof tech === "string" ? tech : JSON.stringify(tech)}
            </span>
          ))}
        </div>
      )}

      {present.map((group) => {
        const rows = summary?.[group.key] || [];
        return (
          <details className="admin-warn-group" key={group.key}>
            <summary>
              <span className={`admin-warn-count tone-${group.tone}`}>{rows.length}</span>
              <span className="admin-warn-label">{group.label}</span>
              <span className="admin-cell-secondary">{group.hint}</span>
            </summary>
            <ul className="admin-warn-list">
              {rows.map((row, index) => (
                <li key={`${group.key}-${index}`}>
                  <code className="admin-warn-url">
                    {typeof row === "string" ? row : (row.url || JSON.stringify(row))}
                  </code>
                  {typeof row !== "string" && row?.reason && (
                    <span className="admin-warn-reason">{row.reason}</span>
                  )}
                </li>
              ))}
            </ul>
          </details>
        );
      })}
    </section>
  );
}

// 掃描進行中與可重排的狀態集合；與後端 admin_api/views.py 的判定一致
const CANCELLABLE_STATUSES = ["queued", "crawling", "scanning", "agent_testing"];
const REQUEUEABLE_STATUSES = ["failed", "cancelled"];

type Feedback = { tone: "good" | "bad"; message: string };

export function AdminScanDetailPage() {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<AdminScanDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();
  const id = Number(scanId);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await fetchAdminScanDetail(id));
    } catch (err) {
      setError(errorDetail(err, "找不到此掃描"));
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function handleCancel() {
    const ok = await confirmDialog(
      "確定終止這個掃描嗎？worker 會在下一個檢查點停下，預扣的點數會全額退回使用者。",
      { danger: true },
    );
    if (!ok) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await adminCancelScan(id);
      setFeedback({
        tone: "good",
        message: result.refunded > 0
          ? `已終止，退回 ${result.refunded} coin。`
          : "已終止（此掃描沒有待退的預扣）。",
      });
      await load();
    } catch (err) {
      notifyDialog(errorDetail(err, "終止失敗"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRequeue() {
    const ok = await confirmDialog(
      "確定重新排入佇列嗎？依產品決策重排不會再次扣點，等同免費重跑一次，"
      + "這個動作會寫入操作日誌。",
      { danger: false },
    );
    if (!ok) return;
    setBusy(true);
    setFeedback(null);
    try {
      await adminRequeueScan(id);
      setFeedback({ tone: "good", message: "已重新排入佇列，未扣點。" });
      await load();
    } catch (err) {
      notifyDialog(errorDetail(err, "重排失敗"));
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <div className="admin-page">
        <AdminErrorState message="無法載入掃描" detail={error} onRetry={load} />
      </div>
    );
  }
  if (!data) return <div className="admin-page"><AdminSkeleton variant="detail" rows={3} /></div>;
  const s = data.scan;
  const canCancel = CANCELLABLE_STATUSES.includes(s.status);
  const canRequeue = REQUEUEABLE_STATUSES.includes(s.status);
  const categoryScores = (data.category_scores || {}) as Record<string, number>;
  const topActions = (data.top_actions || []) as TopAction[];

  return (
    <div className="admin-page">
      <button type="button" className="admin-back-link" onClick={() => navigate("/admin/scans")}>← 回掃描列表</button>
      <header className="admin-page-head">
        <div>
          <h1>掃描 #{s.id}</h1>
          <p>{s.origin} · {s.username}</p>
        </div>
        <div className="admin-page-head-links">
          {canCancel && (
            <button type="button" className="admin-btn danger" disabled={busy} onClick={handleCancel}>
              {busy ? "處理中…" : "終止掃描"}
            </button>
          )}
          {canRequeue && (
            <button type="button" className="admin-btn primary" disabled={busy} onClick={handleRequeue}>
              {busy ? "處理中…" : "重新排入佇列"}
            </button>
          )}
        </div>
      </header>

      {feedback && (
        <div className={`admin-feedback tone-${feedback.tone}`}>{feedback.message}</div>
      )}

      <div className="admin-grid-2col">
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminScansIcon /></span>狀態</h3>
          <dl className="admin-dl">
            <dt>狀態</dt><dd><span className={`admin-status ${s.status}`}>{statusLabel(s.status)}</span></dd>
            <dt>模式</dt><dd>{s.scan_mode === "active" ? "主動測試" : "被動偵測"}</dd>
            <dt>建立時間</dt><dd>{formatDateTime(s.created_at)}</dd>
            <dt>完成時間</dt><dd>{formatDateTime(s.completed_at)}</dd>
            <dt>耗時</dt><dd>{formatDuration(s.duration_sec)}</dd>
          </dl>
        </section>

        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminOrdersIcon /></span>結果摘要</h3>
          <dl className="admin-dl">
            <dt>總分</dt><dd>{s.overall_score ?? "—"}</dd>
            <dt>頁數</dt><dd>{s.pages_count}</dd>
            <dt>問題數</dt><dd>{s.findings_count}</dd>
            <dt>最大頁數設定</dt><dd>{s.max_pages}</dd>
          </dl>
        </section>
      </div>

      {Object.keys(categoryScores).length > 0 && (
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminTrendIcon /></span>各類別分數</h3>
          <div className="admin-cat-scores">
            {Object.entries(categoryScores).map(([cat, score]) => (
              <div key={cat} className="admin-cat-score-item">
                <div className="admin-cat-score-label">{cat.toUpperCase()}</div>
                <div className="admin-cat-score-value">{Math.round(score)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 優先處置建議：後端已依 priority_score 降冪排好 */}
      {topActions.length > 0 && (
        <section className="admin-panel">
          <h3><span className="admin-panel-icon-chip"><AdminAlertIcon /></span>優先處置建議（{topActions.length}）</h3>
          <ol className="admin-top-actions">
            {topActions.map((action, index) => (
              <li className="admin-top-action" key={`${action.title}-${index}`}>
                <span className="admin-top-action-rank">{index + 1}</span>
                <div className="admin-top-action-body">
                  <div className="admin-top-action-title">{action.title}</div>
                  <div className="admin-top-action-meta">
                    <span className={`severity ${action.severity}`}>{action.severity}</span>
                    <span className={`category-pill cat-${action.category}`}>
                      {String(action.category || "").toUpperCase()}
                    </span>
                    <span className="admin-cell-secondary">
                      priority {Math.round(action.priority_score || 0)}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* 爬取警告：被 robots/403/429 擋掉與抓取失敗的 URL。
          分數偏低時多半能在這裡找到原因（爬不到頁就評不了分）。 */}
      <AdminScanWarnings summary={data.warning_summary as WarningSummary | null} />

      {data.error_message && (
        <section className="admin-panel admin-panel-danger">
          <h3><span className="admin-panel-icon-chip"><AdminAlertIcon /></span>錯誤訊息</h3>
          <pre className="admin-error-pre">{data.error_message}</pre>
        </section>
      )}

      <div className="admin-link-row">
        <NavLink to={`/scans/${s.id}`} className="admin-btn">
          以使用者視角查看詳情報告 →
        </NavLink>
        {/* 已完成的掃描其預扣已結算，不適用 refund_full_for_scan；
            要補償得走使用者頁的「調整點數」，不另做第二套退款路徑。 */}
        {s.user_id && (
          <NavLink to={`/admin/users/${s.user_id}`} className="admin-btn">
            查看使用者 / 調整點數 →
          </NavLink>
        )}
      </div>
      {dialogHost}
    </div>
  );
}
