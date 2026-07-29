import React from "react";

// 後台 sidebar nav icon 系統：以 Argus ⟡ 為基底，加上功能性記號
// 設計詳見 docs/superpowers/specs/2026-07-29-admin-sidebar-argus-icons-design.md

function IconShell({ className, ariaHidden = true, title, children }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="18"
      height="18"
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
      {/* ⟡ base */}
      <path d="M12 4c1.25 4.85 3.15 6.75 8 8-4.85 1.25-6.75 3.15-8 8-1.25-4.85-3.15-6.75-8-8 4.85-1.25 6.75-3.15 8-8Z" />
      {children}
    </svg>
  );
}

export function AdminOverviewIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 2x2 dot grid */}
      <g className="accent" fill="currentColor" stroke="none">
        <circle cx="17" cy="17" r="0.9" />
        <circle cx="20.5" cy="17" r="0.9" />
        <circle cx="17" cy="20.5" r="0.9" />
        <circle cx="20.5" cy="20.5" r="0.9" />
      </g>
    </IconShell>
  );
}

export function AdminUsersIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 頭像（圓 + 肩膀弧） */}
      <g className="accent">
        <circle cx="18" cy="15.5" r="1.5" />
        <path d="M14.5 21c1-2.5 2.5-3.5 3.5-3.5s2.5 1 3.5 3.5" />
      </g>
    </IconShell>
  );
}

export function AdminScansIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 十字準星 */}
      <g className="accent">
        <line x1="18" y1="14.5" x2="18" y2="21" />
        <line x1="14.75" y1="17.75" x2="21.25" y2="17.75" />
        <circle cx="18" cy="17.75" r="0.9" fill="currentColor" stroke="none" />
      </g>
    </IconShell>
  );
}

export function AdminTransactionsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: coin（圓 + 中心點） */}
      <g className="accent">
        <circle cx="18" cy="18" r="3.5" />
        <circle cx="18" cy="18" r="0.8" fill="currentColor" stroke="none" />
      </g>
    </IconShell>
  );
}

export function AdminPlansIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 三層堆疊 */}
      <g className="accent">
        <line x1="14" y1="16" x2="21" y2="16" />
        <line x1="14" y1="18.5" x2="19.5" y2="18.5" />
        <line x1="14" y1="21" x2="18" y2="21" />
      </g>
    </IconShell>
  );
}

export function AdminContentIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 文件折角 */}
      <g className="accent">
        <path d="M14 13.5h5l2 2v6.5h-7z" />
        <path d="M19 13.5v2h2" />
      </g>
    </IconShell>
  );
}

export function AdminReviewsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 五角星 */}
      <path
        className="accent"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="1"
        d="M19 13.5L20.1 16.7 23.5 17 20.9 19 21.7 22.3 19 20.5 16.3 22.3 17.1 19 14.5 17 17.9 16.7Z"
      />
    </IconShell>
  );
}

export function AdminSettingsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 簡化齒輪（3 放射 + 中心圓） */}
      <g className="accent">
        <line x1="18" y1="14.5" x2="18" y2="16" />
        <line x1="14.9" y1="19.6" x2="15.9" y2="18.6" />
        <line x1="21.1" y1="19.6" x2="20.1" y2="18.6" />
        <circle cx="18" cy="18" r="1" />
      </g>
    </IconShell>
  );
}

export function AdminAuditLogIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 時鐘 */}
      <g className="accent">
        <circle cx="18" cy="18" r="3.5" />
        <path d="M18 18V15.5M18 18L20 17.5" />
      </g>
    </IconShell>
  );
}

export function AdminAnnouncementsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 同心音波（3 條從左下放射的弧） */}
      <g className="accent">
        <path d="M14.5 21A2.5 2.5 0 0 1 14 18.5" />
        <path d="M14.5 21A4 4 0 0 1 14 17" />
        <path d="M14.5 21A5.5 5.5 0 0 1 14 15.5" />
      </g>
    </IconShell>
  );
}
