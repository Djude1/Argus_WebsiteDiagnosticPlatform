import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectSeoPage } from "./ProjectSeoPage";

vi.mock("../../api", () => ({ api: { get: vi.fn(), post: vi.fn() }, setAccessToken: vi.fn() }));
const { api } = vi.mocked(await import("../../api"));
const project = { id: 7, name: "測試網站", origin: "https://example.test", is_demo: false };
let connection: Record<string, unknown>;

function renderPage(query = "") {
  return render(
    <MemoryRouter initialEntries={[`/projects/7/seo${query}`]}>
      <Routes>
        <Route path="/projects/:projectId" element={<Outlet context={{ project }} />}>
          <Route path="seo" element={<ProjectSeoPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  connection = { enabled: true, connected: false, property: "", needs_reconnect: false };
  api.get.mockImplementation(async (url: string) => {
    if (url === "/projects/7/seo/") return { data: { scan: null, gsc: connection } };
    if (url === "/projects/7/gsc/properties/") {
      return { data: { properties: [{ site_url: "https://example.test/", matches: true }] } };
    }
    return { data: { results: [] } };
  });
});

describe("尚未掃描的網站連接 Search Console", () => {
  it("可以先連接 GSC，同時保留建立 SEO 掃描的入口", async () => {
    renderPage();
    expect(await screen.findByRole("button", { name: "連接 Search Console" })).toBeEnabled();
    expect(screen.getByText("還沒有完成的掃描")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "建立掃描" })).toHaveAttribute("href", "/projects/7/scans");
  });

  it("授權後可選資源，不要求先建立掃描", async () => {
    connection = { ...connection, connected: true };
    renderPage();
    expect(await screen.findByRole("button", { name: "選擇" })).toBeEnabled();
    expect(screen.getByText("https://example.test/")).toBeInTheDocument();
  });

  it("沒有掃描時仍顯示 Google 回呼錯誤，且可以關閉提示", async () => {
    renderPage("?gsc=error&reason=" + encodeURIComponent("Google 授權測試失敗"));
    expect(await screen.findByRole("status")).toHaveTextContent("Google 授權測試失敗");
    await userEvent.click(screen.getByRole("button", { name: "知道了" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("搜尋關鍵字：目標關鍵字與 Search Console 的落差", () => {
  beforeEach(() => {
    const seo = {
      scan: { id: 1, completed_at: "2026-10-07T00:00:00Z", seo_checked: true },
      overview: { pages_scanned: 1 },
      gsc: { enabled: true, connected: true, property: "https://example.test/", needs_reconnect: false },
      keywords: ["咖啡豆"],
      keyword_report: [{
        keyword: "咖啡豆", pages_found: 1, advice: "", pages: [],
        best_page: { page_id: 3, url: "https://example.test/beans", title: "豆子", places: ["Title"], body_count: 4 },
      }],
    };
    const performance = {
      property: "https://example.test/", start: "2026-09-07", end: "2026-10-04", days: 28,
      totals: { clicks: 9, impressions: 700, ctr: 0.0129 },
      queries: [
        { query: "台北 咖啡豆", clicks: 6, impressions: 400, ctr: 0.015, position: 13.4, page: "https://example.test/", clicks_change: null, position_change: null },
        { query: "耳掛咖啡", clicks: 3, impressions: 300, ctr: 0.01, position: 7.2, page: "https://example.test/drip", clicks_change: null, position_change: null },
      ],
      pages: [], trend: [],
    };
    api.get.mockImplementation(async (url: string) => {
      if (url === "/projects/7/seo/") return { data: seo };
      if (url === "/projects/7/gsc/performance/") return { data: performance };
      return { data: { results: [] } };
    });
    api.post.mockResolvedValue({ data: { keywords: ["咖啡豆", "耳掛咖啡"] } });
  });

  it("顯示排名分段、Google 帶到的頁面，並可把有曝光的搜尋詞設為目標", async () => {
    renderPage("?tab=keywords");
    expect(await screen.findByText("第 2 頁")).toBeInTheDocument();
    expect(screen.getByText(/1 個相關搜尋詞・曝光 400・點擊 6/)).toBeInTheDocument();
    expect(screen.getByText(/Google 帶到：/)).toBeInTheDocument();
    expect(screen.getByText("有曝光但還不是目標的搜尋詞")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "設為目標" }));
    expect(api.post).toHaveBeenCalledWith("/projects/7/seo/keywords/", { keywords: ["咖啡豆", "耳掛咖啡"] });
  });
});
