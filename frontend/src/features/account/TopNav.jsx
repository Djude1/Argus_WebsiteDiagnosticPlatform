import { NavLink, useLocation } from "react-router-dom";

import CommandSearch from "../../components/navigation/CommandSearch";
import NavActions from "../../components/navigation/NavActions";
import NotificationBell from "../../components/navigation/NotificationBell";
import ProjectSwitcher from "../../components/navigation/ProjectSwitcher";
import SiteNav, { SiteThemeToggle } from "../../components/navigation/SiteNav";
import { RobotIcon, ShieldIcon } from "../../shared/LineIcons";
import { useArgusStore } from "../../store";

// 登入後導覽列：外觀與公開頁導覽列一致（共用 SiteNav），只換連結與右側動作區。
// 窄螢幕沿用公開頁做法——連結列換到第二行、可左右滑動。
// 目前網站的功能（總覽、掃描、問題分析、歷史報告、設定）在工作區側邊欄；這裡只放帳號層級的入口，
// 網站的新增與切換在品牌旁的專案切換器（docs/adr/0003-site-project-workspace.md）。
// 2026-10-03 依參考設計：頂部列是「品牌｜網站切換器｜搜尋（⌘K）｜日夜｜通知｜點數｜帳號」，不放文字連結；
// 所有專案在切換器與工作區側邊欄，帳號設定、購點在帳號選單（2026-10-03 移除選單裡的所有專案、評論、
// 產品介紹；產品介紹與評論改由側邊欄底部連結進入）。品牌標誌回到所有專案。
// 2026-10-04：網域驗證與 MCP 接入是帳號層級工具，放在搜尋框右側的工具連結（不藏在頭像選單、
// 也不放側邊欄——側邊欄已經夠長）；中等寬度只留圖示，窄螢幕與搜尋框同一列（.nav-search-row）。
const NAV_ITEMS = [];
const NAV_TOOLS = [
  { to: "/domains", label: "網域驗證", Icon: ShieldIcon },
  { to: "/mcp", label: "MCP 接入", Icon: RobotIcon },
];

function NavTools() {
  return (
    <div className="nav-tools">
      {NAV_TOOLS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          title={label}
          className={({ isActive }) => `nav-tool-link${isActive ? " is-active" : ""}`}
        >
          <Icon />
          <span className="nav-tool-label">{label}</span>
        </NavLink>
      ))}
    </div>
  );
}

function TopNav() {
  const accessToken = useArgusStore((state) => state.accessToken);
  const location = useLocation();

  if (!accessToken) return null;
  // /admin/* 與公開頁走獨立 layout，不顯示前台 TopNav
  if (location.pathname.startsWith("/admin")) return null;
  if (["/project", "/purchase", "/download"].some((p) =>
    location.pathname === p || location.pathname.startsWith(`${p}/`),
  )) return null;
  return (
    <SiteNav
      className="is-member"
      items={NAV_ITEMS}
      brandTo={{ path: "/projects", label: "回到所有專案" }}
      leading={(
        <>
          <ProjectSwitcher />
          <div className="nav-search-row">
            <CommandSearch />
            <NavTools />
          </div>
        </>
      )}
      actions={(
        <>
          <SiteThemeToggle />
          <NotificationBell />
          <NavActions showThemeToggle={false} />
        </>
      )}
    />
  );
}

export default TopNav;
export { TopNav };
