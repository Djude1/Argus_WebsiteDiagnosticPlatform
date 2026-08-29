import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import brandLogo from "../../assets/brand-logo.webp";
import { useArgusStore } from "../../store";

const PUBLIC_NAV_ITEMS = [
  { to: "/project", label: "專案介紹" },
  { to: "/free-tools", label: "快速檢查" },
  { to: "/team", label: "團隊" },
  { to: "/purchase", label: "購買" },
  { to: "/download", label: "下載" },
  { to: "/reviews", label: "評論" },
];

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

function MenuToggleIcon({ open }) {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      {open ? (
        <path d="M6 6l12 12M18 6 6 18" />
      ) : (
        <path d="M4 7h16M4 12h16M4 17h16" />
      )}
    </svg>
  );
}

export default function PublicTopBar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const accessToken = useArgusStore((state) => state.accessToken);
  const replayIntro = useArgusStore((state) => state.replayIntro);
  const theme = useArgusStore((state) => state.theme);
  const toggleTheme = useArgusStore((state) => state.toggleTheme);
  const navigate = useNavigate();
  const nextThemeLabel = theme === "light" ? "夜間" : "日間";

  return (
    <nav
      className="public-nav"
      onKeyDown={(event) => {
        if (event.key === "Escape") setMobileMenuOpen(false);
      }}
    >
      <div className="public-nav-inner">
        <button
          type="button"
          className="public-brand active"
          onClick={() => {
            setMobileMenuOpen(false);
            replayIntro();
            navigate("/project");
          }}
          title="重播開場動畫"
          aria-label="重播 ARGUS 開場動畫"
        >
          <img src={brandLogo} className="public-brand-logo" alt="ARGUS — AI 網站健檢平台" />
          <span className="public-brand-sub">AI 網站健檢平台</span>
        </button>

        <div
          id="public-mobile-navigation"
          className={`public-nav-links ${mobileMenuOpen ? "is-open" : ""}`}
        >
          {PUBLIC_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `public-nav-link ${isActive ? "active" : ""}`}
              onClick={() => setMobileMenuOpen(false)}
            >
              {item.label}
            </NavLink>
          ))}
        </div>

        <div className="public-nav-cta">
          <button
            type="button"
            className="public-menu-toggle"
            onClick={() => setMobileMenuOpen((open) => !open)}
            title={mobileMenuOpen ? "關閉導覽選單" : "開啟導覽選單"}
            aria-label={mobileMenuOpen ? "關閉導覽選單" : "開啟導覽選單"}
            aria-controls="public-mobile-navigation"
            aria-expanded={mobileMenuOpen}
          >
            <MenuToggleIcon open={mobileMenuOpen} />
          </button>

          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            title={`切換至${nextThemeLabel}模式`}
            aria-label={`切換至${nextThemeLabel}模式`}
          >
            <span className="theme-toggle-icon" aria-hidden="true">
              <ThemeToggleIcon theme={theme} />
            </span>
            <span>{nextThemeLabel}</span>
          </button>

          <NavLink
            to={accessToken ? "/dashboard" : "/login"}
            className="public-cta-primary"
            aria-label={accessToken ? "進入 Dashboard" : "登入或註冊"}
            onClick={() => setMobileMenuOpen(false)}
          >
            <span className="public-auth-label-full">
              {accessToken ? "進入 Dashboard" : "登入 / 註冊"}
            </span>
            <span className="public-auth-label-compact" aria-hidden="true">
              {accessToken ? "後台" : "登入"}
            </span>
          </NavLink>
        </div>
      </div>
    </nav>
  );
}
