import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectWorkspace } from "./ProjectWorkspace";
import { useArgusStore } from "../../store";

vi.mock("../../api", () => ({ api: { get: vi.fn() }, setAccessToken: vi.fn(), fetchVerifiedDomains: vi.fn() }));
const { api } = await import("../../api");

beforeEach(() => {
  useArgusStore.setState({ wallet: { balance: 100 }, projects: [], currentProjectId: 1 });
  api.get.mockImplementation(async (path) => ({ data: path === "/projects/1/"
    ? { id: 1, name: "測試網站", hostname: "example.com", origin: "https://example.com", summary: {} }
    : { subscription: null } }));
});

function renderWorkspace() {
  return render(<MemoryRouter initialEntries={["/projects/1"]}>
    <Routes><Route path="/projects/:projectId" element={<ProjectWorkspace />}>
      <Route index element={<p>總覽內容</p>} />
      <Route path="seo" element={<p>SEO 內容</p>} />
    </Route></Routes>
  </MemoryRouter>);
}

describe("專案行動功能選單", () => {
  it("可展開、切換分頁，並收合回目前分頁名稱", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    const toggle = await screen.findByRole("button", { name: /總覽.*切換分頁/ });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const sidebar = screen.getByRole("complementary", { name: "網站專案功能" });
    await user.click(within(sidebar).getByRole("link", { name: /SEO 分析/ }));
    expect(await screen.findByText("SEO 內容")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAccessibleName(/SEO 分析.*切換分頁/);
  });

  it("Escape 收合並保留可繼續操作的焦點", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    const toggle = await screen.findByRole("button", { name: /總覽.*切換分頁/ });
    await user.click(toggle);
    screen.getByRole("link", { name: /SEO 分析/ }).focus();
    await user.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
  });
});
