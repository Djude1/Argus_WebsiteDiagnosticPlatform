import { useLocation } from "react-router-dom";

import NavActions from "../../components/navigation/NavActions";
import ProjectSwitcher from "../../components/navigation/ProjectSwitcher";
import SiteNav, { SiteThemeToggle } from "../../components/navigation/SiteNav";
import { useArgusStore } from "../../store";

// 登入後導覽列：外觀與公開頁導覽列一致（共用 SiteNav），只換連結與右側動作區。
// 窄螢幕沿用公開頁做法——連結列換到第二行、可左右滑動。
// 目前網站的功能（總覽、掃描、問題分析、歷史報告、設定）在工作區側邊欄；這裡只放帳號層級的入口，
// 網站的新增與切換在品牌旁的專案切換器（docs/adr/0003-site-project-workspace.md）。
const NAV_ITEMS = [
  { to: "/project", label: "首頁" },
  { to: "/projects", label: "所有專案", end: true },
  { to: "/domains", label: "網域驗證" },
  { to: "/billing", label: "購點" },
  { to: "/mcp", label: "MCP 接入中心" },
];

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
      leading={<ProjectSwitcher />}
      actions={(
        <>
          <SiteThemeToggle />
          <NavActions showThemeToggle={false} />
        </>
      )}
    />
  );
}

export default TopNav;
export { TopNav };
