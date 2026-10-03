import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { CommandSearch } from "./CommandSearch";
import { NotificationBell } from "./NotificationBell";

vi.mock("../../api", () => ({ api: { get: vi.fn() }, setAccessToken: vi.fn() }));
const { api } = vi.mocked(await import("../../api"));

function project(id: number, name: string) {
  return { id, name, origin: `https://${name}`, hostname: name, start_url: `https://${name}/`, archived_at: null, summary: {} };
}

function Location() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  useArgusStore.setState({ accessToken: "t", projects: [project(1, "a.example"), project(2, "b.example")], currentProjectId: 1 });
});

describe("CommandSearch", () => {
  function renderSearch() {
    return render(
      <MemoryRouter initialEntries={["/projects/1"]}>
        <CommandSearch />
        <Routes>
          <Route path="*" element={<Location />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it("Ctrl+K 打開，關鍵字可找到目前網站的問題，Enter 前往問題分析並帶 ?q=", async () => {
    api.get.mockResolvedValue({
      data: { issues: [{ key: "k1", title: "缺少 CSP", severity: "medium", category: "security", remediation: "設定 header" }] },
    } as never);
    const user = userEvent.setup();
    renderSearch();
    await user.keyboard("{Control>}k{/Control}");
    const input = screen.getByRole("combobox");
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/projects/1/issues/"));
    await user.type(input, "csp");
    expect(await screen.findByRole("option", { name: /缺少 CSP/ })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(`/projects/1/issues?q=${encodeURIComponent("缺少 CSP")}`);
  });

  it("可搜尋其他網站專案與目前網站的分頁，找不到時顯示提示，Esc 關閉", async () => {
    api.get.mockResolvedValue({ data: { issues: [] } } as never);
    const user = userEvent.setup();
    renderSearch();
    await user.click(screen.getByRole("button", { name: "搜尋專案、問題或建議" }));
    await user.type(screen.getByRole("combobox"), "b.ex");
    expect(screen.getByRole("option", { name: /b\.example/ })).toBeInTheDocument();
    await user.clear(screen.getByRole("combobox"));
    await user.type(screen.getByRole("combobox"), "歷史");
    await user.click(screen.getByRole("option", { name: "歷史報告" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/1/history");
    await user.click(screen.getByRole("button", { name: "搜尋專案、問題或建議" }));
    await user.type(screen.getByRole("combobox"), "zzz");
    expect(screen.getByText(/找不到符合/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("NotificationBell", () => {
  const ANNOUNCEMENTS = [
    { id: 7, title: "維護通知", content: "週六維護", type: "info", created_at: "2026-10-01T00:00:00Z" },
    { id: 8, title: "新功能", content: "AEO 問答", type: "info", created_at: "2026-10-02T00:00:00Z" },
  ];

  it("有未讀公告時顯示數量，全部標為已讀後寫入 localStorage", async () => {
    localStorage.setItem("ann_dismissed_7", "1");
    api.get.mockResolvedValue({ data: { announcements: ANNOUNCEMENTS } } as never);
    const user = userEvent.setup();
    render(<NotificationBell />);
    const bell = await screen.findByRole("button", { name: "通知（1 則未讀）" });
    await user.click(bell);
    expect(screen.getByRole("dialog", { name: "通知" })).toHaveTextContent("新功能");
    await user.click(screen.getByRole("button", { name: "全部標為已讀" }));
    expect(localStorage.getItem("ann_dismissed_8")).toBe("1");
    expect(screen.getByRole("button", { name: "通知" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("沒有公告時顯示空狀態", async () => {
    api.get.mockResolvedValue({ data: { announcements: [] } } as never);
    const user = userEvent.setup();
    render(<NotificationBell />);
    await user.click(screen.getByRole("button", { name: "通知" }));
    expect(screen.getByText("目前沒有公告。")).toBeInTheDocument();
  });
});
