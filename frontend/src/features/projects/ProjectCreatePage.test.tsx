import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { ProjectCreatePage, parseSiteUrl } from "./ProjectWorkspace";

// 新增專案頁的承諾：網址即時預覽網站與同網站專案、預設掃描設定一起送出、
// 主動測試自動帶上資安維度、依「建立之後」導到掃描或總覽、預估點數跟著設定變。

vi.mock("../../api", () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  fetchVerifiedDomains: vi.fn(async () => ({ results: [{ domain: "verified.example.com", is_effectively_verified: true }] })),
  setAccessToken: vi.fn(),
}));
const { api } = vi.mocked(await import("../../api"));

function Location() {
  return <p data-testid="location">{useLocation().pathname}</p>;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/projects/new"]}>
      <Routes>
        <Route path="/projects/new" element={<ProjectCreatePage />} />
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useArgusStore.setState({
    accessToken: "t",
    wallet: { balance: 1000, coin_per_category: 2 },
    fetchWallet: vi.fn(),
    projects: [{ id: 3, name: "舊專案", origin: "https://old.example.com", hostname: "old.example.com" }],
  } as never);
});

describe("parseSiteUrl", () => {
  it("沒打協定時補 https，取出網站 origin；不是網址回 null", () => {
    expect(parseSiteUrl("shop.example.com/a?b=1")).toMatchObject({ origin: "https://shop.example.com", hostname: "shop.example.com" });
    expect(parseSiteUrl("http://Example.com:8080/")?.origin).toBe("http://example.com:8080");
    expect(parseSiteUrl("not a url")).toBeNull();
    expect(parseSiteUrl("")).toBeNull();
  });
});

describe("ProjectCreatePage", () => {
  it("送出網址、說明與預設掃描設定，建立後前往掃描分頁", async () => {
    api.post.mockResolvedValue({ data: { id: 9, name: "官網", origin: "https://verified.example.com" } } as never);
    const user = userEvent.setup();
    renderPage();
    const submit = screen.getByRole("button", { name: "建立專案並前往掃描" });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/網站網址/), "verified.example.com");
    await user.type(screen.getByLabelText("專案名稱"), "官網");
    await user.type(screen.getByLabelText(/^專案說明/), "公司官網");
    await user.click(screen.getByLabelText(/單一頁面/));
    await user.click(screen.getByLabelText(/^UX/));
    await waitFor(() => expect(screen.getByText("已驗證，可做主動測試")).toBeInTheDocument());
    // 單頁 × 4 維 × 2 coin
    expect(screen.getByText("最多 8 coin")).toBeInTheDocument();

    await user.click(submit);
    expect(api.post).toHaveBeenCalledWith("/projects/", {
      start_url: "verified.example.com",
      name: "官網",
      description: "公司官網",
      default_scope: "single",
      default_categories: ["seo", "aeo", "geo", "security"],
      default_scan_mode: "passive",
    });
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/9/scans");
  });

  it("選主動測試時自動勾上資安且不能取消；選「先到專案總覽」就導到總覽", async () => {
    api.post.mockResolvedValue({ data: { id: 11, name: "x", origin: "https://a.example.com" } } as never);
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/網站網址/), "https://a.example.com/");
    await user.click(screen.getByLabelText(/^資安/));
    expect(screen.getByLabelText(/^資安/)).not.toBeChecked();
    await user.click(screen.getByLabelText(/主動測試/));
    expect(screen.getByLabelText(/^資安/)).toBeChecked();
    expect(screen.getByLabelText(/^資安/)).toBeDisabled();
    expect(await screen.findByText(/a\.example\.com 尚未完成網域驗證/)).toBeInTheDocument();

    await user.click(screen.getByLabelText(/先到專案總覽/));
    await user.click(screen.getByRole("button", { name: "建立專案" }));
    expect(api.post.mock.calls[0]?.[1]).toMatchObject({ default_scan_mode: "active", default_categories: ["seo", "aeo", "geo", "ux", "security"] });
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/11");
  });

  it("同網站已有專案時提示並不能送出；餘額不夠掃整站時提示", async () => {
    useArgusStore.setState({ wallet: { balance: 100, coin_per_category: 2 } } as never);
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/網站網址/), "https://old.example.com/blog");
    expect(screen.getByText(/已經是你的專案「舊專案」/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "建立專案並前往掃描" })).toBeDisabled();
    expect(screen.getByText(/目前餘額不足以用這組預設掃描整個網站/)).toBeInTheDocument();
  });
});
