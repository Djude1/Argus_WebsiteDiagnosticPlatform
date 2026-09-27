import type { FormEvent, RefObject } from "react";
import { CircleAlert, Flag, ShieldAlert, X } from "lucide-react";

import { useDialogFocus } from "../../shared/AppShared";
import type { ReportDraft } from "./reviewTypes";

const REPORT_REASONS = [
  { value: "spam", label: "垃圾內容或廣告", hint: "重複張貼、導流或與使用體驗無關" },
  { value: "privacy", label: "揭露個人資料", hint: "包含電話、Email、真實姓名或其他隱私" },
  { value: "abuse", label: "騷擾或不當內容", hint: "仇恨、威脅、人身攻擊或令人不適的內容" },
  { value: "other", label: "其他問題", hint: "不屬於以上類型，請在下方補充說明" },
];

type ReviewReportDialogProps = {
  draft: ReportDraft;
  busy: boolean;
  onChange: (draft: ReportDraft) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

/** 檢舉視窗：Esc 與點背景可關閉、焦點鎖在視窗內（useDialogFocus） */
export function ReviewReportDialog({ draft, busy, onChange, onClose, onSubmit }: ReviewReportDialogProps) {
  const dialogRef = useDialogFocus(true, onClose);

  return (
    <div
      className="rv-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <form
        ref={dialogRef as RefObject<HTMLFormElement>}
        className="rv-panel rv-report"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rv-report-title"
        tabIndex={-1}
        onSubmit={onSubmit}
      >
        <header className="rv-panel-head">
          <span className="rv-panel-icon is-bad" aria-hidden="true"><ShieldAlert /></span>
          <div>
            <h2 id="rv-report-title">
              {draft.target === "response" ? "檢舉官方回覆" : "檢舉使用者評論"}
            </h2>
            <p>管理員會在審核後決定是否隱藏這則內容。</p>
          </div>
          <button type="button" className="rv-icon-button" onClick={onClose} aria-label="關閉檢舉視窗">
            <X aria-hidden="true" />
          </button>
        </header>

        <fieldset className="rv-reasons">
          <legend className="rv-field-label">發生了什麼問題？</legend>
          {REPORT_REASONS.map((reason) => (
            <label key={reason.value} className="rv-reason">
              <input
                type="radio"
                name="rv-report-reason"
                value={reason.value}
                checked={draft.reason === reason.value}
                onChange={(event) => onChange({ ...draft, reason: event.target.value })}
              />
              <span className="rv-radio-mark" aria-hidden="true" />
              <span className="rv-reason-text"><strong>{reason.label}</strong><small>{reason.hint}</small></span>
            </label>
          ))}
        </fieldset>

        <div className="rv-field">
          <label className="rv-field-label" htmlFor="rv-report-detail">補充說明 <small>選填</small></label>
          <textarea
            id="rv-report-detail"
            className="input rv-textarea"
            rows={3}
            maxLength={500}
            placeholder="請勿填入個人資料"
            value={draft.detail}
            onChange={(event) => onChange({ ...draft, detail: event.target.value })}
          />
          <div className="rv-field-foot"><span /><span className="ag-num">{draft.detail.length} / 500</span></div>
        </div>

        <p className="rv-note is-warn"><CircleAlert aria-hidden="true" />惡意或重複檢舉不會加速處理</p>
        <div className="rv-form-actions">
          <button type="button" className="secondary-button" onClick={onClose}>取消</button>
          <button type="submit" className="rv-danger-button" disabled={busy}>
            <Flag aria-hidden="true" />{busy ? "送出中…" : "送出檢舉"}
          </button>
        </div>
      </form>
    </div>
  );
}
