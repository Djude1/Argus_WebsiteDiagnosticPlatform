import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { submitEcpayForm } from "../../components/billing/BuyerInvoiceFields";
import { useArgusStore } from "../../store";
import { SubscriptionPanel } from "./SubscriptionPanel";

vi.mock("../../api", () => ({
  cancelSubscription: vi.fn(),
  fetchMySubscription: vi.fn(),
  fetchSubscriptionPlans: vi.fn(),
  subscribePlan: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

const PLAN = {
  id: 1, code: "sub-pro", name: "專業月訂閱", monthly_price_ntd: 299, monthly_coins: 500,
  features: [], badge: "", sort_order: 1,
};
const LIVE_ACTION = "https://payment.ecpay.com.tw/Cashier/AioCheckOut/V5";

function renderPanel(path = "/billing") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SubscriptionPanel purchasePlans={[]} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useArgusStore.setState({ me: { email: "me@example.com" }, fetchWallet: vi.fn() });
  api.fetchSubscriptionPlans.mockResolvedValue({
    plans: [PLAN], payment_mode: "ecpay", subscribe_enabled: true,
  });
  api.fetchMySubscription.mockResolvedValue({ subscription: null });
});

describe("SubscriptionPanel（綠界定期定額）", () => {
  it("正式模式：填發票資料並同意每月扣款後，送出綠界結帳表單", async () => {
    const user = userEvent.setup();
    const submit = vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(() => {});
    api.subscribePlan.mockResolvedValue({
      order: { id: 3 },
      payment: { action: LIVE_ACTION, fields: { MerchantTradeNo: "ARGUSS00000000000003" } },
    });
    renderPanel();
    expect(await screen.findByText(/綠界信用卡定期定額/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "訂閱此方案" }));
    await user.type(screen.getByLabelText(/姓名/), "王小明");
    const pay = screen.getByRole("button", { name: "前往綠界綁定信用卡並付款" });
    await user.click(pay);
    expect(api.subscribePlan).not.toHaveBeenCalled(); // 還沒勾同意

    await user.click(screen.getByRole("checkbox", { name: /同意每月自動扣款 NT\$ 299/ }));
    await user.click(pay);
    await waitFor(() => expect(submit).toHaveBeenCalled());
    expect(api.subscribePlan).toHaveBeenCalledWith("sub-pro", expect.objectContaining({
      buyer_name: "王小明", buyer_email: "me@example.com", invoice_type: "personal", agree_terms: true,
    }));
    const form = submit.mock.contexts[0] as HTMLFormElement;
    expect(form.action).toBe(LIVE_ACTION);
    submit.mockRestore();
  });

  it("後端回 409（已有自動扣款）時顯示原因", async () => {
    const user = userEvent.setup();
    api.subscribePlan.mockRejectedValue({
      response: { status: 409, data: { detail: "你已有每月自動扣款中的訂閱；要換方案請先取消目前的訂閱。" } },
    });
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "訂閱此方案" }));
    await user.type(screen.getByLabelText(/姓名/), "王小明");
    await user.click(screen.getByRole("checkbox", { name: /同意每月自動扣款/ }));
    await user.click(screen.getByRole("button", { name: "前往綠界綁定信用卡並付款" }));
    expect(await screen.findByText(/要換方案請先取消/)).toBeInTheDocument();
  });

  it("自動扣款中的訂閱顯示「每月自動扣款：是」", async () => {
    api.fetchMySubscription.mockResolvedValue({
      subscription: {
        status: "active", status_label: "生效中", plan_code: "sub-pro", plan_name: "專業月訂閱",
        plan_monthly_coins: 500, periods_remaining: 0, started_at: "2026-10-04T00:00:00Z",
        current_period_end: "2026-11-04T00:00:00Z", cancelled_at: null, auto_renew: true,
      },
    });
    renderPanel();
    expect(await screen.findByText("是（綠界信用卡）")).toBeInTheDocument();
  });

  it("結帳表單只會送往綠界的測試或正式網址", () => {
    expect(() => submitEcpayForm({ action: "https://evil.example.com/pay", fields: {} })).toThrow();
  });
});
