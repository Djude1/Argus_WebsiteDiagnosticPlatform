import React from "react";

// 後台 sidebar nav icon 系統：每個功能一個滿版、可一眼辨識的獨立圖形，
// 右上角統一疊一個小 ⟡ 品牌角標做識別（取代先前每顆圖示都以整顆 ⟡ 菱形當底、
// 功能記號被壓縮成右下角極小線稿而看起來千篇一律的版本）。

function IconShell({ className, ariaHidden = true, title, children }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="19"
      height="19"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={ariaHidden}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {children}
      {/* ⟡ 品牌角標：固定右上角小記號，統一識別但不搶主圖形風采 */}
      <g className="accent" fill="currentColor" stroke="none">
        <path d="M19.4 2.6c.32 1.12.72 1.52 1.84 1.84-1.12.32-1.52.72-1.84 1.84-.32-1.12-.72-1.52-1.84-1.84 1.12-.32 1.52-.72 1.84-1.84Z" />
      </g>
    </svg>
  );
}

export function AdminOverviewIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：儀表板 2x2 格 */}
      <rect x="3.4" y="3.4" width="7" height="7" rx="1.6" />
      <rect x="13.6" y="3.4" width="7" height="7" rx="1.6" />
      <rect x="3.4" y="13.6" width="7" height="7" rx="1.6" />
      <rect x="13.6" y="13.6" width="7" height="7" rx="1.6" />
    </IconShell>
  );
}

export function AdminUsersIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：人像（頭 + 肩膀） */}
      <circle cx="12" cy="8.2" r="3.3" />
      <path d="M5 20c1.4-4.3 4-6 7-6s5.6 1.7 7 6" />
    </IconShell>
  );
}

export function AdminScansIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：雷達準星 */}
      <circle cx="12" cy="12" r="7.5" />
      <circle cx="12" cy="12" r="3" />
      <line x1="12" y1="2.3" x2="12" y2="5.1" />
      <line x1="12" y1="18.9" x2="12" y2="21.7" />
      <line x1="2.3" y1="12" x2="5.1" y2="12" />
      <line x1="18.9" y1="12" x2="21.7" y2="12" />
    </IconShell>
  );
}

export function AdminTransactionsIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：交疊雙硬幣 */}
      <circle cx="9.3" cy="9.3" r="6.3" />
      <circle cx="14.7" cy="14.7" r="6.3" />
    </IconShell>
  );
}

export function AdminPlansIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：三層方案階梯 */}
      <rect x="7" y="3" width="10" height="4" rx="1.3" />
      <rect x="4.3" y="9.7" width="15.4" height="4" rx="1.3" />
      <rect x="1.6" y="16.4" width="20.8" height="4" rx="1.3" />
    </IconShell>
  );
}

export function AdminContentIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：文件 + 折角 + 內文線 */}
      <path d="M6.5 3h7.5l4.5 4.5V21h-12Z" />
      <path d="M14 3v4.5h4.5" />
      <line x1="9" y1="12.3" x2="15" y2="12.3" />
      <line x1="9" y1="15.7" x2="15" y2="15.7" />
      <line x1="9" y1="19" x2="12.5" y2="19" />
    </IconShell>
  );
}

export function AdminReviewsIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：實心五角星 */}
      <path
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="1"
        d="M12 2.8l2.85 6.1 6.65.7-4.95 4.55 1.35 6.55L12 17.1l-5.9 3.6 1.35-6.55-4.95-4.55 6.65-.7Z"
      />
    </IconShell>
  );
}

export function AdminSettingsIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：8 向放射齒輪 */}
      <circle cx="12" cy="12" r="3" />
      <line x1="12" y1="3.8" x2="12" y2="6.8" />
      <line x1="12" y1="17.2" x2="12" y2="20.2" />
      <line x1="3.8" y1="12" x2="6.8" y2="12" />
      <line x1="17.2" y1="12" x2="20.2" y2="12" />
      <line x1="6.1" y1="6.1" x2="8.3" y2="8.3" />
      <line x1="15.7" y1="15.7" x2="17.9" y2="17.9" />
      <line x1="6.1" y1="17.9" x2="8.3" y2="15.7" />
      <line x1="15.7" y1="8.3" x2="17.9" y2="6.1" />
    </IconShell>
  );
}

export function AdminAuditLogIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：時鐘 */}
      <circle cx="12" cy="12" r="8.3" />
      <path d="M12 7.2v5l3.6 2.1" />
    </IconShell>
  );
}

export function AdminAnnouncementsIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：喇叭 + 音波 */}
      <path d="M3.5 10.3v3.4h3l6.2 3.7V6.6l-6.2 3.7Z" />
      <path d="M15.5 9.3a4 4 0 0 1 0 5.4" />
      <path d="M18.3 6.8a8 8 0 0 1 0 10.4" />
    </IconShell>
  );
}

// ---- 概覽頁 stat card / panel 標頭用圖示（延續同一套 IconShell 語言） ----

export function AdminOrdersIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：收據（鋸齒底 + 內文線），呼應「訂單」 */}
      <path d="M6 3h12v16.5l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3Z" />
      <line x1="9" y1="7.5" x2="15" y2="7.5" />
      <line x1="9" y1="11" x2="15" y2="11" />
      <line x1="9" y1="14.5" x2="13" y2="14.5" />
    </IconShell>
  );
}

export function AdminTokensIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：晶片 + 閃電，呼應 AI 運算用量 */}
      <rect x="4" y="4" width="16" height="16" rx="4" />
      <path
        fill="currentColor"
        stroke="none"
        d="M13 8l-4.5 6H12l-1 4 4.5-6H12Z"
      />
    </IconShell>
  );
}

export function AdminAlertIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：警示三角形 + 驚嘆號 */}
      <path d="M12 3.5 21 19.5H3Z" />
      <line x1="12" y1="9.3" x2="12" y2="14" />
      <circle cx="12" cy="16.8" r="0.9" fill="currentColor" stroke="none" />
    </IconShell>
  );
}

export function AdminTrendIcon(props) {
  return (
    <IconShell {...props}>
      {/* 主圖形：上升折線 + 端點，呼應趨勢圖表 */}
      <path d="M3.5 16.5l4.5-5 3.5 3 4-6 4.5 3.5" />
      <circle cx="20" cy="12" r="1.3" fill="currentColor" stroke="none" />
    </IconShell>
  );
}

// ---- 功能性 glyph（無 ⟡ 底；沿用同一套 stroke 線稿語言，取代頁面內文 Unicode 符號） ----

function GlyphShell({ className, ariaHidden = true, title, children }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={ariaHidden}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

export function AdminMenuIcon(props) {
  return (
    <GlyphShell {...props}>
      <line x1="5" y1="7" x2="19" y2="7" />
      <line x1="5" y1="12" x2="19" y2="12" />
      <line x1="5" y1="17" x2="19" y2="17" />
    </GlyphShell>
  );
}

const STAR_PATH =
  "M12 3.5l2.47 5.61 6.03.57-4.55 4.06 1.3 5.91L12 16.9l-5.25 2.75 1.3-5.91L3.5 9.68l6.03-.57Z";

export function AdminStarIcon({ filled = true, ...props }) {
  return (
    <GlyphShell {...props}>
      <path
        d={STAR_PATH}
        fill={filled ? "currentColor" : "none"}
        strokeWidth={filled ? "1" : "1.75"}
      />
    </GlyphShell>
  );
}
