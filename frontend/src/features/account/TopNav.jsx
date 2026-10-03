import { useLocation } from "react-router-dom";

import NavActions from "../../components/navigation/NavActions";
import SiteNav, { SiteThemeToggle } from "../../components/navigation/SiteNav";
import { useArgusStore } from "../../store";

// 登入後導覽列：外觀與公開頁導覽列一致（共用 SiteNav），只換連結與右側動作區。
// 窄螢幕沿用公開頁做法——連結列換到第二行、可左右滑動。
const NAV_ITEMS = [
  { to: "/project", label: "首頁" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/scans", label: "掃描" },
  { to: "/domains", label: "網域驗證" },
  { to: "/history", label: "歷史" },
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
    location.pathname.startsWith(p),
  )) return null;
  return (
    <SiteNav
      className="is-member"
      items={NAV_ITEMS}
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
