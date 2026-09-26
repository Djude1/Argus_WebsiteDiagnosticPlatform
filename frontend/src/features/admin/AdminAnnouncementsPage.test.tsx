import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Announcement } from "../../shared/apiContracts";
import { useArgusStore } from "../../store";
import { AdminAnnouncementsPage } from "./AdminAnnouncementsPage";

vi.mock("../../api", () => ({
  api: {},
  setAccessToken: vi.fn(),
  fetchAdminAnnouncements: vi.fn(),
  createAnnouncement: vi.fn(),
  updateAnnouncement: vi.fn(),
  deleteAnnouncement: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

function ann(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: 5, title: "系統維護", content: "今晚十點維護", type: "temporary",
    active_days: 3, is_active: true, created_at: "2026-09-26T00:00:00Z",
    ...overrides,
  };
}

/** DRF 400 驗證錯誤的形狀 */
const validationError = (fields: Record<string, string[]>) => ({ response: { status: 400, data: fields } });

beforeEach(() => {
  vi.clearAllMocks();
  useArgusStore.setState({ me: { is_superuser: true } });
  api.fetchAdminAnnouncements.mockResolvedValue({ announcements: [ann()] });
});

describe("AdminAnnouncementsPage", () => {
  it("非超級管理員看不到，也不打 API", () => {
    useArgusStore.setState({ me: { is_superuser: false } });
    render(<AdminAnnouncementsPage />);
    expect(screen.getByText("需要超級管理員權限才能查看。")).toBeInTheDocument();
    expect(api.fetchAdminAnnouncements).not.toHaveBeenCalled();
  });

  it("載入失敗顯示錯誤與重試，而不是誤報「尚無公告」", async () => {
    const user = userEvent.setup();
    api.fetchAdminAnnouncements.mockRejectedValueOnce(new Error("Network Error"));
    render(<AdminAnnouncementsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Network Error");
    expect(screen.queryByText("尚無公告")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重試" }));
    expect(await screen.findByText("系統維護")).toBeInTheDocument();
  });

  it("新增：送出表單內容，成功後關閉並重新載入", async () => {
    const user = userEvent.setup();
    api.createAnnouncement.mockResolvedValue(ann({ id: 6 }));
    render(<AdminAnnouncementsPage />);
    await user.click(await screen.findByRole("button", { name: "＋ 新增公告" }));
    await user.type(screen.getByLabelText(/標題/), "新功能上線");
    await user.type(screen.getByLabelText(/內容/), "歡迎試用");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(api.createAnnouncement).toHaveBeenCalledWith({
      title: "新功能上線", content: "歡迎試用", type: "temporary", active_days: 7, is_active: true,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.fetchAdminAnnouncements).toHaveBeenCalledTimes(2);
  });

  it("儲存遇到驗證錯誤：錯誤顯示在欄位旁、彈窗留著、內容不會丟（原本毫無反應）", async () => {
    const user = userEvent.setup();
    api.createAnnouncement.mockRejectedValue(validationError({ title: ["此欄位不可為空白。"] }));
    render(<AdminAnnouncementsPage />);
    await user.click(await screen.findByRole("button", { name: "＋ 新增公告" }));
    await user.type(screen.getByLabelText(/內容/), "已經打好的內容");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(await screen.findByText("此欄位不可為空白。")).toBeInTheDocument();
    expect(screen.getByLabelText(/標題/)).toHaveAccessibleDescription("此欄位不可為空白。");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/內容/)).toHaveValue("已經打好的內容");
  });

  it("儲存遇到非欄位錯誤（網路等）：在彈窗內顯示整體訊息", async () => {
    const user = userEvent.setup();
    api.updateAnnouncement.mockRejectedValue(new Error("Network Error"));
    render(<AdminAnnouncementsPage />);
    await user.click(await screen.findByRole("button", { name: "編輯" }));
    await user.click(screen.getByRole("button", { name: "儲存" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network Error");
    expect(api.updateAnnouncement).toHaveBeenCalledWith(5, expect.objectContaining({ title: "系統維護" }));
  });

  it("重新開啟編輯時清掉上一次的錯誤", async () => {
    const user = userEvent.setup();
    api.createAnnouncement.mockRejectedValue(validationError({ title: ["此欄位不可為空白。"] }));
    render(<AdminAnnouncementsPage />);
    await user.click(await screen.findByRole("button", { name: "＋ 新增公告" }));
    await user.click(screen.getByRole("button", { name: "儲存" }));
    await screen.findByText("此欄位不可為空白。");
    await user.click(screen.getByRole("button", { name: "取消" }));
    await user.click(screen.getByRole("button", { name: "＋ 新增公告" }));
    expect(screen.queryByText("此欄位不可為空白。")).not.toBeInTheDocument();
  });

  it("刪除要先確認；失敗時提示（原本無聲無息）", async () => {
    const user = userEvent.setup();
    api.deleteAnnouncement.mockRejectedValue(new Error("boom"));
    render(<AdminAnnouncementsPage />);
    await user.click(await screen.findByRole("button", { name: "刪除" }));
    expect(api.deleteAnnouncement).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: "確定" }));
    expect(api.deleteAnnouncement).toHaveBeenCalledWith(5);
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});
