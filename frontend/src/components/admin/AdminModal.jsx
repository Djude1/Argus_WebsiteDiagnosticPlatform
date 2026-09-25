import { useDialogFocus } from "../../shared/AppShared.jsx";

// 後台統一的 modal。
//
// 存在理由：後台原本並存兩套 modal（CMS 用 .admin-modal、方案與公告用 .ann-modal），
// 外觀、按鈕位置與關閉行為都不同，新頁面不知道該跟哪一套。這裡收斂成一個，
// focus trap 與 Esc 沿用既有的 useDialogFocus，行為與其他對話框一致。
//
// 刻意不把開關狀態放進 history：遮罩與 Esc 關閉不應該污染瀏覽器上一頁
// （專案 UI 準則第 6 條）。

export function AdminModal({
  open,
  onClose,
  title,
  size = "md",
  children,
  footer,
  // form：包成 <form> 並在 submit 時呼叫 onSubmit，讓 Enter 能送出
  onSubmit,
  labelledBy,
}) {
  const dialogRef = useDialogFocus(Boolean(open), onClose);
  if (!open) return null;

  const isForm = typeof onSubmit === "function";
  const Tag = isForm ? "form" : "div";
  const tagProps = isForm ? { onSubmit } : {};

  return (
    <div className="admin-modal-backdrop" onClick={onClose}>
      <Tag
        {...tagProps}
        ref={dialogRef}
        className={`admin-modal is-${size}`}
        role="dialog"
        aria-modal="true"
        aria-label={labelledBy ? undefined : title}
        aria-labelledby={labelledBy}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="admin-modal-head">
          <h2 className="admin-modal-title">{title}</h2>
          <button
            type="button"
            className="admin-modal-close"
            onClick={onClose}
            aria-label="關閉"
          >
            ×
          </button>
        </div>
        <div className="admin-modal-body">{children}</div>
        {footer && <div className="admin-modal-foot">{footer}</div>}
      </Tag>
    </div>
  );
}

/**
 * modal 內的表單欄位。把 label、提示、錯誤三段綁在一起，
 * 錯誤訊息用 aria-describedby 連到輸入元件，讀螢幕軟體才唸得到。
 */
export function AdminField({ id, label, hint, error, required, children }) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={`admin-field ${error ? "has-error" : ""}`}>
      <label className="admin-field-label" htmlFor={id}>
        {label}
        {required && <span className="admin-field-required" aria-hidden="true"> *</span>}
        {required && <span className="sr-only">（必填）</span>}
      </label>
      {hint && <span className="admin-field-hint" id={hintId}>{hint}</span>}
      {typeof children === "function"
        ? children({ id, "aria-describedby": [hintId, errorId].filter(Boolean).join(" ") || undefined })
        : children}
      {error && <span className="admin-field-error" id={errorId}>{error}</span>}
    </div>
  );
}
