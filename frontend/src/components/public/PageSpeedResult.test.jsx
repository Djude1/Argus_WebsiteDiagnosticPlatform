import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import PageSpeedResult from "./PageSpeedResult.jsx";

vi.mock("../../api", () => ({ api: { get: vi.fn() }, setAccessToken: vi.fn() }));

const REPORT = {
  lab: {
    version: "12.0.0",
    scores: { performance: 42, accessibility: 95, "best-practices": 80, seo: 100 },
    metrics: { "largest-contentful-paint": { label: "LCP（最大內容繪製）", display: "4.1 s" } },
    opportunities: [{ id: "unused-javascript", title: "減少未使用的 JavaScript", display: "可省 1.2 秒" }],
  },
  field: { reason: "Chrome 使用者資料不足" },
};

describe("PageSpeedResult", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(api.get).mockReset();
  });

  it("平台沒有設定金鑰時不顯示", () => {
    const { container } = render(<PageSpeedResult pagespeed={{ status: "unavailable" }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("量測中會輪詢，完成後顯示分數、指標與改善項目", async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: { status: "pending" } })
      .mockResolvedValueOnce({ data: { status: "done", report: REPORT } });
    render(<PageSpeedResult pagespeed={{ status: "pending", job: "job-token-123456789" }} />);
    expect(screen.getByText(/Google 正在量測/)).toBeInTheDocument();

    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });

    expect(api.get).toHaveBeenCalledWith("/insights/speed-test/pagespeed/job-token-123456789/");
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("4.1 s")).toBeInTheDocument();
    expect(screen.getByText("減少未使用的 JavaScript")).toBeInTheDocument();
    expect(screen.getByText("Chrome 使用者資料不足")).toBeInTheDocument();
  });

  it("量測失敗時顯示原因", () => {
    render(<PageSpeedResult pagespeed={{ status: "failed", reason: "PageSpeed Insights 配額用完" }} />);
    expect(screen.getByText(/PageSpeed Insights 配額用完/)).toBeInTheDocument();
  });
});
