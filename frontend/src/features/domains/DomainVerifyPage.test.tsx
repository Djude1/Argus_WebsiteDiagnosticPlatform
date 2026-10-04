import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DomainVerifyPage } from "./DomainVerifyPage";

vi.mock("../../api", () => ({
  connectDomainSearchConsole: vi.fn(),
  createVerifiedDomain: vi.fn(),
  deleteVerifiedDomain: vi.fn(),
  disconnectDomainSearchConsole: vi.fn(),
  fetchDomainSearchConsole: vi.fn(),
  fetchVerifiedDomain: vi.fn(),
  fetchVerifiedDomains: vi.fn(),
  syncDomainSearchConsole: vi.fn(),
  verifyVerifiedDomain: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

const PENDING = {
  id: 5, domain: "example.tw", status: "pending", method: "", is_effectively_verified: false,
  admin_override: false, expires_at: null, last_checked_at: null, last_error: "",
};
const NOT_CONNECTED = { enabled: true, connected: false, account_connection: false, needs_reconnect: false };
const CONNECTED = { ...NOT_CONNECTED, connected: true, account_connection: true };

function renderPage(path = "/domains") {
  return render(<MemoryRouter initialEntries={[path]}><DomainVerifyPage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchVerifiedDomains.mockResolvedValue({ results: [PENDING] });
  api.fetchDomainSearchConsole.mockResolvedValue(NOT_CONNECTED);
});

describe("DomainVerifyPage（Search Console 一鍵驗證）", () => {
  it("未連接時在本頁直接連接 Search Console（前往 Google 授權）", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    api.connectDomainSearchConsole.mockResolvedValue({ authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "連接 Google Search Console" }));
    expect(assign).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?x=1");
    vi.unstubAllGlobals();
  });

  it("已連接時每個待驗證網域可直接用 Search Console 驗證", async () => {
    const user = userEvent.setup();
    api.fetchDomainSearchConsole.mockResolvedValue(CONNECTED);
    api.verifyVerifiedDomain.mockResolvedValue({ ...PENDING, verified: true, is_effectively_verified: true });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "用 Search Console 驗證" }));
    expect(api.verifyVerifiedDomain).toHaveBeenCalledWith(5, "search_console");
    expect(await screen.findByText(/驗證成功/)).toBeInTheDocument();
  });

  it("Google 導回後顯示自動驗證的網域數", async () => {
    renderPage("/domains?gsc=connected&verified=3");
    expect(await screen.findByText("已連接 Search Console，3 個網域已自動通過驗證。")).toBeInTheDocument();
  });

  it("其他驗證方式：展開後載入設定說明，可用 DNS TXT 驗證", async () => {
    const user = userEvent.setup();
    api.fetchVerifiedDomain.mockResolvedValue({
      ...PENDING, token: "t".repeat(32),
      instructions: { dns_txt: { record_name: "_argus-verification.example.tw", record_type: "TXT", value: "argus-site-verification=ttt" } },
    });
    api.verifyVerifiedDomain.mockResolvedValue({ ...PENDING, verified: false, last_error: "找不到 TXT" });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "其他驗證方式" }));
    expect(await screen.findByText("_argus-verification.example.tw")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "以 DNS TXT 驗證" }));
    expect(api.verifyVerifiedDomain).toHaveBeenCalledWith(5, "dns_txt");
    expect(await screen.findByText("找不到 TXT")).toBeInTheDocument();
  });
});
