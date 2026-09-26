import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminAuditLog } from "../../shared/apiContracts";
import { useArgusStore } from "../../store";
import { AdminAuditLogPage } from "./AdminAuditLogPage";

vi.mock("../../api", () => ({
  api: {},
  setAccessToken: vi.fn(),
  fetchAdminAuditLog: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

function log(overrides: Partial<AdminAuditLog> = {}): AdminAuditLog {
  return {
    id: 1, created_at: "2026-09-26T00:00:00Z", action: "scan_control", action_label: "掃描任務控制",
    actor_username: "root", target_username: "alice", target_object_repr: "Scan #42", payload: {},
    ...overrides,
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/admin/audit-log" element={<AdminAuditLogPage />} /></Routes>
    </MemoryRouter>,
  );
}

const lastCall = () => api.fetchAdminAuditLog.mock.calls.at(-1)?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  useArgusStore.setState({ me: { is_superuser: true } });
  api.fetchAdminAuditLog.mockResolvedValue({ logs: [log()], page: 1, total_pages: 1, total: 1 });
});

describe("AdminAuditLogPage", () => {
  it("非超級管理員看不到，也不打 API", () => {
    useArgusStore.setState({ me: { is_superuser: false } });
    renderAt("/admin/audit-log");
    expect(screen.getByText("需要超級管理員權限才能查看。")).toBeInTheDocument();
    expect(api.fetchAdminAuditLog).not.toHaveBeenCalled();
  });

  it("動作篩選涵蓋後端全部 9 種，含原本漏掉的掃描控制／網域審核／調整訂閱", async () => {
    renderAt("/admin/audit-log");
    const select = await screen.findByRole("combobox", { name: "稽核動作" });
    const values = within(select).getAllByRole("option").map((o) => (o as HTMLOptionElement).value).filter(Boolean);
    expect(values).toHaveLength(9);
    expect(values).toEqual(expect.arrayContaining(["scan_control", "domain_override", "subscription_adjust"]));
  });

  it("?action= 從網址還原並送出；不認得的值不送", async () => {
    const { unmount } = renderAt("/admin/audit-log?action=scan_control");
    await screen.findByText("Scan #42");
    expect(lastCall()).toMatchObject({ action: "scan_control" });
    unmount();

    renderAt("/admin/audit-log?action=delete_everything");
    await screen.findByText("Scan #42");
    expect(lastCall()?.action).toBeUndefined();
  });

  it("切換動作後重新載入", async () => {
    const user = userEvent.setup();
    renderAt("/admin/audit-log");
    await user.selectOptions(await screen.findByRole("combobox", { name: "稽核動作" }), "domain_override");
    await waitFor(() => expect(lastCall()?.action).toBe("domain_override"));
  });

  it("載入失敗顯示錯誤與重試（原本停在「載入中…」）", async () => {
    const user = userEvent.setup();
    api.fetchAdminAuditLog.mockRejectedValueOnce(new Error("Network Error"));
    renderAt("/admin/audit-log");
    expect(await screen.findByRole("alert")).toHaveTextContent("Network Error");
    await user.click(screen.getByRole("button", { name: "重試" }));
    expect(await screen.findByText("Scan #42")).toBeInTheDocument();
  });

  it("payload 非空時才提供展開", async () => {
    api.fetchAdminAuditLog.mockResolvedValue({
      logs: [
        log({ id: 1, target_object_repr: "無 payload" }),
        log({ id: 2, target_object_repr: "有 payload", payload: { operation: "requeue", charged: 0 } }),
      ],
      page: 1, total_pages: 1, total: 2,
    });
    renderAt("/admin/audit-log");
    await screen.findByText("有 payload");
    expect(screen.getAllByText("payload")).toHaveLength(1);
    expect(screen.getByText(/"operation": "requeue"/)).toBeInTheDocument();
  });

  it("操作者已刪除時明確標示", async () => {
    api.fetchAdminAuditLog.mockResolvedValue({
      logs: [log({ actor_username: null })], page: 1, total_pages: 1, total: 1,
    });
    renderAt("/admin/audit-log");
    expect(await screen.findByText("(已刪除)")).toBeInTheDocument();
  });
});
