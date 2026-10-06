import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import OptimizationReport from "./OptimizationReport";

beforeAll(() => {
  // jsdom 沒有 ResizeObserver；預覽框只用它算縮放比例
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

const DATA = {
  has_original: true,
  has_optimized: true,
  findings: [
    { title: "頁面標題太短", severity: "medium", category: "seo" },
    { title: "缺少 CSP", severity: "low", category: "security" },
  ],
  edits: [
    { why: "title 只有 2 個字", impact: "搜尋結果看得出網站主題", layer: "technical", category: "seo", applied: 1, rejected: "" },
    { why: "首屏主標題不突出", impact: "一進頁面就看到主標題", layer: "visual", category: "hierarchy", applied: 1, rejected: "" },
    { why: "想加 script", impact: "", layer: "technical", category: "performance", applied: 0, rejected: "不接受新增 script" },
  ],
  outcome: {
    summary: "補齊搜尋標記，首屏標題更突出",
    metrics: [
      { key: "images_missing_alt", label: "缺少 alt 的圖片", category: "accessibility", before: 3, after: 0, improved: true },
    ],
    not_handled: [{ item: "缺少 CSP", reason: "回應標頭需在伺服器設定", owner: "server" }],
  },
};

describe("OptimizationReport", () => {
  it("一眼看出改了什麼：摘要、流程數字、前後比較", async () => {
    const loadHtml = vi.fn((variant: string) => Promise.resolve(`<p>${variant}</p>`));
    render(<OptimizationReport data={DATA} loadHtml={loadHtml} />);
    expect(screen.getByText("補齊搜尋標記，首屏標題更突出")).toBeInTheDocument();
    expect(screen.getByText("視覺 1・技術 1")).toBeInTheDocument();
    // 兩份 HTML 都載入後才顯示預覽（sandbox iframe）
    await waitFor(() => expect(screen.getByTitle("Argus 優化後")).toBeInTheDocument());
    expect(screen.getByTitle("原始頁面")).toHaveAttribute("sandbox", "");
    expect(loadHtml).toHaveBeenCalledWith("original");
    expect(loadHtml).toHaveBeenCalledWith("optimized");
  });

  it("修改可依分類篩選，被拒絕的修改說明原因", async () => {
    render(<OptimizationReport data={DATA} loadHtml={() => Promise.resolve("")} />);
    expect(screen.getByText("不接受新增 script")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "視覺與 UX 1" }));
    expect(screen.getByText("一進頁面就看到主標題")).toBeInTheDocument();
    expect(screen.queryByText("搜尋結果看得出網站主題")).not.toBeInTheDocument();
  });

  it("列出前後指標與需要其他人處理的項目", () => {
    render(<OptimizationReport data={DATA} loadHtml={() => Promise.resolve("")} />);
    expect(screen.getByRole("row", { name: /缺少 alt 的圖片 3 0/ })).toBeInTheDocument();
    expect(screen.getByText("伺服器設定")).toBeInTheDocument();
    expect(screen.getByText("回應標頭需在伺服器設定")).toBeInTheDocument();
  });
});
