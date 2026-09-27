import { useState } from "react";

import { EyeOffIcon, EyeOpenIcon } from "./ActionIcons";

/**
 * 密碼輸入框 + 顯示／隱藏切換（登入頁與帳號設定共用）。
 * 其餘 props 原樣傳給 <input>；切換鈕不進 Tab 以外的流程，可及名稱會隨狀態改變。
 */
export default function PasswordInput({ className = "", invalid = false, ...inputProps }) {
  const [visible, setVisible] = useState(false);
  return (
    <span className={`pw-input ${invalid ? "is-error" : ""}`}>
      <input
        {...inputProps}
        className={`input pw-input-field ${className}`}
        type={visible ? "text" : "password"}
        aria-invalid={invalid || undefined}
      />
      <button
        type="button"
        className="pw-input-toggle"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "隱藏密碼" : "顯示密碼"}
        aria-pressed={visible}
      >
        {visible ? <EyeOffIcon /> : <EyeOpenIcon />}
      </button>
    </span>
  );
}
