import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AdminScanDetailResponse,
  AdminScanJob,
  AdminScanListResponse,
} from "../../shared/apiContracts";
import { AdminScanDetailPage, AdminScansPage } from "./AdminScansPages";

// 後台出過兩次靜默失效，這裡在畫面層各鎖一次：
//   1. 網址帶 ?user=5，列表卻沒把 user 送給後端（畫面正常、結果是全部人的掃描）
//   2. 掃描缺 user_id，「查看使用者」連結永遠不出現
// 型別已在編譯期擋下欄位名錯誤；這些測試擋的是「欄位對了但沒接上」。

vi.mock("../../api", () => ({
  fetchAdminScans: vi.fn(),
  fetchAdminScanDetail: vi.fn(),
  adminCancelScan: vi.fn(),
  adminRequeueScan: vi.fn(),
}));
const api = await import("../../api");
const fetchAdminScans = vi.mocked(api.fetchAdminScans);
const fetchAdminScanDetail = vi.mocked(api.fetchAdminScanDetail);
const adminCancelScan = vi.mocked(api.adminCancelScan);
const adminRequeueScan = vi.mocked(api.adminRequeueScan);

function scan(overrides: Partial<AdminScanJob> = {}): AdminScanJob {
  return {
    id: 42,
    user_id: 7,
    username: "alice",
    origin: "https://example.com",
    status: "completed",
    scan_mode: "passive",
    overall_score: 88,
    pages_count: 12,
    findings_count: 5,
    max_pages: 50,
    duration_sec: 80,
    created_at: "2026-09-25T06:00:00Z",
    completed_at: "2026-09-25T06:01:20Z",
    ...overrides,
  };
}

function listResponse(scans: AdminScanJob[]): AdminScanListResponse {
  return { scans, page: 1, total_pages: 1, total: scans.length };
}

function detailResponse(overrides: Partial<AdminScanJob> = {}): AdminScanDetailResponse {
  return {
    scan: scan(overrides),
    warning_summary: {},
    top_actions: [],
    category_scores: {},
    error_message: "",
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
        <Route path="/admin/scans" element={<AdminScansPage />} />
        <Route path="/admin/scans/:scanId" element={<AdminScanDetailPage />} />
        <Route path="*" element={null} />
      </Routes>
      <Location />
    </MemoryRouter>,
  );
}

const lastListCall = () => fetchAdminScans.mock.calls.at(-1)?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  fetchAdminScans.mockResolvedValue(listResponse([scan()]));
  fetchAdminScanDetail.mockResolvedValue(detailResponse());
});

describe("AdminScansPage", () => {
  it("?user=5 會以整數送給後端，並提示目前只看單一使用者（失效 1）", async () => {
    renderAt("/admin/scans?user=5");
    await screen.findByText("https://example.com");
    expect(lastListCall()).toMatchObject({ user: 5 });
    expect(screen.getByText("目前只顯示單一使用者的掃描")).toBeInTheDocument();
  });

  it("「顯示全部使用者」會拿掉 user 篩選並重新載入", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans?user=5");
    await user.click(await screen.findByRole("button", { name: "顯示全部使用者" }));
    await waitFor(() => expect(lastListCall()?.user).toBeUndefined());
    expect(screen.queryByText("目前只顯示單一使用者的掃描")).not.toBeInTheDocument();
  });

  it("壞的 user 值不送出（不讓後端收到 NaN）", async () => {
    renderAt("/admin/scans?user=abc");
    await screen.findByText("https://example.com");
    expect(lastListCall()?.user).toBeUndefined();
  });

  it("不在白名單的 ordering 不送出，交給後端用預設排序", async () => {
    renderAt("/admin/scans?ordering=-password");
    await screen.findByText("https://example.com");
    expect(lastListCall()?.ordering).toBeUndefined();
  });

  it("白名單內的 ordering 照送", async () => {
    renderAt("/admin/scans?ordering=-findings_count");
    await screen.findByText("https://example.com");
    expect(lastListCall()?.ordering).toBe("-findings_count");
  });

  it("點表頭排序會改網址並重新載入", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans");
    await screen.findByText("https://example.com");
    await user.click(screen.getByRole("button", { name: /分數/ }));
    expect(screen.getByTestId("location")).toHaveTextContent("ordering=-overall_score");
    await waitFor(() => expect(lastListCall()?.ordering).toBe("-overall_score"));
  });

  it("點列會進到掃描詳情；鍵盤 Enter 也可以", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans");
    const row = (await screen.findByText("https://example.com")).closest("tr")!;
    row.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByTestId("location")).toHaveTextContent("/admin/scans/42");
  });

  it("載入失敗時顯示錯誤與重試，重試會再打一次 API", async () => {
    const user = userEvent.setup();
    fetchAdminScans.mockRejectedValueOnce({ response: { data: { detail: "伺服器忙碌" } } });
    renderAt("/admin/scans");
    expect(await screen.findByRole("alert")).toHaveTextContent("伺服器忙碌");
    await user.click(screen.getByRole("button", { name: "重試" }));
    expect(await screen.findByText("https://example.com")).toBeInTheDocument();
    expect(fetchAdminScans).toHaveBeenCalledTimes(2);
  });
});

describe("AdminScanDetailPage", () => {
  it("有 user_id 時提供「查看使用者」連結（失效 2）", async () => {
    renderAt("/admin/scans/42");
    const link = await screen.findByRole("link", { name: /查看使用者/ });
    expect(link).toHaveAttribute("href", "/admin/users/7");
    expect(fetchAdminScanDetail).toHaveBeenCalledWith(42);
  });

  it("已完成的掃描不能終止也不能重排", async () => {
    renderAt("/admin/scans/42");
    await screen.findByText("掃描 #42");
    expect(screen.queryByRole("button", { name: "終止掃描" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重新排入佇列" })).not.toBeInTheDocument();
  });

  it("失敗的掃描可重排：確認後呼叫 API，並明示未扣點", async () => {
    const user = userEvent.setup();
    fetchAdminScanDetail.mockResolvedValue(detailResponse({ status: "failed" }));
    adminRequeueScan.mockResolvedValue({ status: "queued", charged: 0 });
    renderAt("/admin/scans/42");

    await user.click(await screen.findByRole("button", { name: "重新排入佇列" }));
    await user.click(await screen.findByRole("button", { name: "確定" }));

    expect(adminRequeueScan).toHaveBeenCalledWith(42);
    expect(await screen.findByText("已重新排入佇列，未扣點。")).toBeInTheDocument();
  });

  it("取消確認對話框時不呼叫 API", async () => {
    const user = userEvent.setup();
    fetchAdminScanDetail.mockResolvedValue(detailResponse({ status: "failed" }));
    renderAt("/admin/scans/42");

    await user.click(await screen.findByRole("button", { name: "重新排入佇列" }));
    await user.click(await screen.findByRole("button", { name: "取消" }));
    expect(adminRequeueScan).not.toHaveBeenCalled();
  });

  it("終止進行中的掃描時顯示實際退回的點數", async () => {
    const user = userEvent.setup();
    fetchAdminScanDetail.mockResolvedValue(detailResponse({ status: "crawling" }));
    adminCancelScan.mockResolvedValue({ status: "cancelled", refunded: 30 });
    renderAt("/admin/scans/42");

    await user.click(await screen.findByRole("button", { name: "終止掃描" }));
    await user.click(await screen.findByRole("button", { name: "確定" }));
    expect(await screen.findByText("已終止，退回 30 coin。")).toBeInTheDocument();
  });

  it("top_actions／warning_summary 依產生端的結構呈現", async () => {
    fetchAdminScanDetail.mockResolvedValue({
      ...detailResponse(),
      top_actions: [{ title: "缺少 CSP", category: "security", severity: "high", priority_score: 91.6 }],
      warning_summary: { blocked_urls: [{ url: "https://example.com/admin", reason: "403" }] },
    });
    renderAt("/admin/scans/42");
    expect(await screen.findByText("缺少 CSP")).toBeInTheDocument();
    expect(screen.getByText("priority 92")).toBeInTheDocument();
    expect(screen.getByText("https://example.com/admin")).toBeInTheDocument();
    expect(screen.getByText("403")).toBeInTheDocument();
  });
});
