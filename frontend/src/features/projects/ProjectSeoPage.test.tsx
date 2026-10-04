import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectSeoPage } from "./ProjectSeoPage";

vi.mock("../../api", () => ({ api: { get: vi.fn() }, setAccessToken: vi.fn() }));
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
