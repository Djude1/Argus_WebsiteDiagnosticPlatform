// 頁面切換／頁面資料載入的動畫：Argus Minimal Loading Pack「01 · Signal Bars」原樣使用
// （2026-10-10 使用者指定：動畫與下方「Loading」字樣都不改）。
// label 只給螢幕閱讀器，說明正在載入什麼；畫面上固定顯示「Loading」。
// 樣式：會員區外在 05-brand.css；會員區內在 legacy-member/92-layout.css（舊版範圍會重置外部規則）。
function PageLoader({ label = "載入中…", className = "" }) {
  return (
    <div className={`ag-page-loader ${className}`} role="status" aria-live="polite">
      <div>
        <div className="ag-signal" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
          <i />
        </div>
        <div className="ag-loader-label" aria-hidden="true">Loading</div>
        <span className="ag-sr-only">{label}</span>
      </div>
    </div>
  );
}

export default PageLoader;
