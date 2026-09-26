import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminReview, AdminReviewListResponse } from "../../shared/apiContracts";
import { AdminReviewsPage } from "./AdminReviewsPage";
import { AdminTransactionsPage } from "./AdminTransactionsPage";

vi.mock("../../api", () => ({
  fetchAdminTransactions: vi.fn(),
  fetchAdminReviews: vi.fn(),
  adminReplyReview: vi.fn(),
  adminDeleteReviewReply: vi.fn(),
  adminModerateReview: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/transactions" element={<AdminTransactionsPage />} />
        <Route path="/admin/reviews" element={<AdminReviewsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function review(overrides: Partial<AdminReview> = {}): AdminReview {
  return {
    id: 1, username: "alice", full_name: "Alice Chen", rating: 4, title: "", comment: "不錯",
    show_partial_email: false, status: "published", response: null,
    report_count: 0, pending_report_count: 0, response_report_count: 0,
    response_pending_report_count: 0, is_pending: true,
    created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
    ...overrides,
  };
}

function reviewList(reviews: AdminReview[]): AdminReviewListResponse {
  return {
    reviews, page: 1, total_pages: 1, total: reviews.length,
    overall_total: reviews.length, avg_rating: 4, pending_count: 1, reported_count: 0, hidden_count: 0,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchAdminTransactions.mockResolvedValue({ transactions: [], page: 1, total_pages: 1, total: 0 });
  api.fetchAdminReviews.mockResolvedValue(reviewList([review()]));
});

describe("AdminTransactionsPage", () => {
  it("類型下拉包含後端全部 11 種交易類型（原本只有 5 種）", async () => {
    renderAt("/admin/transactions");
    const select = await screen.findByRole("combobox", { name: "交易類型" });
    const options = within(select).getAllByRole("option").map((o) => (o as HTMLOptionElement).value);
    expect(options.filter(Boolean)).toHaveLength(11);
    expect(options).toEqual(expect.arrayContaining(["subscription_grant", "fixgen_charge", "rebuild_hold"]));
  });

  it("選了新增的類型會送給後端", async () => {
    const user = userEvent.setup();
    renderAt("/admin/transactions");
    await user.selectOptions(await screen.findByRole("combobox", { name: "交易類型" }), "subscription_grant");
    await waitFor(() => expect(api.fetchAdminTransactions.mock.calls.at(-1)?.[0].kind).toBe("subscription_grant"));
  });

  it("網址上不認得的 kind 不送出", async () => {
    renderAt("/admin/transactions?kind=free_money");
    await screen.findByText("沒有符合的交易");
    expect(api.fetchAdminTransactions.mock.calls.at(-1)?.[0].kind).toBeUndefined();
  });
});

describe("AdminReviewsPage", () => {
  it("載入失敗時顯示錯誤與重試（原本整頁空白）", async () => {
    const user = userEvent.setup();
    api.fetchAdminReviews.mockRejectedValueOnce({ response: { data: { detail: "伺服器忙碌" } } });
    renderAt("/admin/reviews");
    expect(await screen.findByRole("alert")).toHaveTextContent("伺服器忙碌");
    await user.click(screen.getByRole("button", { name: "重試" }));
    expect(await screen.findByText("不錯")).toBeInTheDocument();
  });

  it("?filter=reported 送出 reported=1；不認得的 filter 視為全部", async () => {
    const { unmount } = renderAt("/admin/reviews?filter=reported");
    await screen.findByText("不錯");
    expect(api.fetchAdminReviews.mock.calls.at(-1)?.[0]).toMatchObject({ reported: "1" });
    unmount();

    renderAt("/admin/reviews?filter=bogus");
    await screen.findByText("不錯");
    expect(api.fetchAdminReviews.mock.calls.at(-1)?.[0]).toEqual({
      page: 1, pending: undefined, reported: undefined, status: undefined,
    });
    expect(screen.getByRole("combobox")).toHaveValue("all");
  });

  it("空白回覆不送出", async () => {
    const user = userEvent.setup();
    renderAt("/admin/reviews");
    await user.click(await screen.findByRole("button", { name: "送出官方回覆" }));
    expect(api.adminReplyReview).not.toHaveBeenCalled();
    expect(await screen.findByText(/請先輸入官方回覆/)).toBeInTheDocument();
  });

  it("送出回覆後重新載入", async () => {
    const user = userEvent.setup();
    api.adminReplyReview.mockResolvedValue(review());
    renderAt("/admin/reviews");
    await user.type(await screen.findByRole("textbox", { name: /官方回覆/ }), "  感謝回饋  ");
    await user.click(screen.getByRole("button", { name: "送出官方回覆" }));
    expect(api.adminReplyReview).toHaveBeenCalledWith(1, "感謝回饋");
    await waitFor(() => expect(api.fetchAdminReviews).toHaveBeenCalledTimes(2));
  });

  it("隱藏評論要先確認；確認後送出 hidden", async () => {
    const user = userEvent.setup();
    api.adminModerateReview.mockResolvedValue(review({ status: "hidden" }));
    renderAt("/admin/reviews");
    await user.click(await screen.findByRole("button", { name: "隱藏評論" }));
    expect(api.adminModerateReview).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: "確定" }));
    expect(api.adminModerateReview).toHaveBeenCalledWith(1, "hidden");
  });

  it("已有官方回覆時才出現「移除回覆」", async () => {
    api.fetchAdminReviews.mockResolvedValue(reviewList([review({
      response: { body: "謝謝", created_at: "2026-09-21T00:00:00Z", updated_at: "2026-09-21T00:00:00Z", author_username: null },
    })]));
    renderAt("/admin/reviews");
    expect(await screen.findByRole("button", { name: "移除回覆" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更新官方回覆" })).toBeInTheDocument();
  });
});
