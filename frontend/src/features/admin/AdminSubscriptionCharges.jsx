import { useCallback, useEffect, useState } from "react";

import { api } from "../../api";
import { AdminPagination } from "../../components/admin/AdminPagination";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { formatDateTime, formatNtd } from "../../shared/formatters.js";

// 訂閱每期扣款（綠界信用卡定期定額）。電子發票由管理員人工開立（2026-10-04 使用者決策），
// 每一筆成功扣款都要開一張，所以列出每期金額與該訂閱的買受人／發票資料。
// 後端 `/admin/subscription-charges/`（apps/admin_api/views.py::subscription_charges_list）。
export function AdminSubscriptionCharges() {
  const [page, setPage] = useState(1);
  const [onlySucceeded, setOnlySucceeded] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/subscription-charges/", {
        params: { page, succeeded: onlySucceeded ? "true" : undefined },
      });
      setData(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "無法載入訂閱扣款");
    } finally {
      setLoading(false);
    }
  }, [page, onlySucceeded]);

  useEffect(() => { load(); }, [load]);

  return (
    <section className="admin-panel" aria-labelledby="sub-charges-title">
      <h3 id="sub-charges-title">訂閱每期扣款</h3>
      <p className="admin-cell-secondary">
        綠界每月自動扣款的紀錄；每一筆成功的扣款都需要依買受人資料開立一張電子發票。
      </p>
      <label className="admin-checkbox-row">
        <input
          type="checkbox"
          checked={onlySucceeded}
          onChange={(event) => { setOnlySucceeded(event.target.checked); setPage(1); }}
        />
        只看成功扣款
      </label>

      {error && <AdminErrorState message="無法載入訂閱扣款" detail={error} onRetry={load} />}
      {!error && loading && <AdminSkeleton variant="table" rows={4} label="載入訂閱扣款中" />}
      {!error && !loading && data && data.charges.length === 0 && (
        <p className="admin-empty">目前沒有訂閱扣款紀錄。</p>
      )}
      {!error && !loading && data && data.charges.length > 0 && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>時間</th>
                  <th>買受人</th>
                  <th>方案／期數</th>
                  <th className="num">金額</th>
                  <th>結果</th>
                  <th>發票資料</th>
                  <th>綠界編號</th>
                </tr>
              </thead>
              <tbody>
                {data.charges.map((charge) => (
                  <tr key={charge.id}>
                    <td>{formatDateTime(charge.created_at)}</td>
                    <td>
                      <div className="admin-cell-primary">{charge.buyer_name || charge.username}</div>
                      <div className="admin-cell-secondary">{charge.buyer_email}</div>
                    </td>
                    <td>
                      {charge.plan_name}
                      <div className="admin-cell-secondary">第 {charge.sequence} 期・{charge.order_status_label}</div>
                    </td>
                    <td className="num">{formatNtd(charge.amount)}</td>
                    <td>{charge.succeeded ? "成功" : `失敗（${charge.rtn_code} ${charge.rtn_msg}）`}</td>
                    <td>
                      {charge.invoice_type_label}
                      {charge.invoice_type === "company" && (
                        <div className="admin-cell-secondary">{charge.company_name}・統編 {charge.tax_id}</div>
                      )}
                      {charge.invoice_type === "personal" && charge.carrier_id && (
                        <div className="admin-cell-secondary">{charge.carrier_type_label} {charge.carrier_id}</div>
                      )}
                    </td>
                    <td>
                      <div className="admin-cell-secondary">{charge.merchant_trade_no}</div>
                      <div className="admin-cell-secondary">{charge.provider_ref || "—"}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <AdminPagination
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            onChange={setPage}
          />
        </>
      )}
    </section>
  );
}
