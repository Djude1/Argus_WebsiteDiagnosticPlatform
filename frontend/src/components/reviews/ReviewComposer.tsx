import { useState, type FormEvent } from "react";
import { Check, CircleAlert, MessageSquareText, Send, ShieldCheck, Star, X } from "lucide-react";

import { RATING_LABELS, type PublicReview, type ReviewPayload } from "./reviewTypes";

const MIN_LENGTH = 20;
const MAX_LENGTH = 3000;

type RatingInputProps = {
  value: number;
  onChange: (value: number) => void;
  idPrefix: string;
};

/**
 * 星等選擇器：底層是原生 radio group，方向鍵即可切換星等、Tab 進出整組；
 * 星星本身是 label，滑過時預覽會亮到指標所在的那顆。
 */
function RatingInput({ value, onChange, idPrefix }: RatingInputProps) {
  return (
    <fieldset className="rv-rate">
      <legend className="rv-field-label">整體評分</legend>
      <div className="rv-rate-row">
        <div className="rv-rate-options">
          {[1, 2, 3, 4, 5].map((star) => (
            <span key={star} className="rv-rate-option">
              <input
                id={`${idPrefix}-${star}`}
                name={`${idPrefix}-rating`}
                type="radio"
                value={star}
                checked={value === star}
                onChange={() => onChange(star)}
                required
              />
              <label htmlFor={`${idPrefix}-${star}`} title={`${star} 星：${RATING_LABELS[star]}`}>
                <Star aria-hidden="true" className={star <= value ? "is-filled" : ""} />
                <span className="sr-only">{star} 星：{RATING_LABELS[star]}</span>
              </label>
            </span>
          ))}
        </div>
        <output className={`rv-rate-output ${value ? "has-value" : ""}`} aria-live="polite">
          {value ? `${value} 星 · ${RATING_LABELS[value]}` : "尚未評分"}
        </output>
      </div>
    </fieldset>
  );
}

type ReviewComposerProps = {
  review: PublicReview | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (payload: ReviewPayload) => void;
};

export function ReviewComposer({ review, busy, onCancel, onSave }: ReviewComposerProps) {
  const [rating, setRating] = useState(review?.rating || 0);
  const [comment, setComment] = useState(review?.comment || "");
  const [showPartialEmail, setShowPartialEmail] = useState(Boolean(review?.show_partial_email));
  const [error, setError] = useState("");
  const trimmedLength = comment.trim().length;
  const remaining = Math.max(0, MIN_LENGTH - trimmedLength);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!rating) {
      setError("請先選擇 1 到 5 星");
      return;
    }
    if (trimmedLength < MIN_LENGTH) {
      setError("請至少用 20 個字元描述你的使用經驗");
      return;
    }
    onSave({ rating, comment: comment.trim(), show_partial_email: showPartialEmail });
  }

  return (
    <section className="rv-panel rv-composer" aria-labelledby="rv-composer-title">
      <header className="rv-panel-head">
        <span className="rv-panel-icon" aria-hidden="true"><MessageSquareText /></span>
        <div>
          <h2 id="rv-composer-title">{review ? "編輯你的評論" : "寫下你的評論"}</h2>
          <p>評分與內容會公開顯示；名稱可選擇匿名或只顯示部分 Email。</p>
        </div>
        <button type="button" className="rv-icon-button" onClick={onCancel} aria-label="關閉評論表單">
          <X aria-hidden="true" />
        </button>
      </header>

      <form className="rv-composer-form" onSubmit={submit} noValidate>
        <RatingInput value={rating} onChange={setRating} idPrefix={review ? "rv-edit" : "rv-new"} />

        <div className="rv-field">
          <label className="rv-field-label" htmlFor="rv-comment">
            你的使用經驗 <small>至少 20 個字元</small>
          </label>
          <textarea
            id="rv-comment"
            className="input rv-textarea"
            maxLength={MAX_LENGTH}
            rows={6}
            placeholder="說說哪些地方最好用，或還能改善"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            required
          />
          <div className="rv-field-foot">
            <span className={remaining ? "" : "is-ok"}>
              {remaining ? `還需要 ${remaining} 個字元` : <><Check aria-hidden="true" />字數足夠</>}
            </span>
            <span className="ag-num">{comment.length} / {MAX_LENGTH}</span>
          </div>
        </div>

        <label className="rv-switch">
          <input
            type="checkbox"
            checked={showPartialEmail}
            onChange={(event) => setShowPartialEmail(event.target.checked)}
          />
          <span className="rv-switch-track" aria-hidden="true" />
          <span className="rv-switch-text">
            <strong>顯示部分 Email</strong>
            <small>{showPartialEmail ? "以遮罩後的 Email 顯示，例如 ab***@gmail.com" : "以「匿名已驗證使用者」顯示"}</small>
          </span>
        </label>

        <div className="rv-note">
          <ShieldCheck aria-hidden="true" />
          <div>
            <strong>公開前請再看一次</strong>
            <span>請不要填入 Email、電話、真實全名或其他個人資料</span>
          </div>
        </div>

        {error && <p className="rv-form-error" role="alert"><CircleAlert aria-hidden="true" />{error}</p>}
        <div className="rv-form-actions">
          <button type="button" className="secondary-button" onClick={onCancel}>取消</button>
          <button type="submit" className="primary-button" disabled={busy}>
            <Send aria-hidden="true" />
            {busy ? "儲存中…" : review ? "儲存更新" : "發表評論"}
          </button>
        </div>
      </form>
    </section>
  );
}
