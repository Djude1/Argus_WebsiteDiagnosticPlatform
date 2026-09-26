import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminVerifiedDomain } from "../../shared/apiContracts";
import { AdminDomainsPage } from "./AdminDomainsPage";

// 人工核准等同驗證通過、會直接開放主動式測試，所以核准與否決都必須先確認。

vi.mock("../../api", () => ({
  fetchAdminDomains: vi.fn(),
  adminDomainOverride: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

function domain(overrides: Partial<AdminVerifiedDomain> = {}): AdminVerifiedDomain {
  return {
    id: 3, username: "alice", domain: "example.org",
    status: "pending", status_label: "待驗證", method: "", method_label: "",
    verified_at: null, expires_at: null, last_checked_at: null, last_error: "",
    admin_override: false, admin_actor_username: null, admin_note: "",
    is_effectively_verified: false, created_at: "2026-09-20T00:00:00Z",
    ...overrides,
  };
}

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/admin/domains" element={<AdminDomainsPage />} /></Routes>
      <Location />
    </MemoryRouter>,
  );
}

const lastCall = () => api.fetchAdminDomains.mock.calls.at(-1)?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchAdminDomains.mockResolvedValue({ domains: [domain()], page: 1, total_pages: 1, total: 1 });
});

describe("AdminDomainsPage", () => {
  it("篩選條件在網址上——重新整理或從別頁連過來都能還原（原本存在元件 state）", async () => {
    renderAt("/admin/domains?status=pending&q=example");
    await screen.findByText("example.org");
    expect(lastCall()).toMatchObject({ status: "pending", q: "example" });
    expect(screen.getByRole("combobox", { name: "驗證狀態" })).toHaveValue("pending");
  });

  it("切換狀態會寫進網址並重新載入", async () => {
    const user = userEvent.setup();
    renderAt("/admin/domains");
    await user.selectOptions(await screen.findByRole("combobox", { name: "驗證狀態" }), "rejected");
    expect(screen.getByTestId("location")).toHaveTextContent("status=rejected");
    await waitFor(() => expect(lastCall()?.status).toBe("rejected"));
  });

  it("不認得的狀態不送出", async () => {
    renderAt("/admin/domains?status=approved");
    await screen.findByText("example.org");
    expect(lastCall()?.status).toBeUndefined();
  });

  it("載入失敗顯示錯誤與重試（原本停在「載入中…」）", async () => {
    const user = userEvent.setup();
    api.fetchAdminDomains.mockRejectedValueOnce(new Error("Network Error"));
    renderAt("/admin/domains");
    expect(await screen.findByRole("alert")).toHaveTextContent("Network Error");
    await user.click(screen.getByRole("button", { name: "重試" }));
    expect(await screen.findByText("example.org")).toBeInTheDocument();
  });

  it("人工核准要先確認；取消確認就不送出", async () => {
    const user = userEvent.setup();
    renderAt("/admin/domains");
    await user.click(await screen.findByRole("button", { name: "人工核准" }));
    await user.click(await screen.findByRole("button", { name: "取消" }));
    expect(api.adminDomainOverride).not.toHaveBeenCalled();
  });

  it("確認核准後送出備註，並原地更新該列、清空備註（不重新載入整頁）", async () => {
    const user = userEvent.setup();
    api.adminDomainOverride.mockResolvedValue(domain({
      status: "verified", status_label: "已驗證", admin_override: true,
      admin_actor_username: "root", admin_note: "人工確認", is_effectively_verified: true,
    }));
    renderAt("/admin/domains");

    const note = await screen.findByRole("textbox", { name: "example.org 審核備註" });
    await user.type(note, " 人工確認 ");
    await user.click(screen.getByRole("button", { name: "人工核准" }));
    await user.click(await screen.findByRole("button", { name: "確定" }));

    expect(api.adminDomainOverride).toHaveBeenCalledWith(3, true, "人工確認");
    const row = (await screen.findByText("生效中")).closest("tr")!;
    expect(within(row).getByText("已驗證")).toBeInTheDocument();
    expect(note).toHaveValue("");
    expect(api.fetchAdminDomains).toHaveBeenCalledTimes(1);
  });

  it("否決走危險樣式的確認，送出 approve=false", async () => {
    const user = userEvent.setup();
    api.adminDomainOverride.mockResolvedValue(domain({ status: "rejected", status_label: "已否決" }));
    renderAt("/admin/domains");
    await user.click(await screen.findByRole("button", { name: "否決" }));
    const confirm = await screen.findByRole("button", { name: "確定" });
    expect(confirm).toHaveClass("danger");
    await user.click(confirm);
    expect(api.adminDomainOverride).toHaveBeenCalledWith(3, false, "");
  });
});
