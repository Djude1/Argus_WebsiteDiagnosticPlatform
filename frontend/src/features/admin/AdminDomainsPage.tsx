import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminDomainOverride, fetchAdminDomains } from "../../api";
import { AdminPagination } from "../../components/admin/AdminPagination";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { useConfirmDialogs } from "../../shared/AppShared.jsx";
import type {
  AdminDomainListResponse,
  AdminVerifiedDomain,
  VerifiedDomainStatus,
} from "../../shared/apiContracts";
import { formatDateTime } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery";
import { errorDetail, toAllowed } from "./adminHelpers";

// 後台網域管理：所有使用者的網域所有權驗證清單＋人工審核。
// 人工核准等同驗證通過，會直接開放該網域的主動式測試，所以核准／否決都要二次確認。
//
// 從 AdminPages.jsx 拆出並轉成 TypeScript，同時：
//   · 搜尋、狀態、頁碼改進網址（useListQuery）——原本存在元件 state，重新整理或
//     按上一頁就會遺失，也無法分享或從別頁帶篩選連過來；其餘後台列表都已是這樣
//   · 載入失敗改為區塊級錯誤＋重試——原本跳出對話框後頁面停在「載入中…」

const STATUS_LABELS: Record<VerifiedDomainStatus, string> = {
  pending: "待驗證",
  verified: "已驗證",
  rejected: "已否決",
  expired: "已過期",
};
const STATUSES = Object.keys(STATUS_LABELS) as VerifiedDomainStatus[];

const DOMAINS_QUERY_DEFAULTS = { page: 1, q: "", status: "" };

export function AdminDomainsPage() {
  const { params, setParam, setParams, resetFilters, hasFilters } = useListQuery(DOMAINS_QUERY_DEFAULTS);
  const { page, q, status } = params;
  const [data, setData] = useState<AdminDomainListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchDraft, setSearchDraft] = useState(q);
  const [notes, setNotes] = useState<Record<number, string>>({}); // domainId -> 審核備註草稿
  const [busyId, setBusyId] = useState<number | null>(null);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  useEffect(() => { setSearchDraft(q); }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAdminDomains({
        page,
        q: q || undefined,
        status: toAllowed(status, STATUSES),
      }));
    } catch (err) {
      setError(errorDetail(err, "無法載入網域清單"));
    } finally {
      setLoading(false);
    }
  }, [page, q, status]);
  useEffect(() => { load(); }, [load]);

  function handleSearchSubmit(e: FormEvent) {
    e.preventDefault();
    setParams({ q: searchDraft.trim() });
  }

  async function handleOverride(domain: AdminVerifiedDomain, approve: boolean) {
    const note = (notes[domain.id] || "").trim();
    const ok = await confirmDialog(
      approve
        ? `確定人工核准「${domain.domain}」（${domain.username}）？核准後同等於驗證通過，可直接用於主動式測試。`
        : `確定否決「${domain.domain}」（${domain.username}）？否決後該網域將無法用於主動式測試。`,
      { danger: !approve },
    );
    if (!ok) return;
    setBusyId(domain.id);
    try {
      const updated = await adminDomainOverride(domain.id, approve, note);
      setData((current) =>
        current
          ? { ...current, domains: current.domains.map((d) => (d.id === updated.id ? updated : d)) }
          : current,
      );
      setNotes((current) => ({ ...current, [domain.id]: "" }));
    } catch (err) {
      notifyDialog(errorDetail(err, "操作失敗，請稍後再試。"));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1 className="admin-page-title">網域管理</h1>
        <p>所有使用者的網域所有權驗證清單；無法自行驗證的網域可人工核准（同等於驗證通過）或否決。</p>
      </header>

      <div className="admin-filter-bar">
        <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
          <input
            className="admin-input"
            type="search"
            placeholder="搜尋網域或使用者名稱…"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            aria-label="搜尋網域或使用者"
          />
          <button className="admin-btn" type="submit">搜尋</button>
        </form>
        <select
          className="admin-input"
          aria-label="驗證狀態"
          value={status}
          onChange={(e) => setParam("status", e.target.value)}
        >
          <option value="">全部狀態</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        {hasFilters && (
          <button type="button" className="admin-btn ghost" onClick={resetFilters}>清除篩選</button>
        )}
      </div>

      {error && <AdminErrorState message="無法載入網域清單" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={6} label="載入網域中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table compact">
              <thead>
                <tr>
                  <th>網域</th>
                  <th>使用者</th>
                  <th>狀態</th>
                  <th>驗證方法</th>
                  <th>到期日</th>
                  <th>人工核准</th>
                  <th>最後錯誤</th>
                  <th>審核</th>
                </tr>
              </thead>
              <tbody>
                {data.domains.map((domain) => (
                  <tr key={domain.id}>
                    <td className="admin-cell-mono">{domain.domain}</td>
                    <td>{domain.username}</td>
                    <td>
                      <span
                        className={`admin-domain-status is-${domain.status}${domain.is_effectively_verified ? " is-effective" : ""}`}
                      >
                        {domain.status_label}
                      </span>
                      {domain.is_effectively_verified && (
                        <span className="admin-domain-effective" title="掃描閘門判定：生效中">生效中</span>
                      )}
                    </td>
                    <td>{domain.method ? domain.method_label : "—"}</td>
                    <td>{formatDateTime(domain.expires_at)}</td>
                    <td className="admin-cell-secondary">
                      {domain.admin_override
                        ? `${domain.admin_actor_username ? `by ${domain.admin_actor_username}` : "是"}${domain.admin_note ? ` · ${domain.admin_note}` : ""}`
                        : "—"}
                    </td>
                    <td className="admin-cell-secondary admin-domain-error">{domain.last_error || "—"}</td>
                    <td>
                      <div className="admin-domain-review">
                        <input
                          className="admin-input admin-domain-note"
                          placeholder="備註（選填）"
                          value={notes[domain.id] || ""}
                          onChange={(e) =>
                            setNotes((current) => ({ ...current, [domain.id]: e.target.value }))
                          }
                          aria-label={`${domain.domain} 審核備註`}
                        />
                        <button
                          className="admin-btn small"
                          type="button"
                          disabled={busyId === domain.id}
                          onClick={() => handleOverride(domain, true)}
                        >
                          {busyId === domain.id ? "…" : "人工核准"}
                        </button>
                        <button
                          className="admin-btn small danger"
                          type="button"
                          disabled={busyId === domain.id}
                          onClick={() => handleOverride(domain, false)}
                        >
                          否決
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {data.domains.length === 0 && (
                  <tr><td colSpan={8} className="admin-empty">
                    {hasFilters ? "沒有符合條件的網域" : "尚無任何網域驗證申請"}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
          <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />
        </>
      )}
      {dialogHost}
    </div>
  );
}
