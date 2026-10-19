import { useCallback, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

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
import { errorDetail, toAllowed, toPositiveInt } from "./adminHelpers";

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

// user：從使用者詳情「查看全部交易」帶進來的篩選（後端 ?user_id=），與掃描頁的 ?user= 同一條路
const TRANSACTIONS_QUERY_DEFAULTS = { page: 1, kind: "", user: "", ordering: "-created_at" };

export function AdminTransactionsPage() {
  const { params, setParam, resetFilters, hasFilters } = useListQuery(TRANSACTIONS_QUERY_DEFAULTS);
  const { page, kind, user: userFilter, ordering } = params;
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
        user_id: toPositiveInt(userFilter),
        ordering: toAllowed(ordering, TRANSACTION_ORDERINGS),
      }));
    } catch (err) {
      setError(errorDetail(err, "無法載入交易紀錄"));
    } finally {
      setLoading(false);
    }
  }, [page, kind, userFilter, ordering]);
  useEffect(() => { load(); }, [load]);

  const setOrdering = (o: string) => setParam("ordering", o);

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>點數交易</h1>
        <p>所有使用者 coin 異動的帳本；紀錄不可修改，補正用「管理員調整」新增一筆</p>
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

      {userFilter && (
        <div className="admin-scope-note">
          <span>目前只顯示單一使用者的交易</span>
          <button type="button" className="admin-btn ghost" onClick={() => setParam("user", "")}>
            顯示全部使用者
          </button>
        </div>
      )}

      {error && <AdminErrorState message="無法載入交易紀錄" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入交易中" />}
      {!error && !loading && data && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
            <thead>
              <tr>
                <AdminSortableTh field="created_at" ordering={ordering} onChange={setOrdering}>時間</AdminSortableTh>
                <th>使用者</th>
                <th>類型</th>
                {/* 對象＝這筆交易是為了哪個掃描或方案；操作者只在管理員調整時有值 */}
                <th>對象</th>
                <AdminSortableTh field="amount" ordering={ordering} onChange={setOrdering} numeric>變動</AdminSortableTh>
                <AdminSortableTh field="balance_after" ordering={ordering} onChange={setOrdering} numeric>餘額</AdminSortableTh>
                <th>操作者</th><th>備註</th>
              </tr>
            </thead>
            <tbody>
              {data.transactions.map((tx) => (
                <tr key={tx.id}>
                  <td>{formatDateTime(tx.created_at)}</td>
                  <td><NavLink className="admin-cell-primary" to={`/admin/users/${tx.user_id}`}>{tx.username}</NavLink></td>
                  <td>{tx.kind_label}</td>
                  <td className="truncate" title={tx.scan_origin || tx.plan_name || undefined}>
                    {tx.scan_origin || tx.plan_name || "—"}
                  </td>
                  <td className={`num ${tx.amount > 0 ? "tx-pos" : "tx-neg"}`}>{tx.amount > 0 ? "+" : ""}{tx.amount}</td>
                  <td className="num">{tx.balance_after}</td>
                  <td>{tx.admin_actor_username || "—"}</td>
                  <td className="admin-cell-secondary">{tx.note}</td>
                </tr>
              ))}
              {data.transactions.length === 0 && (
                <tr><td colSpan={8} className="admin-empty">沒有符合的交易</td></tr>
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
