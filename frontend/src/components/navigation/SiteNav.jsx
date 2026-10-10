import { NavLink, useNavigate } from "react-router-dom";

import brandLogo from "../../assets/brand-logo.webp";
import { useArgusStore } from "../../store";

// 全站頂部導覽列：公開頁（PublicLayout）與登入後頁面（TopNav）共用同一個外殼，
// 視覺以公開頁為準（.public-nav 系列樣式，見 21-public.css／35-public-legacy.css）。
// 兩邊只差「連結清單」與「右側動作區」（公開頁是登入鈕、登入後是點數與帳號選單）。

function ThemeToggleIcon({ theme }) {
  if (theme === "light") {
    return (
      <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
        <path d="M20.4 15.1A8.2 8.2 0 0 1 8.9 3.6 8.3 8.3 0 1 0 20.4 15.1Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

/** 公開頁風格的日／夜切換鈕（圖示＋文字）。 */
export function SiteThemeToggle() {
  const theme = useArgusStore((s) => s.theme);
  const toggleTheme = useArgusStore((s) => s.toggleTheme);
  const label = theme === "light" ? "切換至夜間模式" : "切換至日間模式";
  return (
    <button type="button" className="theme-toggle" onClick={toggleTheme} title={label} aria-label={label}>
      <span className="theme-toggle-icon" aria-hidden="true">
        <ThemeToggleIcon theme={theme} />
      </span>
      <span>{theme === "light" ? "夜間" : "日間"}</span>
    </button>
  );
}

/**
 * leading：品牌右側的區塊（登入後是網站專案切換器）；item.end＝只在網址完全相同時標示目前頁。
 * brandTo：點品牌要去的頁面；沒給時（公開頁）回產品介紹並重播開場動畫。
 * @param {{ items: {to: string, label: string, end?: boolean}[], actions: React.ReactNode, leading?: React.ReactNode, className?: string, brandTo?: {path: string, label: string} | null }} props
 */
export default function SiteNav({ items, actions, leading = null, className = "", brandTo = null }) {
  const replayIntro = useArgusStore((s) => s.replayIntro);
  const navigate = useNavigate();
  return (
    <nav className={`public-nav ${className}`} aria-label="主要導覽">
      <div className="public-nav-inner">
        <button
          type="button"
          className="public-brand active"
          onClick={() => {
            if (brandTo) {
              navigate(brandTo.path);
              return;
            }
            replayIntro();
            navigate("/project");
          }}
          title={brandTo ? brandTo.label : "重播開場動畫"}
          aria-label={brandTo ? `ARGUS：${brandTo.label}` : "重播 ARGUS 開場動畫"}
        >
          <img src={brandLogo} className="public-brand-logo" alt="ARGUS — AI網站健檢平台" />
          <span className="public-brand-sub">AI網站健檢平台</span>
        </button>
        {leading}
        {items.length > 0 && (
        <div className="public-nav-links">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `public-nav-link ${isActive ? "active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        )}
        <div className="public-nav-cta">{actions}</div>
      </div>
    </nav>
  );
}
