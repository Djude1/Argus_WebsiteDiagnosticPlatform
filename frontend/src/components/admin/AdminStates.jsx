// 後台的三種非內容狀態：載入中、空、錯誤。
//
// 存在理由：原本後台 10 處載入狀態都是一行「載入中…」純文字，資料進來時版面會整個跳動；
// 錯誤則是整頁被一行字取代且沒有重試出口，使用者只能重新整理。這三個元件把狀態
// 收斂成可預期的樣子，並讓錯誤永遠留有下一步。

/**
 * 骨架。variant：
 *   table  — 表格列（用 rows 控制筆數）
 *   card   — 卡片格（用 rows 控制張數）
 *   detail — 詳情頁的區塊
 * 高度刻意貼近真實內容，避免資料載入後版面位移。
 */
export function AdminSkeleton({ variant = "table", rows = 6, label = "載入中" }) {
  const items = Array.from({ length: rows }, (_, index) => index);
  return (
    <div className={`admin-skeleton is-${variant}`} role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {variant === "card" && items.map((i) => (
        <div className="admin-skeleton-card" key={i}>
          <span className="admin-skeleton-bar w-40" />
          <span className="admin-skeleton-bar w-70 tall" />
          <span className="admin-skeleton-bar w-55" />
        </div>
      ))}
      {variant === "detail" && items.slice(0, 3).map((i) => (
        <div className="admin-skeleton-block" key={i}>
          <span className="admin-skeleton-bar w-30" />
          <span className="admin-skeleton-bar w-90" />
          <span className="admin-skeleton-bar w-70" />
        </div>
      ))}
      {variant === "table" && (
        <div className="admin-skeleton-table">
          <div className="admin-skeleton-row is-head">
            <span className="admin-skeleton-bar w-55" />
          </div>
          {items.map((i) => (
            <div className="admin-skeleton-row" key={i}>
              <span className="admin-skeleton-bar w-30" />
              <span className="admin-skeleton-bar w-55" />
              <span className="admin-skeleton-bar w-40" />
              <span className="admin-skeleton-bar w-25" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * 空狀態。刻意區分兩種語意——
 *   沒有資料：本來就還沒有東西，給「建立」的出口
 *   篩選後無結果：資料存在只是被篩掉了，給「清除篩選」的出口
 * 混為一談會讓人以為資料不見了。
 */
export function AdminEmptyState({
  title,
  description,
  icon,
  actionLabel,
  onAction,
  tone = "neutral",
}) {
  return (
    <div className={`admin-empty-state tone-${tone}`}>
      {icon && <span className="admin-empty-state-icon" aria-hidden="true">{icon}</span>}
      <p className="admin-empty-state-title">{title}</p>
      {description && <p className="admin-empty-state-desc">{description}</p>}
      {actionLabel && onAction && (
        <button type="button" className="admin-btn" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}

/**
 * 錯誤狀態。預設是「區塊級」而非整頁級：一個面板載入失敗不該讓整頁消失，
 * 其他還拿得到的資訊仍應留在畫面上。onRetry 存在時一定顯示重試鍵。
 */
export function AdminErrorState({ message, detail, onRetry, compact = false }) {
  return (
    <div className={`admin-error-state ${compact ? "is-compact" : ""}`} role="alert">
      <p className="admin-error-state-title">{message || "載入失敗"}</p>
      {detail && <p className="admin-error-state-detail">{detail}</p>}
      {onRetry && (
        <button type="button" className="admin-btn" onClick={onRetry}>
          重試
        </button>
      )}
    </div>
  );
}
