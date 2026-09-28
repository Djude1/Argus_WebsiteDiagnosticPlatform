import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { McpAccessPage } from "./McpAccessPage";

vi.mock("../../api", () => ({
  api: {},
  setAccessToken: vi.fn(),
  fetchMcpOverview: vi.fn(),
  createMcpKey: vi.fn(),
  revokeMcpKey: vi.fn(),
  checkMcpConnection: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

const ENDPOINT = "https://argus.example/api/mcp/";

function overview(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    endpoint_url: ENDPOINT,
    max_keys: 5,
    rate_per_minute: 60,
    keys: [],
    recent_calls: [],
    tools: [
      { name: "create_scan", title: "建立掃描", description: "建立網站健檢", read_only: false },
      { name: "get_scan", title: "掃描狀態與分數", description: "查詢狀態", read_only: true },
    ],
    entitlement: {
      allowed: true, reason: "", plan_code: "sub-pro", plan_name: "專業訂閱",
      subscription_status: "active", paid_through: "2026-10-28T00:00:00Z",
      monthly_quota: 1500, used_this_month: 12, remaining_this_month: 1488,
      period_start: "2026-09-01T00:00:00+08:00", period_end: "2026-10-01T00:00:00+08:00",
    },
    ...overrides,
  };
}

function renderPage() {
  return render(<MemoryRouter><McpAccessPage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchMcpOverview.mockResolvedValue(overview());
});

describe("McpAccessPage", () => {
  it("沒有有效訂閱時引導訂閱，且不能建立憑證", async () => {
    api.fetchMcpOverview.mockResolvedValue(overview({
      entitlement: {
        ...overview().entitlement, allowed: false, plan_name: "",
        reason: "MCP 接入限有效訂閱會員使用，請先到購點頁訂閱方案。",
      },
    }));
    renderPage();
    expect(await screen.findByRole("link", { name: "前往訂閱方案" })).toHaveAttribute("href", "/billing");
    expect(screen.getByRole("button", { name: "建立憑證" })).toBeDisabled();
  });

  it("建立憑證後明文只顯示在本頁，並自動帶入所選工具的設定", async () => {
    const user = userEvent.setup();
    api.createMcpKey.mockResolvedValue({
      key: { id: 7, name: "Claude Code", prefix: "argus_mcp_abcd", is_active: true },
      secret: "argus_mcp_abcdSECRET",
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "建立憑證" }));
    expect(api.createMcpKey).toHaveBeenCalledWith("Claude Code");
    expect(await screen.findByText(/只會顯示這一次/)).toBeInTheDocument();
    expect(screen.getByText(/claude mcp add --transport http argus/).textContent)
      .toContain("Bearer argus_mcp_abcdSECRET");

    await user.click(screen.getByRole("tab", { name: "Codex" }));
    const codex = screen.getByText(/codex mcp add argus/).textContent || "";
    expect(codex).toContain(`--url ${ENDPOINT}`);
    expect(codex).toContain('ARGUS_MCP_TOKEN="argus_mcp_abcdSECRET"');
  });

  it("未建立憑證時設定使用佔位字，不會出現任何憑證", async () => {
    renderPage();
    expect((await screen.findByText(/claude mcp add/)).textContent).toContain("<你的 Argus MCP 憑證>");
  });

  it("撤銷前要二次確認，取消就不呼叫 API", async () => {
    const user = userEvent.setup();
    api.fetchMcpOverview.mockResolvedValue(overview({
      keys: [{ id: 3, name: "筆電", prefix: "argus_mcp_wxyz", is_active: true,
        created_at: "2026-09-20T00:00:00Z", last_used_at: null, last_client: "", revoked_at: null }],
    }));
    renderPage();
    const row = (await screen.findByText("筆電")).closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "撤銷" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(api.revokeMcpKey).not.toHaveBeenCalled();

    await user.click(within(row).getByRole("button", { name: "撤銷" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "確定" }));
    await waitFor(() => expect(api.revokeMcpKey).toHaveBeenCalledWith(3));
  });

  it("驗證連線：收到工具呼叫後顯示成功", async () => {
    const user = userEvent.setup();
    api.checkMcpConnection.mockResolvedValue({
      connected: true, tool_called: true,
      calls: [{ id: 1, method: "initialize", detail: "claude-code 2.1" }],
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "開始驗證連線" }));
    expect(await screen.findByText(/連線成功，已收到工具呼叫（claude-code 2.1）/)).toBeInTheDocument();
  });
});
