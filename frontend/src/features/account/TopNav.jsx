import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { ArgusLogo } from "../../components/brand/ArgusMark";
import NavActions, { accountInitial, useLogout } from "../../components/navigation/NavActions";
import { useArgusStore } from "../../store";
import { CloseIcon, LogoutIcon, MenuIcon } from "../../shared/ActionIcons";
import {
  ChartIcon,
  ClockIcon,
  CoinIcon,
  GearIcon,
  GlobeIcon,
  HomeIcon,
  MagnifierIcon,
  StarIcon,
} from "../../shared/LineIcons";

// 八個導覽項目依使用頻率排序。圖示統一走 currentColor：未選取時是次要文字色，
// 選取時跟著品牌主色——八個顏色並排只會互相搶注意力。
const NAV_ITEMS = [
  { to: "/project", label: "首頁", Icon: HomeIcon },
  { to: "/dashboard", label: "Dashboard", Icon: ChartIcon },
  { to: "/scans", label: "掃描", Icon: MagnifierIcon },
  { to: "/domains", label: "網域驗證", Icon: GlobeIcon },
  { to: "/history", label: "歷史", Icon: ClockIcon },
  { to: "/billing", label: "購點", Icon: CoinIcon },
  { to: "/reviews", label: "評論", Icon: StarIcon },
  { to: "/settings", label: "設定", Icon: GearIcon },
];

/** 窄螢幕的導覽抽屜：Esc／點背景關閉，開啟時鎖住焦點起點在第一個連結。 */
function NavDrawer({ items, onClose }) {
  const panelRef = useRef(null);
  const me = useArgusStore((s) => s.me);
  const wallet = useArgusStore((s) => s.wallet);
  const logout = useLogout();

  useEffect(() => {
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    panelRef.current?.querySelector("a, button")?.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  // 以 portal 掛到 body：導覽列有 backdrop-filter，會讓內部 position:fixed 以導覽列為定位基準
  return createPortal(
    <>
      <button type="button" className="app-drawer-backdrop" aria-label="關閉選單" tabIndex={-1} onClick={onClose} />
      <div className="app-drawer" role="dialog" aria-modal="true" aria-label="主選單" ref={panelRef}>
        <div className="app-drawer-head">
          <ArgusLogo size={28} subtitle={null} />
          <button type="button" className="app-icon-button" onClick={onClose} aria-label="關閉選單">
            <CloseIcon />
          </button>
        </div>
        <div className="app-drawer-account">
          <span className="app-avatar is-lg" aria-hidden="true">{accountInitial(me)}</span>
          <span className="app-drawer-account-id">
            <strong>{me?.display_name?.trim() || me?.email || "我的帳號"}</strong>
            <small className="ag-num">{wallet?.balance == null ? "—" : wallet.balance.toLocaleString()} coin</small>
          </span>
        </div>
        <nav aria-label="主要導覽">
          <ul className="app-drawer-links">
            {items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) => `app-drawer-link ${isActive ? "is-active" : ""}`}
                  onClick={onClose}
                >
                  <item.Icon className="app-nav-icon" />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <button type="button" className="app-drawer-logout" onClick={() => { onClose(); logout(); }}>
          <LogoutIcon /> 登出
        </button>
      </div>
    </>,
    document.body,
  );
}

function TopNav() {
  const accessToken = useArgusStore((state) => state.accessToken);
  const replayIntro = useArgusStore((s) => s.replayIntro);
  const location = useLocation();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  // 換頁即收起抽屜
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  if (!accessToken) return null;
  // /admin/* 與公開頁走獨立 layout，不顯示前台 TopNav
  if (location.pathname.startsWith("/admin")) return null;
  if (["/project", "/purchase", "/download"].some((p) =>
    location.pathname.startsWith(p),
  )) return null;
  // 掃描頁的 top bar 不顯示「評論」入口（首頁等其他頁保留）
  const onScanPage = location.pathname.startsWith("/scans");
  const visibleNavItems = onScanPage
    ? NAV_ITEMS.filter((item) => item.to !== "/reviews")
    : NAV_ITEMS;
  return (
    <header className="app-nav">
      <div className="app-nav-inner">
        <button
          type="button"
          className="app-nav-menu-btn app-icon-button"
          onClick={() => setDrawerOpen(true)}
          aria-label="開啟主選單"
          aria-expanded={drawerOpen}
        >
          <MenuIcon />
        </button>
        <button
          type="button"
          className="app-nav-brand"
          onClick={() => { replayIntro(); navigate("/project"); }}
          title="重播開場動畫"
          aria-label="重播 ARGUS 開場動畫"
        >
          <ArgusLogo size={30} subtitle="AI 網站健檢平台" />
        </button>
        <nav className="app-nav-links" aria-label="主要導覽">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `app-nav-link ${isActive ? "is-active" : ""}`}
            >
              <item.Icon className="app-nav-icon" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <NavActions />
      </div>
      {drawerOpen && <NavDrawer items={visibleNavItems} onClose={closeDrawer} />}
    </header>
  );
}

export default TopNav;
export { TopNav };
