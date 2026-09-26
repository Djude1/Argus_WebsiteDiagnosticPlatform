import { useCallback, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { fetchAdminAuditLog } from "../../api";
import { AdminPagination } from "../../components/admin/AdminPagination";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import type { AdminAuditAction, AdminAuditLogListResponse } from "../../shared/apiContracts";
import { formatDateTime } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery";
import { useArgusStore } from "../../store";
import { errorDetail, toAllowed } from "./adminHelpers";

// 操作日誌（僅超級管理員）。從 AdminPages.jsx 拆出並轉成 TypeScript，同時：
//   · 動作篩選補齊：原本只列 6 種＋其他，漏了實際會寫入的「調整訂閱」「網域驗證
//     人工審核」「掃描任務控制」三種，超管無法只看掃描終止／重排或網域核准的紀錄。
//     改以 Record<AdminAuditAction, string> 宣告，後端新增動作而這裡沒補會是編譯錯誤
//   · 篩選與頁碼改進網址；載入失敗改為錯誤＋重試（原本停在「載入中…」）

const ACTION_LABELS: Record<AdminAuditAction, string> = {
  coin_adjust: "調整點數",
  subscription_adjust: "調整訂閱",
  review_reply: "回覆評論",
  review_moderate: "審核評論",
  review_delete: "刪除評論",
  user_toggle_staff: "切換管理員身份",
  domain_override: "網域驗證人工審核",
  scan_control: "掃描任務控制",
  other: "其他",
};
const ACTIONS = Object.keys(ACTION_LABELS) as AdminAuditAction[];

const AUDIT_QUERY_DEFAULTS = { page: 1, action: "" };

export function AdminAuditLogPage() {
  const me = useArgusStore((s) => s.me);

  if (!me?.is_superuser) {
    return <div className="admin-error">需要超級管理員權限才能查看。</div>;
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <div>
          <h1 className="admin-page-title">操作日誌</h1>
          <p>管理員操作的稽核軌跡（僅超級管理員可見）</p>
        </div>
        <div className="admin-page-head-links">
          <NavLink to="/admin/transactions" className="admin-btn ghost">點數交易 →</NavLink>
          <NavLink to="/admin/scans" className="admin-btn ghost">掃描紀錄 →</NavLink>
        </div>
      </header>

      <div className="admin-panel">
        <AuditLogTable />
      </div>
    </div>
  );
}

function AuditLogTable() {
  const { params, setParam, resetFilters, hasFilters } = useListQuery(AUDIT_QUERY_DEFAULTS);
  const { page, action } = params;
  const [data, setData] = useState<AdminAuditLogListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAdminAuditLog({ page, action: toAllowed(action, ACTIONS) }));
    } catch (err) {
      setError(errorDetail(err, "無法載入操作日誌"));
    } finally {
      setLoading(false);
    }
  }, [page, action]);
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <div className="admin-filter-bar">
        <select
          className="admin-input"
          aria-label="稽核動作"
          value={action}
          onChange={(e) => setParam("action", e.target.value)}
        >
          <option value="">全部動作</option>
          {ACTIONS.map((a) => (
            <option key={a} value={a}>{ACTION_LABELS[a]}</option>
          ))}
        </select>
        {hasFilters && (
          <button type="button" className="admin-btn ghost" onClick={resetFilters}>清除篩選</button>
        )}
      </div>

      {error && <AdminErrorState message="無法載入操作日誌" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入操作日誌中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <th>時間</th>
                <th>動作</th>
                <th>操作者</th>
                <th>對象</th>
                <th>細節</th>
              </tr>
            </thead>
            <tbody>
              {data.logs.map((log) => {
                // payload 在後端是 JSONField，schema 只能給 unknown
                const payload = log.payload && typeof log.payload === "object"
                  ? (log.payload as Record<string, unknown>)
                  : null;
                return (
                  <tr key={log.id}>
                    <td>{formatDateTime(log.created_at)}</td>
                    <td><span className="admin-status">{log.action_label}</span></td>
                    <td><strong>{log.actor_username || "(已刪除)"}</strong></td>
                    <td>{log.target_username || "—"}</td>
                    <td className="admin-cell-secondary">
                      {log.target_object_repr}
                      {payload && Object.keys(payload).length > 0 && (
                        <details className="admin-log-payload">
                          <summary>payload</summary>
                          <pre>
                            {JSON.stringify(payload, null, 2)}
                          </pre>
                        </details>
                      )}
                    </td>
                  </tr>
                );
              })}
              {data.logs.length === 0 && (
                <tr><td colSpan={5} className="admin-empty">
                  {hasFilters ? "沒有符合條件的紀錄" : "尚無紀錄"}
                </td></tr>
              )}
            </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />
        </>
      )}
    </>
  );
}
