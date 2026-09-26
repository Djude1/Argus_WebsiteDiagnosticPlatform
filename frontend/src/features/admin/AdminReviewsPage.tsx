import { useCallback, useEffect, useState } from "react";

import {
  adminDeleteReviewReply,
  adminModerateReview,
  adminReplyReview,
  fetchAdminReviews,
} from "../../api";
import { AdminStarIcon } from "../../components/admin/AdminIcons.jsx";
import { AdminPagination } from "../../components/admin/AdminPagination";
import { AdminStatCard } from "../../components/admin/AdminStatCard";
import { AdminErrorState, AdminSkeleton } from "../../components/admin/AdminStates";
import { StatusDoneGlyph, useConfirmDialogs } from "../../shared/AppShared.jsx";
import type { AdminReview, AdminReviewListResponse } from "../../shared/apiContracts";
import { formatDateTime } from "../../shared/formatters.js";
import { useListQuery } from "../../shared/useListQuery";
import { errorDetail, toAllowed } from "./adminHelpers";

// 後台評論治理：官方回覆、檢舉與公開狀態。從 AdminPages.jsx 拆出並轉成 TypeScript。
//
// 拆出時補上載入失敗的處理：原本 load() 沒有 try/catch，請求失敗時 promise
// 未處理、data 停在 null，整頁空白且沒有重試出口。

// filter 進網址，概覽頁才能用 /admin/reviews?filter=reported 帶著篩選跳過來
const REVIEW_FILTERS = ["all", "pending", "reported", "hidden"] as const;
type ReviewFilter = (typeof REVIEW_FILTERS)[number];

const REVIEWS_QUERY_DEFAULTS = { page: 1, filter: "all" };

export function AdminReviewsPage() {
  const { params, setParam } = useListQuery(REVIEWS_QUERY_DEFAULTS);
  const { page } = params;
  // 網址上的 filter 可能是任何字串；不認得的值視為「全部」，下拉選單也才對得上
  const filter: ReviewFilter = toAllowed(params.filter, REVIEW_FILTERS) ?? "all";
  const [data, setData] = useState<AdminReviewListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftReplies, setDraftReplies] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();

  const load = useCallback(async () => {
    setError(null);
    try {
      const result = await fetchAdminReviews({
        page,
        pending: filter === "pending" ? "1" : undefined,
        reported: filter === "reported" ? "1" : undefined,
        status: filter === "hidden" ? "hidden" : undefined,
      });
      setData(result);
      setDraftReplies(Object.fromEntries(
        result.reviews.map((review) => [review.id, review.response?.body || ""]),
      ));
    } catch (err) {
      setError(errorDetail(err, "無法載入評論"));
    }
  }, [page, filter]);
  useEffect(() => { load(); }, [load]);

  async function handleReply(review: AdminReview) {
    const reply = (draftReplies[review.id] || "").trim();
    if (!reply) {
      notifyDialog("請先輸入官方回覆；如要移除既有回覆，請使用「移除回覆」。");
      return;
    }
    setBusyId(review.id);
    try {
      await adminReplyReview(review.id, reply);
      await load();
    } catch (err) {
      notifyDialog(errorDetail(err, "回覆儲存失敗"));
    } finally {
      setBusyId(null);
    }
  }

  async function removeReply(review: AdminReview) {
    if (!(await confirmDialog("確定移除這則官方回覆嗎？", { danger: true }))) return;
    setBusyId(review.id);
    try {
      await adminDeleteReviewReply(review.id);
      await load();
    } catch (err) {
      notifyDialog(errorDetail(err, "移除回覆失敗"));
    } finally {
      setBusyId(null);
    }
  }

  async function toggleVisibility(review: AdminReview) {
    const hiding = review.status === "published";
    const message = hiding
      ? "確定隱藏這則評論嗎？前台會立即停止顯示，相關待處理檢舉將標記為已處理。"
      : "確定重新公開這則評論嗎？相關待處理檢舉將標記為不成立。";
    if (!(await confirmDialog(message, { danger: hiding }))) return;
    setBusyId(review.id);
    try {
      await adminModerateReview(review.id, hiding ? "hidden" : "published");
      await load();
    } catch (err) {
      notifyDialog(errorDetail(err, "審核狀態更新失敗"));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="admin-page">
      <header className="admin-page-head">
        <h1>評論治理</h1>
        <p>官方回覆、內容檢舉與公開狀態；使用者評分和原文保持唯讀。</p>
      </header>

      {data && (
        <div className="admin-stat-grid">
          <AdminStatCard label="總評論數" value={data.overall_total} tone="cyan" />
          <AdminStatCard label="平均評分" value={data.avg_rating ? <>{data.avg_rating} <AdminStarIcon className="admin-star-icon" /></> : "—"} tone="good" />
          <AdminStatCard label="待回覆" value={data.pending_count} tone={data.pending_count > 0 ? "warn" : "good"} />
          <AdminStatCard label="待審檢舉" value={data.reported_count} tone={data.reported_count > 0 ? "warn" : "good"} />
        </div>
      )}

      <div className="admin-filter-bar">
        <label>
          <span className="sr-only">篩選評論</span>
          <select
            className="admin-input"
            value={filter}
            onChange={(event) => setParam("filter", event.target.value)}
          >
            <option value="all">全部評論</option>
            <option value="pending">只看待回覆</option>
            <option value="reported">只看待審檢舉</option>
            <option value="hidden">只看已隱藏</option>
          </select>
        </label>
        {data && <span className="admin-cell-secondary">目前顯示 {data.total} 則 · 已隱藏 {data.hidden_count} 則</span>}
      </div>

      {error && <AdminErrorState message="無法載入評論" detail={error} onRetry={load} />}
      {!error && !data && <AdminSkeleton variant="card" rows={3} label="載入評論中" />}

      {!error && data && data.reviews.map((review) => (
        <article
          key={review.id}
          className={[
            "admin-review",
            review.is_pending ? "is-pending" : "",
            review.status === "hidden" ? "is-hidden" : "",
            review.pending_report_count > 0 || review.response_pending_report_count > 0
              ? "is-reported"
              : "",
          ].filter(Boolean).join(" ")}
        >
          <header className="admin-review-head">
            <div>
              <div className="admin-review-user">
                {review.full_name}
                <span className="admin-cell-secondary"> @{review.username}</span>
              </div>
              <div className="admin-review-time">
                {formatDateTime(review.created_at)}
                {review.updated_at !== review.created_at && " · 使用者已編輯"}
              </div>
            </div>
            <div className="admin-review-rating" aria-label={`${review.rating} 顆星`}>
              {Array.from({ length: 5 }, (_, i) => (
                <AdminStarIcon key={i} filled={i < review.rating} className="admin-star-icon" />
              ))}
              <span className="admin-cell-secondary"> ({review.rating})</span>
            </div>
          </header>

          <div className="admin-review-status-row">
            <span className={review.status === "published" ? "status-active" : "status-inactive"}>
              {review.status === "published" ? "前台公開" : "已隱藏"}
            </span>
            {review.is_pending && <span className="admin-status">待回覆</span>}
            {review.pending_report_count > 0 && (
              <span className="admin-status failed">待審檢舉 {review.pending_report_count}</span>
            )}
            {review.response_pending_report_count > 0 && (
              <span className="admin-status failed">
                官方回覆待審 {review.response_pending_report_count}
              </span>
            )}
            {review.report_count > review.pending_report_count && (
              <span className="admin-cell-secondary">歷史檢舉 {review.report_count}</span>
            )}
            {review.response_report_count > review.response_pending_report_count && (
              <span className="admin-cell-secondary">
                官方回覆歷史檢舉 {review.response_report_count}
              </span>
            )}
          </div>

          {review.title && <h2 className="admin-review-title">{review.title}</h2>}
          <p className="admin-review-body">{review.comment || "（舊版評論未填文字）"}</p>
          <p className="admin-review-public-name">
            前台顯示：{review.show_partial_email ? "遮罩後的部分 Email" : "完全匿名"}
          </p>

          <div className="admin-review-reply-section">
            <label className="admin-review-reply-field">
              <span>ARGUS 團隊官方回覆</span>
              <textarea
                className="admin-input admin-reply-input"
                placeholder="清楚回應使用者的具體意見…"
                rows={3}
                maxLength={2000}
                value={draftReplies[review.id] ?? ""}
                onChange={(event) => setDraftReplies({
                  ...draftReplies,
                  [review.id]: event.target.value,
                })}
              />
            </label>
            <div className="admin-review-actions">
              <button
                type="button"
                className="admin-btn primary"
                disabled={busyId === review.id}
                onClick={() => handleReply(review)}
              >
                {review.response ? "更新官方回覆" : "送出官方回覆"}
              </button>
              {review.response && (
                <button
                  type="button"
                  className="admin-btn danger"
                  disabled={busyId === review.id}
                  onClick={() => removeReply(review)}
                >
                  移除回覆
                </button>
              )}
              <button
                type="button"
                className={`admin-btn ${review.status === "published" ? "danger" : ""}`}
                disabled={busyId === review.id}
                onClick={() => toggleVisibility(review)}
              >
                {review.status === "published" ? "隱藏評論" : "重新公開"}
              </button>
            </div>
          </div>

          {review.response && (
            <div className="admin-review-existing-reply">
              <StatusDoneGlyph className="admin-inline-glyph" /> 官方回覆最後更新於 {formatDateTime(review.response.updated_at)}
              {review.response.author_username ? ` · ${review.response.author_username}` : ""}
            </div>
          )}
        </article>
      ))}
      {!error && data && data.reviews.length === 0 && (
        <div className="admin-empty admin-panel">沒有符合條件的評論</div>
      )}
      {!error && data && <AdminPagination page={data.page} totalPages={data.total_pages} total={data.total} onChange={(n) => setParam("page", n)} />}
      {dialogHost}
    </div>
  );
}
