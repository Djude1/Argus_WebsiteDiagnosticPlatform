// 公開子頁（快速檢查、團隊、購買、下載、查驗、404）共用的頁首。
//
// 品牌語言：掃描面細網格＋虹膜青光暈當底、等寬眉標、觀景窗四角框托住標題區。
// 首頁的 hero 另有插畫與輸入框，不走這個元件。
//
// title 可以傳 JSX：要強調的字包 <em>，CSS 會上虹膜青（不用漸層）。

export function PublicHero({ eyebrow, title, children, actions, aside, className = "" }) {
  return (
    <section className={`public-hero ${aside ? "has-aside" : ""} ${className}`}>
      <div className="public-hero-backdrop ag-surface-grid" aria-hidden="true" />
      <div className="public-hero-inner">
        <div className="public-hero-copy">
          {eyebrow && <span className="ag-eyebrow public-hero-eyebrow">{eyebrow}</span>}
          <h1 className="public-hero-title">{title}</h1>
          {children && <div className="public-hero-sub">{children}</div>}
          {actions && <div className="public-hero-actions">{actions}</div>}
        </div>
        {aside && <div className="public-hero-aside">{aside}</div>}
      </div>
    </section>
  );
}

/** 區段：眉標＋標題＋一句說明，內容置於下方。 */
export function PublicSection({ id, eyebrow, title, description, actions, children, className = "" }) {
  return (
    <section className={`public-section ${className}`} id={id}>
      {(title || eyebrow) && (
        <header className="public-section-head">
          <div className="public-section-head-text">
            {eyebrow && <span className="ag-eyebrow">{eyebrow}</span>}
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions && <div className="public-section-head-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export default PublicHero;
