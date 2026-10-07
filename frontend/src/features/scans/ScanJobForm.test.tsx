import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
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

describe("ScanJobForm（2026-10-07 定價：首次免費、部分掃描、深度附加費）", () => {
  const full = () => project(1, "a.example");

  it("首次完整掃描免費：預扣顯示 0、不會出現點數不足", () => {
    useArgusStore.setState({
      wallet: { balance: 200, coin_per_category: 2, agent_ux_fee: 20, free_trial_available: true },
    });
    renderForm(full());
    expect(screen.getByText(/首次完整掃描免費/)).toBeInTheDocument();
    expect(screen.getByText("0 coin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /點數不足/ })).not.toBeInTheDocument();
  });

  it("點數不足時提供部分掃描，使用者確認後才改用 N 頁送出", async () => {
    const user = userEvent.setup();
    useArgusStore.setState({
      wallet: { balance: 200, coin_per_category: 2, agent_ux_fee: 20, free_trial_available: false },
    });
    vi.mocked(api.post).mockResolvedValue({ data: { id: 9 } });
    renderForm(full());
    // 200 點、每頁 10 點＋UX 20 點 → 最多 18 頁；還沒確認前不會自動縮小
    const partial = screen.getByRole("button", { name: /改為部分掃描：最多 18 頁/ });
    expect(screen.queryByText(/部分掃描：最多 18 頁，結果可能/)).not.toBeInTheDocument();
    await user.click(partial);
    expect(screen.getByText(/部分掃描：最多 18 頁，結果可能/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /我擁有此網站/ }));
    await user.click(screen.getByRole("button", { name: /建立掃描|開始掃描|送出/ }));
    expect(vi.mocked(api.post)).toHaveBeenCalledWith(
      "/scans/", expect.objectContaining({ max_pages: 18 }),
    );
  });

  it("主動＋已授權時列出深度資安附加費", async () => {
    const user = userEvent.setup();
    useArgusStore.setState({
      wallet: { balance: 2000, coin_per_category: 2, agent_ux_fee: 20, agent_deep_fee: 50 },
    });
    renderForm(full());
    await user.click(screen.getByRole("checkbox", { name: /啟用主動式資安測試/ }));
    await user.click(screen.getByRole("checkbox", { name: /同意進行侵入式測試/ }));
    expect(screen.getByText(/深度資安 AI Agent 另加 50 coin/)).toBeInTheDocument();
    expect(screen.getByText("570 coin")).toBeInTheDocument();
  });
});
