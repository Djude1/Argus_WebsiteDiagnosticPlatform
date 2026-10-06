import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../../api";
import { copyToClipboard } from "../../shared/clipboard";
import { ACCESS_OPTIONS } from "./optimizeLabels";

/**
 * 分享優化結果（參考 Notion／Figma 的分享面板）：選擇誰可以檢視、複製連結。
 *
 * - 連結第一次分享時產生、之後固定不變；改回「僅限我」就是關閉分享，再打開仍是同一個網址。
 * - 檢視者一律唯讀：看得到前後比較與修改清單，看不到你的專案、點數或其他頁面。
 * - Esc 或點遮罩關閉，不寫進瀏覽器歷史。
 */
export default function ShareDialog({ rebuild, onChange, onClose }) {
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const dialogRef = useRef(null);
  const access = rebuild.share_active ? rebuild.share_access : "private";
  const url = rebuild.share_path ? `${window.location.origin}${rebuild.share_path}` : "";

  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    dialogRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function choose(value) {
    if (value === access || busy) return;
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const { data } =
        value === "private"
          ? await api.delete(`/rebuilds/${rebuild.id}/share/`)
          : await api.post(`/rebuilds/${rebuild.id}/share/`, { access: value });
      onChange(data);
    } catch (err) {
      setError(err?.response?.data?.detail || "無法更新分享設定，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    setCopied(await copyToClipboard(url));
  }

  return createPortal(
    <div className="member-legacy">
      <div className="opt-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
        <div
          className="opt-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="opt-share-title"
          tabIndex={-1}
          ref={dialogRef}
        >
          <div className="opt-dialog-head">
            <h2 id="opt-share-title" className="opt-dialog-title">分享優化結果</h2>
            <button type="button" className="opt-dialog-close" onClick={onClose} aria-label="關閉">×</button>
          </div>
          <p className="opt-dialog-lead">
            把前後比較與修改清單傳給設計師、前端工程師、主管或客戶。檢視者只能查看，無法修改，也看不到你的專案、點數與其他頁面。
          </p>

          <fieldset className="opt-access" disabled={busy}>
            <legend>誰可以檢視</legend>
            {ACCESS_OPTIONS.map((option) => (
              <label key={option.value} className={`opt-access-option ${access === option.value ? "is-selected" : ""}`}>
                <input
                  type="radio"
                  name="share-access"
                  value={option.value}
                  checked={access === option.value}
                  onChange={() => choose(option.value)}
                />
                <span>
                  <span className="opt-access-label">{option.label}</span>
                  <span className="opt-access-hint">{option.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>

          <div className="opt-share-link">
            <input
              className="opt-share-input"
              readOnly
              value={access === "private" ? "選擇「知道連結的任何人」或「已登入的人」後產生連結" : url}
              aria-label="分享連結"
              onFocus={(event) => event.target.select()}
            />
            <button
              type="button"
              className="primary-button"
              disabled={access === "private" || busy}
              onClick={copy}
            >
              {copied ? "已複製" : "複製連結"}
            </button>
          </div>
          {error && <p className="error-text" role="alert">{error}</p>}
          <p className="opt-dialog-note">
            {access === "private"
              ? "目前沒有分享。"
              : "連結不會過期；隨時改回「僅限我」即可關閉，之後再打開仍是同一個連結。"}
          </p>
        </div>
      </div>
    </div>,
    document.body,
  );
}
