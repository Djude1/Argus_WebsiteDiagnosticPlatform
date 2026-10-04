import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { WorkspaceShell } from "./ProjectWorkspace";

vi.mock("../../api", () => ({
  api: { get: vi.fn().mockResolvedValue({ data: { subscription: null } }) },
  fetchVerifiedDomains: vi.fn(),
}));

beforeEach(() => {
  useArgusStore.setState({ projects: [], fetchProjects: vi.fn(), wallet: null });
});

describe("側邊欄的帳號工具（網域驗證、MCP 接入不藏在頭像選單）", () => {
  it("沒有網站專案也看得到兩個入口，目前頁標示為 current", () => {
    render(
      <MemoryRouter>
        <WorkspaceShell activeTool="domains"><p>內容</p></WorkspaceShell>
      </MemoryRouter>,
    );
    const domains = screen.getByRole("link", { name: /網域驗證/ });
    expect(domains).toHaveAttribute("href", "/domains");
    expect(domains).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /MCP 接入/ })).toHaveAttribute("href", "/mcp");
    expect(screen.getByText("內容")).toBeInTheDocument();
  });

  it("有專案時同時顯示專案分頁與帳號工具", () => {
    useArgusStore.setState({
      projects: [{ id: 3, name: "示範商店", origin: "https://shop.example.tw", hostname: "shop.example.tw", summary: {} }],
      currentProjectId: 3,
    });
    render(
      <MemoryRouter>
        <WorkspaceShell activeTool="domains"><p>內容</p></WorkspaceShell>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /^總覽/ })).toHaveAttribute("href", "/projects/3");
    expect(screen.getByRole("link", { name: /^總覽/ })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: /MCP 接入/ })).toBeInTheDocument();
  });
});
