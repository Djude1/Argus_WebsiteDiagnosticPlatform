import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import { BadgeCheck, ChevronDown, Flag, Star, ThumbsUp } from "lucide-react";

import { ArgusMark } from "../brand/ArgusMark";
import { formatDate } from "../../shared/formatters";
import type { PublicReview, ReviewTarget } from "./reviewTypes";

type ReadonlyStarsProps = {
  value: number | string | null | undefined;
  size?: "sm" | "md" | "lg";
};

/** 唯讀星等：四捨五入到整顆星，可及名稱保留原始數值（例如 4.62 顆星） */
export function ReadonlyStars({ value, size = "md" }: ReadonlyStarsProps) {
  const rounded = Math.round(Number(value) || 0);
  return (
    <span className={`rv-stars is-${size}`} role="img" aria-label={`${value || 0} 顆星`}>
      {[1, 2, 3, 4, 5].map((star) => (
        <Star key={star} aria-hidden="true" className={star <= rounded ? "is-filled" : ""} />
      ))}
    </span>
  );
}

type ContentActionsProps = {
  count: number;
  active: boolean;
  loggedIn: boolean;
  label: string;
  onHelpful: () => void;
  onReport: () => void;
};

function ContentActions({ count, active, loggedIn, label, onHelpful, onReport }: ContentActionsProps) {
  return (
    <div className="rv-actions" role="group" aria-label={`${label}互動`}>
      <button
        type="button"
        className={`rv-action is-helpful ${active ? "is-active" : ""}`}
        aria-label={`按讚${label}，目前 ${count || 0} 個讚`}
        aria-pressed={active}
        title={!loggedIn ? "登入後可按讚" : `按讚${label}`}
        onClick={onHelpful}
      >
        <ThumbsUp aria-hidden="true" />
        <span className="rv-action-label">有幫助</span>
        <strong className="ag-num">{count || 0}</strong>
      </button>
      <button
        type="button"
        className="rv-action is-report"
        aria-label={`檢舉${label}`}
        title={`檢舉${label}`}
        onClick={onReport}
      >
        <Flag aria-hidden="true" />
        <span className="rv-action-label">檢舉</span>
      </button>
    </div>
  );
}

/** 長文預設收合到數行；只有真的被截斷時才出現「顯示更多」 */
function ExpandableReviewText({ text, label }: { text: string; label: string }) {
  const contentId = useId();
  const textRef = useRef<HTMLParagraphElement | null>(null);
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
    <div className="rv-copy">
      <p ref={textRef} id={contentId} className={expanded ? "" : "is-collapsed"}>{text}</p>
      {canExpand && (
        <button
          type="button"
          className={`rv-copy-toggle ${expanded ? "is-expanded" : ""}`}
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

type ReviewCardProps = {
  review: PublicReview;
  loggedIn: boolean;
  index: number;
  onHelpful: (review: PublicReview, target: ReviewTarget) => void;
  onReport: (review: PublicReview, target: ReviewTarget) => void;
  showActions?: boolean;
};

export function ReviewCard({ review, loggedIn, index, onHelpful, onReport, showActions = true }: ReviewCardProps) {
  const response = review.response;
  const initial = Array.from(review.user_display || "訪")[0];
  const edited = review.updated_at !== review.created_at;
  // 進場錯開延遲是動態值，依規範可用 inline style
  const style = { "--rv-i": Math.min(index, 8) } as CSSProperties;

  return (
    <article className={`rv-card ${review.is_mine ? "is-mine" : ""}`} style={style}>
      <header className="rv-card-head">
        <span className="rv-avatar" aria-hidden="true">{initial}</span>
        <div className="rv-author">
          <div className="rv-author-line">
            <strong className="rv-author-name">{review.user_display}</strong>
            {review.is_mine && <span className="rv-chip is-mine">我的評論</span>}
          </div>
          <div className="rv-author-meta">
            {review.verified_experience && (
              <span className="rv-verified"><BadgeCheck aria-hidden="true" />已驗證</span>
            )}
            <time dateTime={review.created_at}>
              {formatDate(review.created_at)}{edited ? " · 已編輯" : ""}
            </time>
          </div>
        </div>
        <ReadonlyStars value={review.rating} size="sm" />
      </header>

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

      {response && (
        <aside className="rv-reply" aria-label="Argus 官方回覆">
          <header className="rv-reply-head">
            <span className="rv-reply-mark"><ArgusMark size={20} /></span>
            <strong>Argus 團隊回覆</strong>
            <span className="rv-chip is-official">官方</span>
            <time dateTime={response.updated_at}>{formatDate(response.updated_at)}</time>
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
        </aside>
      )}
    </article>
  );
}
