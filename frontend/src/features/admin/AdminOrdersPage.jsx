import { useCallback, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

import { api } from "../../api";
import { AdminOrdersIcon } from "../../components/admin/AdminIcons.jsx";
import { AdminModal } from "../../components/admin/AdminModal";
import { AdminPagination } from "../../components/admin/AdminPagination";
import {
  AdminEmptyState,
  AdminErrorState,
  AdminSkeleton,
} from "../../components/admin/AdminStates";
import { AdminSortableTh } from "../../components/admin/AdminSortableTh";
import { formatDateTime, formatNtd, formatNumber } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery";

// 訂單管理。
//
// 後端 `/admin/orders/`（apps/admin_api/views.py::orders_list）早就實作完成，
// 支援 q（buyer_email / buyer_name / company_name / tax_id / username）、status
// 與 invoice_type 篩選，但前端一直沒有任何 UI——概覽頁顯示訂單數卻點不進去，
// 發票與統編類客訴在後台無從查起。這一頁把既有能力接上，後端零改動。

// 狀態值取自 billing/models.py::PurchaseOrder.Status（pending / paid / cancelled）
const STATUS_TABS = [
  { value: "", label: "全部" },
  { value: "paid", label: "已付款" },
  { value: "pending", label: "處理中" },
  { value: "cancelled", label: "已取消" },
];

const STATUS_TONE = {
  paid: "good",
  pending: "warn",
  cancelled: "muted",
};

// 網址參數預設值；與預設相同的值不會寫進 query string
const QUERY_DEFAULTS = {
  page: 1,
  q: "",
  status: "",
  invoice_type: "",
  ordering: "-created_at",
};

const INVOICE_OPTIONS = [
  { value: "", label: "全部發票類型" },
  { value: "personal", label: "個人發票" },
  { value: "company", label: "公司發票" },
];

function OrderStatusBadge({ status, label }) {
  // 狀態同時用色彩、圓點與文字三重編碼，不讓色盲使用者只能靠顏色判讀
  return (
    <span className={`admin-order-status tone-${STATUS_TONE[status] || "muted"}`}>
      <span className="admin-order-status-dot" aria-hidden="true" />
      {label || status}
    </span>
  );
}

export function AdminOrdersPage() {
  const { params, setParam, setParams, resetFilters, hasFilters } = useListQuery(QUERY_DEFAULTS);
  const { page, q, status, invoice_type: invoiceType, ordering } = params;
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  // 輸入框是本地暫存，送出才進網址——每打一個字就改網址會塞爆 history
  const [searchDraft, setSearchDraft] = useState(q);
  const [detail, setDetail] = useState(null);

  // 從網址還原（例如從詳情頁返回、或別人貼過來的連結）時同步輸入框
  useEffect(() => { setSearchDraft(q); }, [q]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get("/admin/orders/", {
        params: {
          page,
          q: q || undefined,
          status: status || undefined,
          invoice_type: invoiceType || undefined,
          ordering,
        },
      });
      setData(response.data);
    } catch (err) {
      // 保留真實原因，不再用 .catch(() => setError("失敗")) 把它吞掉
      setError(err?.response?.data?.detail || err?.message || "無法載入訂單");
    } finally {
      setLoading(false);
    }
  }, [page, q, status, invoiceType, ordering]);

  useEffect(() => { load(); }, [load]);

  function handleSearchSubmit(event) {
    event.preventDefault();
    setParams({ q: searchDraft.trim() });
  }

  const hasFilter = hasFilters;
  const clearFilters = resetFilters;

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <div>
          <h1>訂單</h1>
          <p>購點訂單、發票資訊與付款狀態</p>
        </div>
      </header>

      <div className="admin-segmented" role="tablist" aria-label="訂單狀態">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={status === tab.value}
            className={`admin-segment ${status === tab.value ? "active" : ""}`}
            onClick={() => setParam("status", tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <form className="admin-search-bar" onSubmit={handleSearchSubmit}>
        <input
          className="admin-input"
          placeholder="搜尋 email、姓名、公司名或統編"
          aria-label="搜尋訂單"
          value={searchDraft}
          onChange={(event) => setSearchDraft(event.target.value)}
        />
        <select
          className="admin-input"
          aria-label="發票類型"
          value={invoiceType}
          onChange={(event) => setParam("invoice_type", event.target.value)}
        >
          {INVOICE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <button className="admin-btn" type="submit">搜尋</button>
        {hasFilter && (
          <button type="button" className="admin-btn ghost" onClick={clearFilters}>
            清除篩選
          </button>
        )}
      </form>

      {error && <AdminErrorState message="無法載入訂單" detail={error} onRetry={load} />}

      {!error && loading && <AdminSkeleton variant="table" rows={8} label="載入訂單中" />}

      {!error && !loading && data && data.orders.length === 0 && (
        <AdminEmptyState
          icon={<AdminOrdersIcon />}
          title={hasFilter ? "沒有符合條件的訂單" : "尚無訂單"}
          description={hasFilter
            ? "目前的搜尋或篩選條件沒有比對到任何訂單。"
            : "使用者完成購點結帳後，訂單會出現在這裡。"}
          actionLabel={hasFilter ? "清除篩選" : undefined}
          onAction={hasFilter ? clearFilters : undefined}
        />
      )}

      {!error && !loading && data && data.orders.length > 0 && (
        <>
          <div className="admin-table-scroll">
            <table className="admin-table">
              <thead>
                <tr>
                  <AdminSortableTh field="created_at" ordering={ordering} onChange={(o) => setParam("ordering", o)}>時間</AdminSortableTh>
                  <th>使用者</th>
                  <th>方案</th>
                  <AdminSortableTh field="price_ntd" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>金額</AdminSortableTh>
                  <AdminSortableTh field="coin_amount" ordering={ordering} onChange={(o) => setParam("ordering", o)} numeric>Coin</AdminSortableTh>
                  <th>狀態</th>
                  <th>發票</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((order) => (
                  <tr
                    key={order.id}
                    className="clickable"
                    role="button"
                    tabIndex={0}
                    aria-label={`查看訂單 #${order.id} 明細`}
                    onClick={() => setDetail(order)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setDetail(order);
                      }
                    }}
                  >
                    <td>{formatDateTime(order.created_at)}</td>
                    <td>
                      <div className="admin-cell-primary">{order.buyer_name || order.username}</div>
                      <div className="admin-cell-secondary">{order.buyer_email}</div>
                    </td>
                    <td>{order.plan_name || "—"}</td>
                    <td className="num">{formatNtd(order.price_ntd)}</td>
                    <td className="num"><span className="admin-coin">{formatNumber(order.coin_amount)}</span></td>
                    <td><OrderStatusBadge status={order.status} label={order.status_label} /></td>
                    <td>
                      {order.invoice_type_label || "—"}
                      {order.tax_id && <div className="admin-cell-secondary">統編 {order.tax_id}</div>}
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
            onChange={(next) => setParam("page", next)}
          />
        </>
      )}

      {/* 明細用 modal 就地展開，不跳頁——客服多半在對照列表與單筆之間來回 */}
      <AdminModal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail ? `訂單 #${detail.id}` : ""}
        size="sm"
        footer={
          <button type="button" className="admin-btn" onClick={() => setDetail(null)}>
            關閉
          </button>
        }
      >
        {detail && (
          <>
            <dl className="admin-dl">
              <dt>狀態</dt>
              <dd><OrderStatusBadge status={detail.status} label={detail.status_label} /></dd>
              <dt>建立時間</dt><dd>{formatDateTime(detail.created_at)}</dd>
              <dt>付款時間</dt><dd>{formatDateTime(detail.paid_at)}</dd>
              <dt>方案</dt><dd>{detail.plan_name || "—"}</dd>
              <dt>金額</dt><dd>{formatNtd(detail.price_ntd)}</dd>
              <dt>Coin</dt><dd>{formatNumber(detail.coin_amount)}</dd>
            </dl>
            <h3 className="admin-modal-subhead">買受人</h3>
            <dl className="admin-dl">
              <dt>帳號</dt><dd>{detail.username || "—"}</dd>
              <dt>姓名</dt><dd>{detail.buyer_name || "—"}</dd>
              <dt>Email</dt><dd>{detail.buyer_email || "—"}</dd>
              <dt>發票類型</dt><dd>{detail.invoice_type_label || "—"}</dd>
              {detail.invoice_type === "company" && (
                <>
                  <dt>公司名稱</dt><dd>{detail.company_name || "—"}</dd>
                  <dt>統一編號</dt><dd>{detail.tax_id || "—"}</dd>
                </>
              )}
            </dl>
            <div className="admin-link-row">
              <NavLink className="admin-btn" to="/admin/transactions">
                查看點數交易紀錄 →
              </NavLink>
            </div>
          </>
        )}
      </AdminModal>
    </div>
  );
}
