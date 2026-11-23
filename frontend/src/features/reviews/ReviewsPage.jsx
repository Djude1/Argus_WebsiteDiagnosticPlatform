import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  Check,
  ChevronDown,
  CircleAlert,
  Flag,
  MessageSquareText,
  Pencil,
  Send,
  ShieldAlert,
  ShieldCheck,
  Star,
  ThumbsUp,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../../api";
import brandLogo from "../../assets/brand-logo.webp";
import { useConfirmDialogs, useDialogFocus } from "../../shared/AppShared.jsx";
import { useArgusStore } from "../../store";

const RATING_LABELS = {
  1: "很不滿意",
  2: "不滿意",
  3: "普通",
  4: "滿意",
  5: "很滿意",
};

const REPORT_REASONS = [
  { value: "spam", label: "垃圾內容或廣告", hint: "重複張貼、導流或與使用體驗無關" },
  { value: "privacy", label: "揭露個人資料", hint: "包含電話、Email、真實姓名或其他隱私" },
  { value: "abuse", label: "騷擾或不當內容", hint: "仇恨、威脅、人身攻擊或令人不適的內容" },
  { value: "other", label: "其他問題", hint: "不屬於以上類型，請在下方補充說明" },
];

function apiMessage(error, fallback) {
  const data = error?.response?.data;
  if (typeof data?.detail === "string") return data.detail;
  const first = data && Object.values(data).flat().find((value) => typeof value === "string");
  return first || fallback;
}

function BrandEye({ size = "default" }) {
  return (
    <span className={`review-next-brand-eye size-${size}`} aria-hidden="true">
      <img src={brandLogo} alt="" />
    </span>
  );
}

function ReadonlyStars({ value, compact = false }) {
  const rounded = Math.round(Number(value) || 0);
  return (
    <span
      className={`review-next-stars ${compact ? "is-compact" : ""}`}
      role="img"
      aria-label={`${value || 0} 顆星`}
    >
      {[1, 2, 3, 4, 5].map((star) => (
        <Star key={star} aria-hidden="true" className={star <= rounded ? "is-filled" : ""} />
      ))}
    </span>
  );
}

function RatingInput({
  value,
  onChange,
  idPrefix,
  showPartialEmail,
  onShowPartialEmailChange,
}) {
  return (
    <fieldset className="review-next-rating-input">
      <legend>整體評分</legend>
      <div className="review-next-rating-row">
        <div className="review-next-rating-options">
          {[1, 2, 3, 4, 5].map((star) => (
            <span key={star}>
              <input
                id={`${idPrefix}-${star}`}
                name={`${idPrefix}-rating`}
                type="radio"
                value={star}
                checked={value === star}
                onChange={() => onChange(star)}
                required
              />
              <label
                className="review-next-rating-star"
                htmlFor={`${idPrefix}-${star}`}
                title={`${star} 星：${RATING_LABELS[star]}`}
              >
                <Star aria-hidden="true" className={star <= value ? "is-filled" : ""} />
                <span className="sr-only">{star} 星：{RATING_LABELS[star]}</span>
              </label>
            </span>
          ))}
          <output aria-live="polite">
            {value ? `${value} 星 · ${RATING_LABELS[value]}` : "尚未評分"}
          </output>
        </div>

        <label className="review-next-author-privacy">
          <input
            type="checkbox"
            checked={showPartialEmail}
            onChange={(event) => onShowPartialEmailChange(event.target.checked)}
          />
          <span className="review-next-checkbox-mark" aria-hidden="true"><Check /></span>
          <span>顯示部分 Email</span>
        </label>
      </div>
    </fieldset>
  );
}

function ReviewComposer({ review, busy, onCancel, onSave }) {
  const [rating, setRating] = useState(review?.rating || 0);
  const [comment, setComment] = useState(review?.comment || "");
  const [showPartialEmail, setShowPartialEmail] = useState(
    Boolean(review?.show_partial_email),
  );
  const [error, setError] = useState("");

  function submit(event) {
    event.preventDefault();
    setError("");
    if (!rating) {
      setError("請先選擇 1 到 5 星");
      return;
    }
    if (comment.trim().length < 20) {
      setError("請至少用 20 個字元描述你的使用經驗");
      return;
    }
    onSave({
      rating,
      comment: comment.trim(),
      show_partial_email: showPartialEmail,
    });
  }

  return (
    <section className="review-next-composer-shell" aria-labelledby="review-next-composer-title">
      <div className="review-next-section-heading">
        <div className="review-next-heading-icon"><MessageSquareText aria-hidden="true" /></div>
        <div>
          <h2 id="review-next-composer-title">{review ? "編輯你的評論" : "寫下你的評論"}</h2>
        </div>
        <button type="button" className="review-next-icon-button" onClick={onCancel} aria-label="關閉評論表單">
          <X aria-hidden="true" />
        </button>
      </div>

      <form className="review-next-composer" onSubmit={submit}>
        <RatingInput
          value={rating}
          onChange={setRating}
          idPrefix={review ? "next-edit" : "next-new"}
          showPartialEmail={showPartialEmail}
          onShowPartialEmailChange={setShowPartialEmail}
        />

        <label className="review-next-field" htmlFor="review-next-comment">
          <span>你的使用經驗 <small>至少 20 個字元</small></span>
          <textarea
            id="review-next-comment"
            maxLength={3000}
            rows={7}
            placeholder="說說哪些地方最好用，或還能改善"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            required
          />
          <small>{comment.length} / 3000</small>
        </label>

        <div className="review-next-privacy-note">
          <ShieldCheck aria-hidden="true" />
          <div>
            <strong>公開前請再看一次</strong>
            <span>請不要填入 Email、電話、真實全名或其他個人資料</span>
          </div>
        </div>

        {error && <p className="review-next-form-error" role="alert"><CircleAlert aria-hidden="true" />{error}</p>}
        <div className="review-next-form-actions">
          <button type="button" className="review-next-button is-secondary" onClick={onCancel}>取消</button>
          <button type="submit" className="review-next-button is-primary" disabled={busy}>
            <Send aria-hidden="true" />
            {busy ? "儲存中…" : review ? "儲存更新" : "發表評論"}
          </button>
        </div>
      </form>
    </section>
  );
}

function ContentActions({ count, active, loggedIn, label, onHelpful, onReport }) {
  return (
    <div className="review-next-entry-actions" aria-label={`${label}互動`}>
      <button
        type="button"
        className={`review-next-entry-action is-helpful ${active ? "is-active" : ""}`}
        aria-label={`有幫助，${label}目前 ${count || 0} 個讚`}
        aria-pressed={active}
        title={!loggedIn ? "登入後可按讚" : `按讚${label}`}
        onClick={onHelpful}
      >
        <ThumbsUp aria-hidden="true" />有幫助 <strong>{count || 0}</strong>
      </button>
      <button
        type="button"
        className="review-next-entry-action is-report"
        aria-label={`檢舉${label}`}
        title={`檢舉${label}`}
        onClick={onReport}
      >
        <Flag aria-hidden="true" />檢舉
      </button>
    </div>
  );
}

function ExpandableReviewText({ text, label }) {
  const contentId = useId();
  const textRef = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const [canExpand, setCanExpand] = useState(false);

  useEffect(() => {
    const node = textRef.current;
    if (!node) return undefined;

    const measure = () => {
      if (expanded) return;
      setCanExpand(node.scrollHeight > node.clientHeight + 1);
    };

    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [expanded, text]);

  return (
    <div className="review-next-copy">
      <p ref={textRef} id={contentId} className={expanded ? "" : "is-collapsed"}>{text}</p>
      {canExpand && (
        <button
          type="button"
          className={`review-next-copy-toggle ${expanded ? "is-expanded" : ""}`}
          aria-controls={contentId}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "收合" : "顯示更多"}<ChevronDown aria-hidden="true" />
          <span className="sr-only">{label}</span>
        </button>
      )}
    </div>
  );
}

function ReviewCard({ review, loggedIn, onHelpful, onReport, showActions = true }) {
  const response = review.response;
  const date = new Date(review.created_at).toLocaleDateString("zh-Hant", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  return (
    <article className={`reviews-entry ${review.is_mine ? "is-mine" : ""}`}>
      <header className="reviews-entry-meta">
        <div>
          <div className="reviews-entry-author">
            <strong>{review.user_display}</strong>
            {review.verified_experience && <span><BadgeCheck aria-hidden="true" />已完成健檢</span>}
          </div>
          <time dateTime={review.created_at}>{date}{review.updated_at !== review.created_at ? " · 已編輯" : ""}</time>
        </div>
        <ReadonlyStars value={review.rating} compact />
      </header>

      <div className="reviews-entry-body">
        {review.title && <h3>{review.title}</h3>}
        <ExpandableReviewText text={review.comment} label="使用者評論" />
        {showActions && (
          <ContentActions
            count={review.helpful_count}
            active={review.my_helpful}
            loggedIn={loggedIn}
            label="使用者評論"
            onHelpful={() => onHelpful(review, "review")}
            onReport={() => onReport(review, "review")}
          />
        )}
      </div>

      {response && (
        <aside className="review-next-response" aria-label="Argus 官方回覆">
          <div className="review-next-response-line" aria-hidden="true" />
          <BrandEye size="small" />
          <div className="review-next-response-content">
            <header>
              <span><strong>Argus 官方回覆</strong></span>
              <time dateTime={response.updated_at}>
                {new Date(response.updated_at).toLocaleDateString("zh-Hant")}
              </time>
            </header>
            <ExpandableReviewText text={response.body} label="官方回覆" />
            <ContentActions
              count={response.helpful_count}
              active={response.my_helpful}
              loggedIn={loggedIn}
              label="官方回覆"
              onHelpful={() => onHelpful(review, "response")}
              onReport={() => onReport(review, "response")}
            />
          </div>
        </aside>
      )}
    </article>
  );
}

function ReviewsPage() {
  const navigate = useNavigate();
  const distributionToggle = useRef(null);
  const [distributionOpen, setDistributionOpen] = useState(false);
  const accessToken = useArgusStore((state) => state.accessToken);
  const theme = useArgusStore((state) => state.theme);
  // 預先渲染（Node 無 localStorage，主題一律 dark）的 HTML 必須與 hydrate 後的首次 render 一致，
  // 否則 React 會整塊重畫（畫面跑板、並被記成 JS 執行期錯誤）。掛載前用與伺服器相同的預設主題，
  // 掛載後才切到使用者實際主題。
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const activeTheme = mounted ? theme : "dark";
  const [summary, setSummary] = useState({ total: 0, average: null, distribution: {} });
  const [listData, setListData] = useState({ reviews: [], total: 0, total_pages: 1, page: 1 });
  const [mineInfo, setMineInfo] = useState(null);
  const [sort, setSort] = useState("helpful");
  const [ratingFilter, setRatingFilter] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [composerOpen, setComposerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [feedback, setFeedback] = useState(null);
  const [reportDraft, setReportDraft] = useState(null);
  const [reporting, setReporting] = useState(false);
  const { confirmDialog, notifyDialog, dialogHost } = useConfirmDialogs();
  const reportDialogRef = useDialogFocus(Boolean(reportDraft), () => setReportDraft(null));

  useEffect(() => {
    let active = true;
    api.get("/reviews/summary/")
      .then((response) => { if (active) setSummary(response.data); })
      .catch(() => { if (active) setFeedback({ tone: "bad", message: "暫時無法載入評論統計" }); });
    if (accessToken) {
      api.get("/reviews/mine/")
        .then((response) => { if (active) setMineInfo(response.data); })
        .catch(() => { if (active) setMineInfo(null); });
    } else {
      setMineInfo(null);
      setComposerOpen(false);
    }
    return () => { active = false; };
  }, [accessToken, refreshKey]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.get("/reviews/", { params: { sort, rating: ratingFilter || undefined, page } })
      .then((response) => { if (active) setListData(response.data); })
      .catch(() => { if (active) setFeedback({ tone: "bad", message: "暫時無法載入評論，請稍後重試" }); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sort, ratingFilter, page, accessToken, refreshKey]);

  const distribution = useMemo(() => [5, 4, 3, 2, 1].map((star) => ({
    star,
    count: summary.distribution?.[String(star)] || 0,
    percent: summary.total
      ? Math.round(((summary.distribution?.[String(star)] || 0) / summary.total) * 100)
      : 0,
  })), [summary]);

  const mine = mineInfo?.review || null;
  const eligibility = mineInfo?.eligibility || null;
  const visibleReviews = useMemo(
    () => listData.reviews.filter((review) => !review.is_mine),
    [listData.reviews],
  );
  const canSort = visibleReviews.length > 0 || listData.total_pages > 1;

  function openComposer() {
    if (mine || eligibility?.eligible) {
      setComposerOpen(true);
      return;
    }
    notifyDialog("評論前先完成一次掃描");
  }

  async function saveReview(payload) {
    setSaving(true);
    setFeedback(null);
    try {
      if (mine) await api.patch("/reviews/mine/", payload);
      else await api.post("/reviews/mine/", payload);
      setComposerOpen(false);
      setFeedback({ tone: "good", message: mine ? "你的評論已更新" : "評論已發表，謝謝你的分享" });
      setRefreshKey((value) => value + 1);
    } catch (error) {
      setFeedback({ tone: "bad", message: apiMessage(error, "評論儲存失敗，請稍後再試") });
    } finally {
      setSaving(false);
    }
  }

  async function deleteMine() {
    if (!(await confirmDialog("確定要刪除你的評論嗎？此操作無法復原", { danger: true }))) return;
    try {
      await api.delete("/reviews/mine/");
      setComposerOpen(false);
      setFeedback({ tone: "good", message: "你的評論已刪除" });
      setRefreshKey((value) => value + 1);
    } catch (error) {
      notifyDialog(apiMessage(error, "刪除失敗，請稍後再試"));
    }
  }

  async function toggleHelpful(review, target) {
    if (!accessToken) {
      navigate("/login?next=%2Freviews");
      return;
    }
    if (target === "review" && review.is_mine) return;
    try {
      const endpoint = target === "response"
        ? `/reviews/responses/${review.response.id}/helpful/`
        : `/reviews/${review.id}/helpful/`;
      const response = await api.post(endpoint);
      const updateReview = (item) => {
        if (item.id !== review.id) return item;
        if (target === "response") {
          return {
            ...item,
            response: {
              ...item.response,
              helpful_count: response.data.helpful_count,
              my_helpful: response.data.my_helpful,
            },
          };
        }
        return {
          ...item,
          helpful_count: response.data.helpful_count,
          my_helpful: response.data.my_helpful,
        };
      };
      setListData((current) => ({
        ...current,
        reviews: current.reviews.map(updateReview),
      }));
      setMineInfo((current) => current?.review?.id === review.id
        ? { ...current, review: updateReview(current.review) }
        : current);
    } catch (error) {
      notifyDialog(apiMessage(error, "操作失敗，請稍後再試"));
    }
  }

  function openReport(review, target) {
    if (!accessToken) {
      navigate("/login?next=%2Freviews");
      return;
    }
    setReportDraft({
      target,
      reviewId: review.id,
      responseId: target === "response" ? review.response.id : null,
      reason: "spam",
      detail: "",
    });
  }

  async function submitReport(event) {
    event.preventDefault();
    setReporting(true);
    try {
      const endpoint = reportDraft.target === "response"
        ? `/reviews/responses/${reportDraft.responseId}/report/`
        : `/reviews/${reportDraft.reviewId}/report/`;
      const response = await api.post(
        endpoint,
        { reason: reportDraft.reason, detail: reportDraft.detail.trim() },
      );
      setReportDraft(null);
      notifyDialog(response.data.detail);
    } catch (error) {
      notifyDialog(apiMessage(error, "檢舉送出失敗，請稍後再試"));
    } finally {
      setReporting(false);
    }
  }

  function selectRating(star) {
    setRatingFilter((current) => current === star ? null : star);
    setPage(1);
    if (distributionToggle.current?.getClientRects().length) {
      setDistributionOpen(false);
      distributionToggle.current.focus({ preventScroll: true });
    }
  }

  return (
    <div className="review-next-page reviews-reader" data-review-theme={activeTheme}>
      <div className="reviews-inner">
        <header className="reviews-heading">
          <h1 id="review-next-title">使用者評論</h1>
          {!composerOpen && !mine && (
            !accessToken ? (
              <Link className="reviews-write" to="/login?next=%2Freviews"><Pencil aria-hidden="true" />寫下評論</Link>
            ) : eligibility && !eligibility.eligible ? (
              <Link className="reviews-write" to="/scans">完成健檢後評論</Link>
            ) : (
              <button type="button" className="reviews-write" onClick={openComposer}><Pencil aria-hidden="true" />寫下評論</button>
            )
          )}
        </header>

        {feedback && (
          <div className={`review-next-feedback tone-${feedback.tone}`} role="status" aria-live="polite">
            {feedback.tone === "good" ? <Check aria-hidden="true" /> : <CircleAlert aria-hidden="true" />}
            {feedback.message}
          </div>
        )}

        {composerOpen && (
          <ReviewComposer
            key={mine?.updated_at || "new"}
            review={mine}
            busy={saving}
            onCancel={() => setComposerOpen(false)}
            onSave={saveReview}
          />
        )}

        <div className="reviews-columns">
          <section className="reviews-overview" aria-labelledby="reviews-score-heading">
            <div className="reviews-score">
              <h2 id="reviews-score-heading">整體評分</h2>
              <div className="reviews-average"><strong>{summary.average == null ? "—" : Number(summary.average).toFixed(1)}</strong><span>/ 5</span></div>
              <div className="reviews-sample">
                {summary.total > 0 && <ReadonlyStars value={summary.average} />}
                <span>共 {summary.total.toLocaleString()} 則評分</span>
              </div>
            </div>
            <button ref={distributionToggle} type="button" className="reviews-bars-toggle" aria-expanded={distributionOpen} aria-controls="reviews-distribution" onClick={() => setDistributionOpen(!distributionOpen)}>
              星等分布<ChevronDown aria-hidden="true" />
            </button>
            <div id="reviews-distribution" className="reviews-distribution" data-open={distributionOpen}>
              <div className="reviews-bars-heading" aria-hidden="true"><span>依星等篩選</span><span>則數</span></div>
              <div role="group" aria-label="依星等篩選評論">
                {distribution.map((item) => (
                  <button key={item.star} type="button" className="reviews-rating-row" aria-label={`${item.star} 星，${item.count} 則評論`} aria-pressed={ratingFilter === item.star} onClick={() => selectRating(item.star)}>
                    <span>{item.star} 星</span>
                    <span className="reviews-track" aria-hidden="true"><span style={{ width: `${item.percent}%` }} /></span>
                    <span>{item.count.toLocaleString()}</span>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <div className="reviews-feed">
            {mine && !composerOpen && (
              <section className="review-next-my-review" aria-labelledby="review-next-my-title">
                <header>
                  <div>
                    <UserRound aria-hidden="true" />
                    <h2 id="review-next-my-title">我的評論</h2>
                  </div>
                  <div>
                    <button type="button" className="review-next-button is-secondary" onClick={() => setComposerOpen(true)}>
                      <Pencil aria-hidden="true" />編輯
                    </button>
                    <button type="button" className="review-next-button is-danger" onClick={deleteMine}>
                      <Trash2 aria-hidden="true" />刪除
                    </button>
                  </div>
                </header>
                <ReviewCard
                  review={mine}
                  loggedIn
                  onHelpful={toggleHelpful}
                  onReport={openReport}
                  showActions={false}
                />
              </section>
            )}

            <section id="review-next-list" aria-labelledby="review-next-list-title">
              <h2 id="review-next-list-title" className="sr-only">評論列表</h2>
              {(ratingFilter || canSort) && (
                <div className="reviews-tools">
                  {ratingFilter && (
                    <button type="button" className="reviews-clear" onClick={() => selectRating(ratingFilter)}>
                      清除 {ratingFilter} 星篩選<X aria-hidden="true" />
                    </button>
                  )}
                  {canSort && (
                    <div className="reviews-sort" role="group" aria-label="排序方式">
                      {[["helpful", "熱門"], ["newest", "最新"]].map(([value, label]) => (
                        <button key={value} type="button" aria-pressed={sort === value} onClick={() => { setSort(value); setPage(1); }}>{label}</button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <p className="sr-only" role="status">
                {loading ? "正在載入評論" : `本頁 ${visibleReviews.length} 則評論，依${sort === "helpful" ? "熱門程度" : "最新時間"}排序`}
              </p>
              <div className="reviews-list" aria-busy={loading}>
                {loading && [1, 2, 3].map((item) => <div className="review-next-skeleton" key={item} />)}
                {!loading && visibleReviews.map((review) => (
                  <ReviewCard
                    key={review.id}
                    review={review}
                    loggedIn={Boolean(accessToken)}
                    onHelpful={toggleHelpful}
                    onReport={openReport}
                  />
                ))}
                {!loading && visibleReviews.length === 0 && (
                  <p className="reviews-empty">
                    {mine ? "沒有其他符合條件的評論" : ratingFilter ? "這個星等還沒有評論" : "目前還沒有公開評論"}
                  </p>
                )}
              </div>

              {listData.total_pages > 1 && (
                <nav className="review-next-pagination" aria-label="評論分頁">
                  <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
                    <ArrowLeft aria-hidden="true" />上一頁
                  </button>
                  <span>第 <strong>{listData.page}</strong> 頁，共 {listData.total_pages} 頁</span>
                  <button type="button" disabled={page >= listData.total_pages} onClick={() => setPage((value) => value + 1)}>
                    下一頁<ArrowRight aria-hidden="true" />
                  </button>
                </nav>
              )}
            </section>
          </div>
        </div>
      </div>

      {reportDraft && (
        <div className="review-next-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setReportDraft(null); }}>
          <form
            ref={reportDialogRef}
            className="review-next-report-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-next-report-title"
            tabIndex={-1}
            onSubmit={submitReport}
          >
            <header>
              <div className="review-next-report-icon"><ShieldAlert aria-hidden="true" /></div>
              <div>
                <h2 id="review-next-report-title">
                  {reportDraft.target === "response" ? "檢舉官方回覆" : "檢舉使用者評論"}
                </h2>
              </div>
              <button type="button" className="review-next-icon-button" onClick={() => setReportDraft(null)} aria-label="關閉檢舉視窗">
                <X aria-hidden="true" />
              </button>
            </header>

            <fieldset className="review-next-report-reasons">
              <legend>發生了什麼問題？</legend>
              {REPORT_REASONS.map((reason) => (
                <label key={reason.value}>
                  <input
                    type="radio"
                    name="review-next-report-reason"
                    value={reason.value}
                    checked={reportDraft.reason === reason.value}
                    onChange={(event) => setReportDraft({ ...reportDraft, reason: event.target.value })}
                  />
                  <span className="review-next-radio-mark" aria-hidden="true" />
                  <span><strong>{reason.label}</strong><small>{reason.hint}</small></span>
                </label>
              ))}
            </fieldset>

            <label className="review-next-field" htmlFor="review-next-report-detail">
              <span>補充說明 <small>選填</small></span>
              <textarea
                id="review-next-report-detail"
                rows={4}
                maxLength={500}
                placeholder="請勿填入個人資料"
                value={reportDraft.detail}
                onChange={(event) => setReportDraft({ ...reportDraft, detail: event.target.value })}
              />
              <small>{reportDraft.detail.length} / 500</small>
            </label>

            <div className="review-next-report-notice">
              <CircleAlert aria-hidden="true" />惡意或重複檢舉不會加速處理
            </div>
            <div className="review-next-form-actions">
              <button type="button" className="review-next-button is-secondary" onClick={() => setReportDraft(null)}>取消</button>
              <button type="submit" className="review-next-button is-report" disabled={reporting}>
                <Flag aria-hidden="true" />{reporting ? "送出中…" : "送出檢舉"}
              </button>
            </div>
          </form>
        </div>
      )}
      {dialogHost}
    </div>
  );
}

export { ReviewsPage };
