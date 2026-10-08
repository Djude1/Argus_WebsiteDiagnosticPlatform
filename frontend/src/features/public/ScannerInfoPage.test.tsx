import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScannerInfoPage } from "./ScannerInfoPage";

// 掃描來源說明的承諾：User-Agent、robots 規則與出口 IP 都照後端設定顯示；
// 沒有公布 IP 時明講請以 User-Agent 辨識；讀取失敗有重新載入。

vi.mock("../../api", () => ({ api: { get: vi.fn() } }));
const { api } = vi.mocked(await import("../../api"));

const INFO = {
  user_agent: "SiteSense-AI-Scanner/1.0 (authorized-audit)",
  robots_token: "SiteSense-AI-Scanner",
  egress_ips: [] as string[],
  passive_pages_per_second: 5,
  active_requests_per_second: 2,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ScannerInfoPage />
    </MemoryRouter>,
  );
}

describe("ScannerInfoPage", () => {
  beforeEach(() => {
    api.get.mockReset();
  });

  it("顯示 User-Agent、robots 規則與速率；沒有公布 IP 時請對方以 User-Agent 辨識", async () => {
    api.get.mockResolvedValue({ data: INFO });
    renderPage();
    expect(await screen.findByText(INFO.user_agent)).toBeInTheDocument();
    expect(screen.getByText(/User-agent: SiteSense-AI-Scanner/)).toHaveTextContent("Disallow: /");
    expect(screen.getByText(/每秒最多 5 頁/)).toBeInTheDocument();
    expect(screen.getByText("目前沒有公布固定的出口 IP，請以 User-Agent 辨識。")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/content/scanner-info/");
  });

  it("有設定出口 IP 時逐一列出", async () => {
    api.get.mockResolvedValue({ data: { ...INFO, egress_ips: ["203.0.113.10", "198.51.100.0/28"] } });
    renderPage();
    expect(await screen.findByText("203.0.113.10")).toBeInTheDocument();
    expect(screen.getByText("198.51.100.0/28")).toBeInTheDocument();
    expect(screen.queryByText(/目前沒有公布固定的出口 IP/)).not.toBeInTheDocument();
  });

  it("讀取失敗時可以重新載入", async () => {
    const user = userEvent.setup();
    api.get.mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce({ data: INFO });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "重新載入" }));
    expect(await screen.findByText(INFO.user_agent)).toBeInTheDocument();
  });
});
