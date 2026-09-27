import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useArgusStore } from "../../store";
import { ArgusLogo } from "../../components/brand/ArgusMark";

// 公開頁共用外框：top nav（品牌、主要連結、主題切換、登入入口）＋ footer。
// /reviews 也掛在這個 layout 底下，所以 .public-main 只負責版心與留白，
// 不假設子頁長什麼樣。

const PUBLIC_NAV_ITEMS = [
  { to: "/project", label: "專案介紹" },
  { to: "/free-tools", label: "快速檢查" },
  { to: "/team", label: "團隊" },
  { to: "/purchase", label: "購買" },
  { to: "/download", label: "下載" },
  { to: "/reviews", label: "評論" },
];

const FOOTER_GROUPS = [
  {
    title: "產品",
    links: [
      { to: "/project", label: "專案介紹" },
      { to: "/free-tools", label: "免費快速檢查" },
      { to: "/purchase", label: "方案與計費" },
      { to: "/download", label: "下載 PWA" },
    ],
  },
  {
    title: "信任",
    links: [
      { to: "/verify", label: "報告查驗" },
      { to: "/reviews", label: "使用者評論" },
      { to: "/team", label: "團隊" },
    ],
  },
];

function ThemeToggleIcon({ theme }) {
  // 顯示「按下去會切到哪個主題」：日間時給月亮、夜間時給太陽
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

function ThemeToggle() {
  const theme = useArgusStore((s) => s.theme);
  const toggleTheme = useArgusStore((s) => s.toggleTheme);
  const label = theme === "light" ? "切換至夜間模式" : "切換至日間模式";
  return (
    <button type="button" className="theme-toggle" onClick={toggleTheme} title={label} aria-label={label}>
      <span className="theme-toggle-icon" aria-hidden="true">
        <ThemeToggleIcon theme={theme} />
      </span>
      <span className="theme-toggle-text">{theme === "light" ? "夜間" : "日間"}</span>
    </button>
  );
}

function PublicNav() {
  const accessToken = useArgusStore((s) => s.accessToken);
  const replayIntro = useArgusStore((s) => s.replayIntro);
  const navigate = useNavigate();
  return (
    <nav className="public-nav" aria-label="公開頁導覽">
      <div className="public-nav-inner">
        <button
          type="button"
          className="public-brand"
          onClick={() => { replayIntro(); navigate("/project"); }}
          title="重播開場動畫"
          aria-label="重播 ARGUS 開場動畫"
        >
          <ArgusLogo size={32} />
        </button>
        <div className="public-nav-links">
          {PUBLIC_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `public-nav-link ${isActive ? "active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
        <div className="public-nav-cta">
          <ThemeToggle />
          <NavLink to={accessToken ? "/dashboard" : "/login"} className="public-cta public-cta-primary public-nav-login">
            {accessToken ? "進入 Dashboard" : "登入 / 註冊"}
          </NavLink>
        </div>
      </div>
    </nav>
  );
}

function PublicFooter() {
  return (
    <footer className="public-footer">
      <div className="public-footer-inner">
        <div className="public-footer-brand">
          <ArgusLogo size={30} subtitle="授權式 AI 網站健檢平台" />
          <p className="public-footer-tagline">
            看見網站在 SEO、AEO、GEO、資安與 UX 上的問題，並直接給出可用的修正。
          </p>
        </div>
        {FOOTER_GROUPS.map((group) => (
          <div className="public-footer-group" key={group.title}>
            <h2 className="public-footer-group-title">{group.title}</h2>
            <ul>
              {group.links.map((link) => (
                <li key={link.to}>
                  <NavLink to={link.to}>{link.label}</NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="public-footer-bottom">
        <span>© Argus</span>
        <span className="public-footer-note">僅供授權測試的網站健檢工具</span>
      </div>
    </footer>
  );
}

export function PublicLayout() {
  return (
    <div className="public-shell">
      <PublicNav />
      <main className="public-main">
        <Outlet />
      </main>
      <PublicFooter />
    </div>
  );
}

export default PublicLayout;
