import argusEyeStill from "../../assets/argus-eye-still.webp";
import brandLogo from "../../assets/brand-logo.webp";

/*
 * Argus 品牌標誌。
 *
 * 一律使用專案原本的品牌圖：
 *   - ArgusMark：argus-eye-still.webp（Argus 之眼，登入頁、狀態圖示、空狀態等小圖示用）
 *   - ArgusLogo：brand-logo.webp（之眼 + ARGUS 字標，導覽列、頁尾、後台側欄用）
 * 呼叫端 API（size / scanning / subtitle）維持不變。
 */

const EYE_RATIO = 202 / 256; // argus-eye-still.webp 原始寬高比
const LOGO_RATIO = 1024 / 683; // brand-logo.webp 原始寬高比

type ArgusMarkProps = {
  size?: number;
  className?: string;
  /** 掃描中：之眼加上呼吸光暈（尊重 prefers-reduced-motion） */
  scanning?: boolean;
  title?: string;
};

export function ArgusMark({ size = 32, className = "", scanning = false, title }: ArgusMarkProps) {
  return (
    <img
      className={`ag-mark ${scanning ? "is-scanning" : ""} ${className}`}
      src={argusEyeStill}
      width={size}
      height={Math.round(size * EYE_RATIO)}
      style={{ width: size }}
      alt={title ?? ""}
      aria-hidden={title ? undefined : true}
      draggable={false}
    />
  );
}

type ArgusLogoProps = {
  size?: number;
  className?: string;
  subtitle?: string | null;
};

/** 品牌 logo（brand-logo.webp）+ 選填副標 */
export function ArgusLogo({ size = 34, className = "", subtitle = "AI 網站健檢平台" }: ArgusLogoProps) {
  const height = Math.round(size * 1.75);
  return (
    <span className={`ag-logo ${className}`}>
      <img
        className="ag-logo-img"
        src={brandLogo}
        height={height}
        width={Math.round(height * LOGO_RATIO)}
        style={{ height }}
        alt="ARGUS"
        draggable={false}
      />
      {subtitle ? <span className="ag-logo-sub">{subtitle}</span> : null}
    </span>
  );
}

export default ArgusMark;
