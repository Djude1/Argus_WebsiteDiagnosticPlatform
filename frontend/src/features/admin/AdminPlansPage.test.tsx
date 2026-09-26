import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PricingPlan } from "../../shared/apiContracts";
import { AdminPlansPage } from "./AdminPlansPage";

vi.mock("../../api", () => ({
  fetchAdminPlans: vi.fn(),
  createPlan: vi.fn(),
  updatePlan: vi.fn(),
  deletePlan: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

function plan(overrides: Partial<PricingPlan> = {}): PricingPlan {
  return {
    id: 4, code: "flagship", name: "旗艦方案", price_ntd: 1500, coin_amount: 2200,
    badge: "", description: "", sort_order: 3, is_active: true,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

const validationError = (fields: Record<string, string[]>) => ({ response: { status: 400, data: fields } });

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchAdminPlans.mockResolvedValue({ items: [plan()], coin_per_page: 10 });
});

describe("AdminPlansPage", () => {
  it("毛利依後端的每頁 coin 數計算：旗艦方案約 90%（原本誤算成 2%、標成須重新定價）", async () => {
    render(<AdminPlansPage />);
    const card = (await screen.findByText("旗艦方案")).closest(".admin-plan-card") as HTMLElement;
    expect(within(card).getByText(/（90%）/)).toHaveClass("tone-good");
    expect(within(card).getByText("NT$ 147.4")).toBeInTheDocument();
    expect(within(card).getByText(/≈ 220 頁掃描/)).toBeInTheDocument();
  });

  it("新增方案有 code 欄位並一起送出（原本沒有，新增一律被後端拒絕）", async () => {
    const user = userEvent.setup();
    api.createPlan.mockResolvedValue(plan({ id: 9, code: "pro-2026" }));
    render(<AdminPlansPage />);
    await user.click(await screen.findByRole("button", { name: "＋ 新增方案" }));
    await user.type(screen.getByLabelText(/方案代碼/), "pro-2026");
    await user.type(screen.getByLabelText(/方案名稱/), "專業方案");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(api.createPlan).toHaveBeenCalledWith(expect.objectContaining({ code: "pro-2026", name: "專業方案" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.fetchAdminPlans).toHaveBeenCalledTimes(2);
  });

  it("後端驗證錯誤顯示在對應欄位旁，彈窗留著", async () => {
    const user = userEvent.setup();
    api.createPlan.mockRejectedValue(validationError({ code: ["此為必需欄位。"] }));
    render(<AdminPlansPage />);
    await user.click(await screen.findByRole("button", { name: "＋ 新增方案" }));
    await user.click(screen.getByRole("button", { name: "儲存" }));
    expect(await screen.findByText("此為必需欄位。")).toBeInTheDocument();
    expect(screen.getByLabelText(/方案代碼/)).toHaveAccessibleDescription(/此為必需欄位。/);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("編輯時 code 唯讀且不送出（購點與「推薦」標示都以 code 識別方案）", async () => {
    const user = userEvent.setup();
    api.updatePlan.mockResolvedValue(plan({ price_ntd: 1600 }));
    render(<AdminPlansPage />);
    await user.click(await screen.findByRole("button", { name: "編輯" }));
    expect(screen.getByLabelText(/方案代碼/)).toHaveAttribute("readonly");

    const price = screen.getByLabelText(/價格/);
    await user.clear(price);
    await user.type(price, "1600");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(api.updatePlan).toHaveBeenCalledWith(4, expect.objectContaining({ price_ntd: 1600 }));
    expect(api.updatePlan.mock.calls[0]?.[1]).not.toHaveProperty("code");
  });

  it("編輯中的即時試算跟著輸入變動", async () => {
    const user = userEvent.setup();
    render(<AdminPlansPage />);
    await user.click(await screen.findByRole("button", { name: "＋ 新增方案" }));
    // 預設 100 coin、NT$0 → 輸入 NT$100：成本 NT$6.7、毛利 93%
    const price = screen.getByLabelText(/價格/);
    await user.clear(price);
    await user.type(price, "100");
    expect(screen.getByText(/毛利 NT\$ 93\.3（93%，健康）/)).toBeInTheDocument();
  });

  it("載入失敗顯示錯誤與重試，不誤報「尚無方案」", async () => {
    const user = userEvent.setup();
    api.fetchAdminPlans.mockRejectedValueOnce(new Error("Network Error"));
    render(<AdminPlansPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Network Error");
    expect(screen.queryByText("尚無方案")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重試" }));
    expect(await screen.findByText("旗艦方案")).toBeInTheDocument();
  });

  it("刪除已有訂單的方案：顯示後端的 409 說明（原本後端直接 500）", async () => {
    const user = userEvent.setup();
    api.deletePlan.mockRejectedValue({ response: { status: 409, data: { detail: "此項目已被其他資料引用（例如訂單），無法刪除；如要下架請改為停用。" } } });
    render(<AdminPlansPage />);
    await user.click(await screen.findByRole("button", { name: "刪除" }));
    await user.click(await screen.findByRole("button", { name: "確定" }));
    expect(await screen.findByText("此項目已被其他資料引用（例如訂單），無法刪除；如要下架請改為停用。")).toBeInTheDocument();
  });
});
