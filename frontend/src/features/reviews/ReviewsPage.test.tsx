import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { ReviewsPage } from "./ReviewsPage";

vi.mock("../../api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
const { api } = vi.mocked(await import("../../api"));

const SUMMARY = { total: 2, average: 4.5, distribution: { 5: 1, 4: 1 } };
const REVIEW = {
  id: 1, rating: 5, title: "", comment: "報告清楚，修正產出可以直接貼上使用。", show_partial_email: true,
  user_display: "ab***@example.com", is_mine: false, verified_experience: true, experience_at: null,
  helpful_count: 3, my_helpful: false,
  response: {
    id: 9, body: "謝謝你的回饋！", helpful_count: 0, my_helpful: false,
    created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
  },
  created_at: "2026-09-19T00:00:00Z", updated_at: "2026-09-19T00:00:00Z",
};
const LIST = { reviews: [REVIEW], total: 1, total_pages: 1, page: 1 };

function renderPage() {
  return render(<MemoryRouter><ReviewsPage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (url: string) => {
    if (url === "/reviews/summary/") return { data: SUMMARY };
    if (url === "/reviews/mine/") {
      return { data: { review: null, eligibility: { eligible: true, reason: "", experience_at: null } } };
    }
    return { data: LIST };
  });
});

afterEach(() => {
  useArgusStore.setState({ accessToken: null });
});

describe("ReviewsPage", () => {
  it("評論載入失敗時一定有重試鍵，重試後顯示評論", async () => {
    api.get.mockImplementation(async (url: string) => {
      if (url === "/reviews/summary/") return { data: SUMMARY };
      throw new Error("network");
    });
    renderPage();
    const retry = await screen.findByRole("button", { name: "重新載入" });

    api.get.mockImplementation(async (url: string) => (
      url === "/reviews/summary/" ? { data: SUMMARY } : { data: LIST }
    ));
    await userEvent.click(retry);
    expect(await screen.findByText(REVIEW.comment)).toBeInTheDocument();
  });

  it("官方回覆以「Argus 團隊回覆」標示，並保留逐則按讚與檢舉", async () => {
    renderPage();
    const reply = await screen.findByRole("complementary", { name: "Argus 官方回覆" });
    expect(reply).toHaveTextContent("Argus 團隊回覆");
    expect(screen.getByRole("button", { name: "按讚使用者評論，目前 3 個讚" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "檢舉官方回覆" })).toBeInTheDocument();
  });

  it("有資格的使用者可開啟表單，星等選擇器以 radio 呈現可及名稱", async () => {
    useArgusStore.setState({ accessToken: "token" });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "寫下你的評論" }));
    await userEvent.click(screen.getByRole("radio", { name: "4 星：滿意" }));
    expect(screen.getByRole("radio", { name: "4 星：滿意" })).toBeChecked();
    expect(screen.getByText("4 星 · 滿意")).toBeInTheDocument();
  });
});
