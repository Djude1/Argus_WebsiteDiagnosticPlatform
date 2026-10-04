import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { DomainVerifyPage } from "./DomainVerifyPage";

vi.mock("../../api", () => ({
  createVerifiedDomain: vi.fn(),
  deleteVerifiedDomain: vi.fn(),
  fetchVerifiedDomains: vi.fn(),
  verifyVerifiedDomain: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

const PENDING = {
  id: 5, domain: "example.tw", status: "pending", method: "", is_effectively_verified: false,
  admin_override: false, expires_at: null, last_checked_at: null, last_error: "",
};

beforeEach(() => {
  vi.clearAllMocks();
  useArgusStore.setState({
    projects: [{ id: 9, name: "示範商店", origin: "https://shop.example.tw" }],
    fetchProjects: vi.fn(),
  });
  api.fetchVerifiedDomains.mockResolvedValue({ results: [PENDING] });
});

describe("DomainVerifyPage（Search Console 為主要驗證方式）", () => {
  it("預設用 Search Console 驗證，並連到對應專案的 SEO 分析頁", async () => {
    const user = userEvent.setup();
    api.verifyVerifiedDomain.mockResolvedValue({ ...PENDING, verified: true, is_effectively_verified: true });
    render(<MemoryRouter><DomainVerifyPage /></MemoryRouter>);

    const link = await screen.findByRole("link", { name: /示範商店.*連接 Search Console/ });
    expect(link).toHaveAttribute("href", "/projects/9/seo?tab=keywords");
    expect(screen.getByRole("button", { name: "Search Console（建議）" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "驗證" }));
    expect(api.verifyVerifiedDomain).toHaveBeenCalledWith(5, "search_console");
  });

  it("舊方法仍可選用", async () => {
    const user = userEvent.setup();
    api.verifyVerifiedDomain.mockResolvedValue({ ...PENDING, verified: false, last_error: "找不到" });
    render(<MemoryRouter><DomainVerifyPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: "DNS TXT" }));
    await user.click(screen.getByRole("button", { name: "驗證" }));
    expect(api.verifyVerifiedDomain).toHaveBeenCalledWith(5, "dns_txt");
  });
});
