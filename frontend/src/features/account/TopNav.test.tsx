import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { TopNav } from "./TopNav";

vi.mock("../../api", () => ({ api: { get: vi.fn().mockResolvedValue({ data: [] }) }, setAccessToken: vi.fn() }));

beforeEach(() => {
  useArgusStore.setState({ accessToken: "t", projects: [], currentProjectId: null });
});

describe("TopNav 帳號工具", () => {
  it("網域驗證與 MCP 接入直接在頂部導覽列，目前頁標示 aria-current", () => {
    render(
      <MemoryRouter initialEntries={["/domains"]}>
        <TopNav />
      </MemoryRouter>,
    );
    const domains = screen.getByRole("link", { name: "網域驗證" });
    const mcp = screen.getByRole("link", { name: "MCP 接入" });
    expect(domains).toHaveAttribute("href", "/domains");
    expect(domains).toHaveAttribute("aria-current", "page");
    expect(mcp).toHaveAttribute("href", "/mcp");
    expect(mcp).not.toHaveAttribute("aria-current");
  });
});
