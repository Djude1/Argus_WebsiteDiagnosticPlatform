import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { ScanJobForm } from "./ScanExperience";

vi.mock("../../api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
  setAccessToken: vi.fn(),
  fetchVerifiedDomains: vi.fn().mockResolvedValue({ results: [] }),
}));

function project(id: number, host: string, overrides: Record<string, unknown> = {}) {
  return {
    id, name: host, origin: `https://${host}`, hostname: host, start_url: `https://${host}/start`,
    default_scope: "site", default_categories: ["seo", "aeo", "geo", "ux", "security"], ...overrides,
  };
}

function renderForm(p: ReturnType<typeof project>) {
  return render(<MemoryRouter><ScanJobForm project={p} onCreated={vi.fn()} /></MemoryRouter>);
}

beforeEach(() => {
  localStorage.clear();
  useArgusStore.setState({ accessToken: "t", wallet: { balance: 1000, coin_per_category: 2, agent_ux_fee: 0 } });
});

describe("ScanJobForm（網站專案）", () => {
  it("以專案的起始網址、預設範圍與維度為初始值", () => {
    renderForm(project(1, "a.example", { default_scope: "single", default_categories: ["seo", "security"] }));
    expect(screen.getByRole("textbox", { name: /目標網址|網址/ })).toHaveValue("https://a.example/start");
    expect(screen.getByRole("button", { name: /單一頁面/ })).toHaveClass("active");
    expect(screen.getByText(/已選 2 維/)).toBeInTheDocument();
  });

  it("草稿按專案分開：A 網站沒送出的修改不會帶到 B 網站", async () => {
    const user = userEvent.setup();
    const { unmount } = renderForm(project(1, "a.example"));
    const input = screen.getByRole("textbox", { name: /目標網址|網址/ });
    await user.clear(input);
    await user.type(input, "https://a.example/draft");
    unmount();
    renderForm(project(2, "b.example")).unmount();
    expect(localStorage.getItem("argus_scan_draft_v1:project-2")).toContain("https://b.example/start");
    renderForm(project(1, "a.example"));
    expect(screen.getByRole("textbox", { name: /目標網址|網址/ })).toHaveValue("https://a.example/draft");
  });
});
