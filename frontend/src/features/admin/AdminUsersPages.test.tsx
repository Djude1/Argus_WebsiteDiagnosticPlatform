import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AdminSubscriptionPlan,
  AdminUser,
  AdminUserDetailResponse,
  AdminUserSubscription,
} from "../../shared/apiContracts";
import { AdminUserDetailPage, AdminUsersPage } from "./AdminUsersPages";

// fixture 以產生的型別宣告：後端改欄位時，這裡會先編譯失敗，而不是測試照過。

vi.mock("../../api", () => ({
  fetchAdminUsers: vi.fn(),
  fetchAdminUserDetail: vi.fn(),
  adminAdjustCoin: vi.fn(),
  fetchUserLoginEvents: vi.fn(),
  fetchUserSubscription: vi.fn(),
  fetchAdminSubscriptionPlans: vi.fn(),
  adminUserSubscriptionAction: vi.fn(),
}));
const api = vi.mocked(await import("../../api"));

function listUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 7,
    username: "alice",
    email: "alice@example.com",
    full_name: "Alice Chen",
    date_joined: "2026-01-01T00:00:00Z",
    last_login: null,
    is_staff: false,
    balance: 1200,
    total_purchased_ntd: 0,
    total_scans_used: 3,
    ...overrides,
  };
}

function detail(overrides: Partial<AdminUserDetailResponse> = {}): AdminUserDetailResponse {
  return {
    ...listUser(),
    is_active: true,
    is_superuser: false,
    wallet: {
      balance: 1200,
      total_purchased_ntd: 1990,
      total_scans_used: 3,
      last_bonus_year: 2026,
      last_bonus_month: 9,
    },
    recent_transactions: [],
    ai_usage: { total_tokens: 0, total_sessions: 0, by_provider: [] },
    recent_scans: [{
      id: 42, user_id: 7, username: "alice", origin: "https://example.com",
      status: "failed", scan_mode: "passive", overall_score: null, pages_count: 0,
      findings_count: 0, max_pages: 50, duration_sec: null,
      created_at: "2026-09-25T06:00:00Z", completed_at: null,
    }],
    scans_total: 3,
    ...overrides,
  };
}

const PLANS: AdminSubscriptionPlan[] = [
  {
    id: 1, code: "legacy", name: "舊方案", monthly_price_ntd: 99, monthly_coins: 100,
    features: [], badge: "", sort_order: 0, is_active: false,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: 2, code: "pro", name: "專業版", monthly_price_ntd: 299, monthly_coins: 500,
    features: [], badge: "", sort_order: 1, is_active: true,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  },
];

function subscription(overrides: Partial<AdminUserSubscription> = {}): AdminUserSubscription {
  return {
    status: "active", status_label: "有效", plan_code: "pro", plan_name: "專業版",
    periods_remaining: 3, started_at: "2026-09-01T00:00:00Z",
    current_period_end: "2026-10-01T00:00:00Z", cancelled_at: null,
    created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/users" element={<AdminUsersPage />} />
        <Route path="/admin/users/:userId" element={<AdminUserDetailPage />} />
        <Route path="*" element={null} />
      </Routes>
      <Location />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchAdminUsers.mockResolvedValue({ users: [listUser()], page: 1, total_pages: 1, total: 1 });
  api.fetchAdminUserDetail.mockResolvedValue(detail());
  api.fetchUserLoginEvents.mockResolvedValue({ events: [] });
  api.fetchUserSubscription.mockResolvedValue({ subscription: null });
  api.fetchAdminSubscriptionPlans.mockResolvedValue({ plans: PLANS });
});

describe("AdminUsersPage", () => {
  it("白名單內的 ordering 照送，白名單外的不送", async () => {
    const { unmount } = renderAt("/admin/users?ordering=-balance");
    await screen.findByText("Alice Chen");
    expect(api.fetchAdminUsers.mock.calls.at(-1)?.[0].ordering).toBe("-balance");
    unmount();

    renderAt("/admin/users?ordering=password");
    await screen.findByText("Alice Chen");
    expect(api.fetchAdminUsers.mock.calls.at(-1)?.[0].ordering).toBeUndefined();
  });

  it("搜尋送出後以 q 重新載入，並回到第一頁", async () => {
    const user = userEvent.setup();
    renderAt("/admin/users?page=3");
    await screen.findByText("Alice Chen");
    await user.type(screen.getByRole("textbox", { name: "搜尋使用者" }), "alice");
    await user.click(screen.getByRole("button", { name: "搜尋" }));
    await waitFor(() => expect(api.fetchAdminUsers.mock.calls.at(-1)?.[0]).toMatchObject({ q: "alice", page: 1 }));
  });

  it("點列進入使用者詳情", async () => {
    const user = userEvent.setup();
    renderAt("/admin/users");
    await user.click(await screen.findByText("Alice Chen"));
    expect(screen.getByTestId("location")).toHaveTextContent("/admin/users/7");
  });
});

describe("AdminUserDetailPage", () => {
  it("網址上的 id 不是正整數時直接顯示找不到，不打 API", async () => {
    renderAt("/admin/users/abc");
    expect(await screen.findByText("找不到此使用者")).toBeInTheDocument();
    expect(api.fetchAdminUserDetail).not.toHaveBeenCalled();
  });

  it("「查看全部」連到以 user 篩選的掃描列表——與掃描頁的 ?user= 是同一條路", async () => {
    renderAt("/admin/users/7");
    const link = await screen.findByRole("link", { name: /查看全部/ });
    expect(link).toHaveAttribute("href", "/admin/scans?user=7");
  });

  it("沒有任何掃描時不給「查看全部」", async () => {
    api.fetchAdminUserDetail.mockResolvedValue(detail({ scans_total: 0, recent_scans: [] }));
    renderAt("/admin/users/7");
    expect(await screen.findByText("此使用者尚未建立任何掃描")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /查看全部/ })).not.toBeInTheDocument();
  });

  it("最近掃描的列可進入該掃描詳情", async () => {
    const user = userEvent.setup();
    renderAt("/admin/users/7");
    await user.click(await screen.findByText("https://example.com"));
    expect(screen.getByTestId("location")).toHaveTextContent("/admin/scans/42");
  });

  it("沒有錢包時明確顯示，而不是壞掉", async () => {
    api.fetchAdminUserDetail.mockResolvedValue(detail({ wallet: null }));
    renderAt("/admin/users/7");
    expect(await screen.findByText("尚未建立錢包")).toBeInTheDocument();
  });

  it("調整點數：0 不送出", async () => {
    const user = userEvent.setup();
    renderAt("/admin/users/7");
    await user.type(await screen.findByRole("spinbutton", { name: "變動金額" }), "0");
    await user.click(screen.getByRole("button", { name: "送出" }));
    expect(await screen.findByText("請輸入非 0 的整數")).toBeInTheDocument();
    expect(api.adminAdjustCoin).not.toHaveBeenCalled();
  });

  it("調整點數：快捷鍵帶入金額，送出後顯示結果並重新載入", async () => {
    const user = userEvent.setup();
    api.adminAdjustCoin.mockResolvedValue({
      transaction: {
        id: 1, amount: -100, kind: "admin_adjust", kind_label: "管理員調整", balance_after: 1100,
        scan_job: null, scan_origin: null, plan: null, plan_name: null,
        admin_actor_username: "root", note: "退費", created_at: "2026-09-26T00:00:00Z",
      },
      wallet_balance: 1100,
    });
    renderAt("/admin/users/7");

    await user.click(await screen.findByRole("button", { name: "-100" }));
    await user.type(screen.getByRole("textbox", { name: "備註" }), "退費");
    await user.click(screen.getByRole("button", { name: "送出" }));

    expect(api.adminAdjustCoin).toHaveBeenCalledWith(7, -100, "退費");
    expect(await screen.findByText("已扣 100 coin，當前餘額 1100")).toBeInTheDocument();
    expect(api.fetchAdminUserDetail).toHaveBeenCalledTimes(2);
  });

  it("訂閱：預設選第一個啟用中的方案（跳過停用的）", async () => {
    renderAt("/admin/users/7");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "訂閱方案" })).toHaveValue("pro"));
  });

  it("訂閱：開通送出所選方案與期數", async () => {
    const user = userEvent.setup();
    api.adminUserSubscriptionAction.mockResolvedValue({ subscription: subscription() });
    renderAt("/admin/users/7");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "訂閱方案" })).toHaveValue("pro"));

    await user.click(screen.getByRole("button", { name: "開通訂閱" }));
    expect(api.adminUserSubscriptionAction).toHaveBeenCalledWith(7, "grant", "pro", 1);
    expect(await screen.findByText(/已開通 專業版（3 期）/)).toBeInTheDocument();
  });

  it("訂閱：取消要先確認，取消確認就不呼叫 API", async () => {
    const user = userEvent.setup();
    renderAt("/admin/users/7");
    await user.click(await screen.findByRole("button", { name: "取消訂閱" }));
    await user.click(await screen.findByRole("button", { name: "取消" }));
    expect(api.adminUserSubscriptionAction).not.toHaveBeenCalled();
  });

  it("登入記錄載入失敗時顯示空狀態，不擋整頁", async () => {
    api.fetchUserLoginEvents.mockRejectedValue(new Error("boom"));
    renderAt("/admin/users/7");
    expect(await screen.findByText("尚無登入紀錄")).toBeInTheDocument();
    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
  });
});
