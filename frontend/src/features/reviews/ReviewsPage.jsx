import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleAlert,
  MessageSquareText,
  Pencil,
  RotateCw,
  ScanSearch,
  SlidersHorizontal,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../../api";
import { ArgusMark } from "../../components/brand/ArgusMark";
import { ReviewCard, ReadonlyStars } from "../../components/reviews/ReviewCard";
import { ReviewComposer } from "../../components/reviews/ReviewComposer";
import { ReviewReportDialog } from "../../components/reviews/ReviewReportDialog";
import { useConfirmDialogs } from "../../shared/AppShared";
import { formatNumber } from "../../shared/formatters";
import { useArgusStore } from "../../store";

const STAR_FILTERS = [5, 4, 3, 2, 1];

function apiMessage(error, fallback) {
  const data = error?.response?.data;
  if (typeof data?.detail === "string") return data.detail;
  const first = data && Object.values(data).flat().find((value) => typeof value === "string");
  return first || fallback;
}

/** 撰寫入口：依登入／資格顯示不同的說明與行動 */
function ComposeEntry({ loggedIn, eligibility, onOpen }) {
  let title = "分享你的使用經驗";
  let body = "你的評分能幫助其他團隊判斷 Argus 是否適合他們的網站。";
  let action = (
    <button type="button" className="primary-button" onClick={onOpen}>
      <Pencil aria-hidden="true" />寫下你的評論
    </button>
  );
  if (!loggedIn) {
    title = "用過 Argus 嗎？";
    body = "登入並完成一次網站掃描後，就能留下你的評分與心得。";
    action = (
      <Link className="primary-button" to="/login?next=%2Freviews">
        <Pencil aria-hidden="true" />寫下你的評論
      </Link>
    );
  } else if (eligibility && !eligibility.eligible) {
    title = "想分享你的使用經驗？";
    body = eligibility.reason || "評論只開放給實際用過掃描的帳號，確保每則評價都有真實依據。";
    action = (
      <Link className="secondary-button" to="/scans">
        <ScanSearch aria-hidden="true" />評論前先完成一次掃描
      </Link>
    );
  }

  return (
    <section className="rv-cta" aria-label="撰寫評論">
      <span className="rv-cta-icon" aria-hidden="true"><MessageSquareText /></span>
      <div className="rv-cta-copy">
        <strong>{title}</strong>
        <span>{body}</span>
      </div>
      {action}
    </section>
  );
}

/** 評分總覽：大數字＋星等＋可點擊篩選的分布長條 */
function ScoreCard({ summary, status, distribution, ratingFilter, onSelect, onRetry }) {
  const ready = status === "ready";
  return (
    <section className="rv-score ag-viewfinder" aria-label="評論總覽">
      <div className="rv-score-top">
        <div className="rv-score-value">
          <span className="ag-eyebrow">整體評分</span>
          <strong className="ag-num">{ready && summary.average != null ? Number(summary.average).toFixed(2) : "—"}</strong>
          <ReadonlyStars value={ready ? summary.average || 0 : 0} size="lg" />
          <span className="rv-score-total">
            {ready ? <>共 <b className="ag-num">{formatNumber(summary.total, "0")}</b> 則評論</> : status === "error" ? "統計暫時無法取得" : "載入統計中…"}
          </span>
        </div>
      </div>

      {status === "error" ? (
        <div className="rv-score-error" role="alert">
          <CircleAlert aria-hidden="true" />
          <span>暫時無法載入評論統計</span>
          <button type="button" className="rv-link-button" onClick={onRetry}>重試</button>
        </div>
      ) : (
        <div className={`rv-bars ${status === "loading" ? "is-loading" : ""}`}>
          {distribution.map((item) => {
            const active = ratingFilter === item.star;
            return (
              <button
                key={item.star}
                type="button"
                className={`rv-bar ${active ? "is-active" : ""}`}
                aria-pressed={active}
                aria-label={`${item.star} 星，共 ${item.count} 則評論${active ? "，目前已篩選" : ""}`}
                onClick={() => onSelect(item.star)}
                disabled={!ready}
              >
                <span className="rv-bar-star ag-num">{item.star}<Star aria-hidden="true" /></span>
                <span className="rv-bar-track" aria-hidden="true">
                  {/* 長條寬度是動態值，依規範可用 inline style */}
                  <span className="rv-bar-fill" style={{ "--rv-pct": `${item.percent}%` }} />
                </span>
                <span className="rv-bar-count ag-num">{item.count}</span>
                <span className="rv-bar-pct ag-num" aria-hidden="true">{item.percent}%</span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ReviewsPage() {
  const accessToken = useArgusStore((state) => state.accessToken);
  const [summary, setSummary] = useState({ total: 0, average: null, distribution: {} });
  const [summaryStatus, setSummaryStatus] = useState("loading");
  const [listData, setListData] = useState({ reviews: [], total: 0, total_pages: 1, page: 1 });
  const [listError, setListError] = useState(false);
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

  useEffect(() => {
    let active = true;
    setSummaryStatus("loading");
    api.get("/reviews/summary/")
      .then((response) => { if (active) { setSummary(response.data); setSummaryStatus("ready"); } })
      .catch(() => { if (active) setSummaryStatus("error"); });
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
    setListError(false);
    api.get("/reviews/", { params: { sort, rating: ratingFilter || undefined, page } })
      .then((response) => { if (active) setListData(response.data); })
      .catch(() => { if (active) setListError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sort, ratingFilter, page, accessToken, refreshKey]);

  const distribution = useMemo(() => STAR_FILTERS.map((star) => ({
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
  const mineMatchesFilter = Boolean(mine && (!ratingFilter || mine.rating === ratingFilter));
  const visibleTotal = Math.max(0, listData.total - (mineMatchesFilter ? 1 : 0));

  function retry() {
    setRefreshKey((value) => value + 1);
  }

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
      notifyDialog("請先登入後再按讚");
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
      notifyDialog("請先登入後再檢舉內容");
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
  }

  function clearRating() {
    setRatingFilter(null);
    setPage(1);
  }

  return (
    <div className="rv-page">
      <div className="rv-wrap">
        <section className="rv-hero" aria-labelledby="rv-title">
          <div className="rv-hero-copy">
            <span className="ag-eyebrow">User Reviews</span>
            <h1 id="rv-title">使用者怎麼評價 <span>Argus</span></h1>
            <p className="rv-lead">
              每則評論都來自完成過網站掃描的帳號，顯示名稱經過遮罩；官方回覆會以 Argus 標誌標示。
            </p>
            {!composerOpen && !mine && (
              <ComposeEntry loggedIn={Boolean(accessToken)} eligibility={eligibility} onOpen={openComposer} />
            )}
          </div>
          <ScoreCard
            summary={summary}
            status={summaryStatus}
            distribution={distribution}
            ratingFilter={ratingFilter}
            onSelect={selectRating}
            onRetry={retry}
          />
        </section>

        {feedback && (
          <div className={`rv-feedback is-${feedback.tone}`} role="status" aria-live="polite">
            {feedback.tone === "good" ? <Check aria-hidden="true" /> : <CircleAlert aria-hidden="true" />}
            <span>{feedback.message}</span>
            <button type="button" className="rv-icon-button is-sm" onClick={() => setFeedback(null)} aria-label="關閉提示">
              <X aria-hidden="true" />
            </button>
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

        {mine && !composerOpen && (
          <section className="rv-mine" aria-labelledby="rv-mine-title">
            <header className="rv-section-head">
              <h2 id="rv-mine-title">我的評論</h2>
              <div className="rv-mine-actions">
                <button type="button" className="secondary-button" onClick={() => setComposerOpen(true)}>
                  <Pencil aria-hidden="true" />編輯
                </button>
                <button type="button" className="rv-danger-button is-ghost" onClick={deleteMine}>
                  <Trash2 aria-hidden="true" />刪除
                </button>
              </div>
            </header>
            <ReviewCard
              review={mine}
              loggedIn
              index={0}
              onHelpful={toggleHelpful}
              onReport={openReport}
              showActions={false}
            />
          </section>
        )}

        <section className="rv-list-section" id="rv-list" aria-labelledby="rv-list-title">
          <div className="rv-toolbar">
            <div className="rv-section-head">
              <h2 id="rv-list-title">使用者評論</h2>
              {!listError && (
                <p className="rv-count" aria-live="polite">
                  共 <strong className="ag-num">{loading ? "…" : visibleTotal}</strong> 則{ratingFilter ? ` ${ratingFilter} 星` : ""}評論
                </p>
              )}
            </div>
            <div className="rv-toolbar-controls">
              <div className="rv-segment" role="group" aria-label="依星等篩選">
                <button type="button" aria-pressed={!ratingFilter} onClick={clearRating}>全部</button>
                {STAR_FILTERS.map((star) => (
                  <button
                    key={star}
                    type="button"
                    aria-pressed={ratingFilter === star}
                    aria-label={`只看 ${star} 星`}
                    onClick={() => selectRating(star)}
                  >
                    <span className="ag-num">{star}</span><Star aria-hidden="true" />
                  </button>
                ))}
              </div>
              <label className="rv-sort">
                <SlidersHorizontal aria-hidden="true" />
                <span>排序</span>
                <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}>
                  <option value="helpful">熱門</option>
                  <option value="newest">最新</option>
                </select>
              </label>
            </div>
          </div>

          {ratingFilter && (
            <div className="rv-active-filter">
              <span>目前只顯示 {ratingFilter} 星評論</span>
              <button type="button" className="rv-chip is-filter" onClick={() => selectRating(ratingFilter)}>
                {ratingFilter} 星 · 清除篩選<X aria-hidden="true" />
              </button>
            </div>
          )}

          <div className="rv-list" aria-busy={loading}>
            {loading && [1, 2, 3].map((item) => (
              <div className="rv-card rv-skeleton" key={item} aria-hidden="true">
                <span className="rv-sk-row"><i className="rv-sk-avatar" /><i className="rv-sk-line is-short" /></span>
                <i className="rv-sk-line" />
                <i className="rv-sk-line is-mid" />
              </div>
            ))}

            {!loading && listError && (
              <div className="rv-state is-error" role="alert">
                <span className="rv-state-mark"><ArgusMark size={44} /></span>
                <h3>評論暫時無法載入</h3>
                <p>暫時無法載入評論，請稍後重試。若問題持續，可能是網路或伺服器正在維護。</p>
                <button type="button" className="primary-button" onClick={retry}>
                  <RotateCw aria-hidden="true" />重新載入
                </button>
              </div>
            )}

            {!loading && !listError && visibleReviews.map((review, index) => (
              <ReviewCard
                key={review.id}
                review={review}
                loggedIn={Boolean(accessToken)}
                index={index}
                onHelpful={toggleHelpful}
                onReport={openReport}
              />
            ))}

            {!loading && !listError && visibleReviews.length === 0 && (
              <div className="rv-state">
                <span className="rv-state-mark"><ArgusMark size={44} /></span>
                <h3>{ratingFilter ? `目前沒有 ${ratingFilter} 星評論` : "目前還沒有評論"}</h3>
                <p>{ratingFilter ? "清除篩選或選擇其他星等" : "目前還沒有公開評論，歡迎成為第一個分享使用經驗的人。"}</p>
                {ratingFilter && (
                  <button type="button" className="secondary-button" onClick={() => selectRating(ratingFilter)}>
                    清除星等篩選
                  </button>
                )}
              </div>
            )}
          </div>

          {!listError && listData.total_pages > 1 && (
            <nav className="rv-pagination" aria-label="評論分頁">
              <button type="button" className="secondary-button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
                <ArrowLeft aria-hidden="true" />上一頁
              </button>
              <span>第 <strong className="ag-num">{listData.page}</strong> 頁，共 <span className="ag-num">{listData.total_pages}</span> 頁</span>
              <button type="button" className="secondary-button" disabled={page >= listData.total_pages} onClick={() => setPage((value) => value + 1)}>
                下一頁<ArrowRight aria-hidden="true" />
              </button>
            </nav>
          )}
        </section>
      </div>

      {reportDraft && (
        <ReviewReportDialog
          draft={reportDraft}
          busy={reporting}
          onChange={setReportDraft}
          onClose={() => setReportDraft(null)}
          onSubmit={submitReport}
        />
      )}
      {dialogHost}
    </div>
  );
}

export { ReviewsPage };
