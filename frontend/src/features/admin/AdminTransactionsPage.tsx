import { useCallback, useEffect, useState } from "react";

import { fetchAdminTransactions } from "../../api";
import { AdminPagination } from "../../components/admin/AdminPagination";
import { AdminSortableTh } from "../../components/admin/AdminSortableTh";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import type {
  AdminTransactionListParams,
  AdminTransactionListResponse,
  CoinTransactionKind,
} from "../../shared/apiContracts";
import { formatDateTime } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery";
import { errorDetail, toAllowed } from "./adminHelpers";

// 後台交易紀錄。從 AdminPages.jsx 拆出並轉成 TypeScript。
//
// 類型篩選原本只寫死 5 種，但後端 CoinTransaction.Kind 有 11 種（複刻、修正
// 產出、訂閱贈點都漏了），管理員無法只看這幾類交易。現在標籤表以
// Record<CoinTransactionKind, string> 宣告：後端新增類型而這裡沒補標籤，會是編譯錯誤。

const KIND_LABELS: Record<CoinTransactionKind, string> = {
  monthly_bonus: "每月贈點",
  purchase: "購買",
  scan_hold: "掃描預扣",
  scan_refund: "掃描退款",
  admin_adjust: "管理員調整",
  rebuild_hold: "網頁複刻預扣",
  rebuild_refund: "網頁複刻退款",
  fixgen_grant: "修正產出額度贈與",
  fixgen_charge: "修正產出扣款",
  fixgen_refund: "修正產出退款",
  subscription_grant: "訂閱月贈點",
};
const KINDS = Object.keys(KIND_LABELS) as CoinTransactionKind[];

type TransactionOrdering = NonNullable<AdminTransactionListParams["ordering"]>;
const TRANSACTION_ORDERINGS = [
  "created_at", "-created_at",
  "amount", "-amount",
  "balance_after", "-balance_after",
] as const satisfies readonly TransactionOrdering[];

const TRANSACTIONS_QUERY_DEFAULTS = { page: 1, kind: "", ordering: "-created_at" };

export function AdminTransactionsPage() {
  const { params, setParam, resetFilters, hasFilters } = useListQuery(TRANSACTIONS_QUERY_DEFAULTS);
  const { page, kind, ordering } = params;
  const [data, setData] = useState<AdminTransactionListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchAdminTransactions({
        page,
        kind: toAllowed(kind, KINDS),
        ordering: toAllowed(ordering, TRANSACTION_ORDERINGS),
      }));
    } catch (err) {
      setError(errorDetail(err, "無法載入交易紀錄"));
    } finally {
      setLoading(false);
    }
  }, [page, kind, ordering]);
  useEffect(() => { load(); }, [load]);

  const setOrdering = (o: string) => setParam("ordering", o);

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>交易紀錄</h1>
        <p>所有 coin 異動的審計紀錄</p>
      </header>

      <div className="admin-filter-bar">
        <select
          className="admin-input"
          aria-label="交易類型"
          value={kind}
          onChange={(e) => setParam("kind", e.target.value)}
        >
          <option value="">全部類型</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>{KIND_LABELS[k]}</option>
          ))}
        </select>
        {hasFilters && (
          <button type="button" className="admin-btn ghost" onClick={resetFilters}>清除篩選</button>
        )}
      </div>

      {error && <AdminErrorState message="無法載入交易紀錄" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入交易中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <AdminSortableTh field="created_at" ordering={ordering} onChange={setOrdering}>時間</AdminSortableTh>
                {/* 這欄實際顯示交易對象（掃描網址或方案名），原欄名「使用者」與內容不符 */}
                <th>來源對象</th>
                <th>類型</th>
                <AdminSortableTh field="amount" ordering={ordering} onChange={setOrdering} numeric>變動</AdminSortableTh>
                <AdminSortableTh field="balance_after" ordering={ordering} onChange={setOrdering} numeric>餘額</AdminSortableTh>
                <th>操作者 / 方案</th><th>備註</th>
              </tr>
            </thead>
            <tbody>
              {data.transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{formatDateTime(tx.created_at)}</td>
                  <td>{tx.scan_origin || (tx.plan_name ? `購買 ${tx.plan_name}` : "—")}</td>
                  <td>{tx.kind_label}</td>
                  <td className={`num ${tx.amount > 0 ? "tx-pos" : "tx-neg"}`}>{tx.amount > 0 ? "+" : ""}{tx.amount}</td>
                  <td className="num">{tx.balance_after}</td>
                  <td>{tx.admin_actor_username ? `admin: ${tx.admin_actor_username}` : (tx.plan_name || tx.scan_origin || "—")}</td>
                  <td className="admin-cell-secondary">{tx.note}</td>
                </tr>
              ))}
              {data.transactions.length === 0 && (
                <tr><td colSpan={7} className="admin-empty">沒有符合的交易</td></tr>
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
