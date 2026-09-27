import { ArgusMark } from "../../components/brand/ArgusMark";
import { AlertIcon, RefreshIcon } from "../../shared/ActionIcons";

/*
 * 會員區共用的頁面狀態：載入骨架、錯誤（一定附重試）、空狀態。
 * 只服務 features/account 內的頁面。
 */

/** 載入骨架：依頁面給出大致版型（hero + 卡片列），避免整頁跳動。 */
export function AccountSkeleton({ label = "載入中…", tiles = 4, blocks = 2 }) {
  return (
    <div className="acct-skeleton" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="acct-skel acct-skel-hero" aria-hidden="true" />
      {tiles > 0 && (
        <div className="acct-skel-row" aria-hidden="true">
          {Array.from({ length: tiles }, (_, i) => <div key={i} className="acct-skel acct-skel-tile" />)}
        </div>
      )}
      {Array.from({ length: blocks }, (_, i) => (
        <div key={i} className="acct-skel acct-skel-block" aria-hidden="true" />
      ))}
    </div>
  );
}

/** 區塊級錯誤：說明發生什麼事 + 重試鍵。 */
export function AccountError({ message, onRetry }) {
  return (
    <section className="acct-state is-error" role="alert">
      <span className="acct-state-icon"><AlertIcon /></span>
      <div className="acct-state-copy">
        <h2>{message}</h2>
        <p>可能是網路不穩或服務暫時忙碌，請稍後再試。</p>
      </div>
      {onRetry && (
        <button type="button" className="secondary-button" onClick={onRetry}>
          <RefreshIcon className="acct-btn-icon" /> 重新載入
        </button>
      )}
    </section>
  );
}

/** 空狀態：品牌標誌 + 標題 + 說明 + 行動。 */
export function AccountEmpty({ title, children, action }) {
  return (
    <section className="acct-state is-empty">
      <ArgusMark size={48} />
      <div className="acct-state-copy">
        <h2>{title}</h2>
        {children}
      </div>
      {action}
    </section>
  );
}
