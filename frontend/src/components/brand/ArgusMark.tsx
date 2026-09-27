import { useId } from "react";

/*
 * Argus 品牌標誌（向量版）。
 *
 * 構成：杏眼輪廓 + 由 12 顆「小眼」圍成的虹膜（百眼巨人 Argus Panoptes）
 * + 瞳孔 + 一點守望琥珀的反光。整體以 currentColor 以外的品牌 token 著色，
 * 深／淺主題自動切換；任何尺寸（16px favicon 到 hero）都清晰。
 *
 * 取代原本 164 KB 的點陣 logo（小尺寸糊成一團、日間模式白邊）。
 */

const IRIS_DOTS = Array.from({ length: 12 }, (_, i) => {
  const angle = (i / 12) * Math.PI * 2 - Math.PI / 2;
  return { cx: 24 + Math.cos(angle) * 8.6, cy: 24 + Math.sin(angle) * 8.6 };
});

type ArgusMarkProps = {
  size?: number;
  className?: string;
  /** 掃描中：虹膜小眼依序亮起（尊重 prefers-reduced-motion） */
  scanning?: boolean;
  title?: string;
};

export function ArgusMark({ size = 32, className = "", scanning = false, title }: ArgusMarkProps) {
  const gradientId = useId();
  return (
    <svg
      className={`ag-mark ${scanning ? "is-scanning" : ""} ${className}`}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <defs>
        <linearGradient id={gradientId} x1="6" y1="10" x2="42" y2="38" gradientUnits="userSpaceOnUse">
          <stop offset="0" className="ag-mark-stop-a" />
          <stop offset="1" className="ag-mark-stop-b" />
        </linearGradient>
      </defs>
      <path
        className="ag-mark-lid"
        d="M3.5 24C9.2 14.6 16.2 10 24 10s14.8 4.6 20.5 14C38.8 33.4 31.8 38 24 38S9.2 33.4 3.5 24Z"
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      <g className="ag-mark-iris">
        {IRIS_DOTS.map((dot, index) => (
          <circle
            key={index}
            cx={dot.cx}
            cy={dot.cy}
            r="1.55"
            className="ag-mark-eye"
            style={{ animationDelay: `${index * 90}ms` }}
          />
        ))}
      </g>
      <circle cx="24" cy="24" r="4.6" className="ag-mark-pupil" />
      <circle cx="26.3" cy="21.7" r="1.35" className="ag-mark-glint" />
    </svg>
  );
}

type ArgusLogoProps = {
  size?: number;
  className?: string;
  subtitle?: string | null;
};

/** 標誌 + ARGUS 字標（Sora 寬字距）+ 選填副標 */
export function ArgusLogo({ size = 34, className = "", subtitle = "AI 網站健檢平台" }: ArgusLogoProps) {
  return (
    <span className={`ag-logo ${className}`}>
      <ArgusMark size={size} />
      <span className="ag-logo-text">
        <span className="ag-logo-word">ARGUS</span>
        {subtitle ? <span className="ag-logo-sub">{subtitle}</span> : null}
      </span>
    </span>
  );
}

export default ArgusMark;
