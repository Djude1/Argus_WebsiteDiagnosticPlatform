import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PerformancePanel } from "./PerformancePanel";

const REPORT = {
  lab: {
    version: "12.6.0",
    error: "",
    scores: { performance: 72, accessibility: 90, "best-practices": 96, seo: 92 },
    metrics: { "largest-contentful-paint": { label: "LCP（最大內容繪製）", display: "3.1 s" } },
    opportunities: [{ id: "unused-javascript", title: "Reduce unused JavaScript", display: "" }],
  },
  field: {
    period: "過去 28 天",
    scope: "origin",
    metrics: { LCP: { p75: 2600, category: "AVERAGE", category_label: "需改善" } },
  },
};

describe("PerformancePanel", () => {
  it("分開呈現 Lighthouse 實驗室分數與 CrUX 真實使用者資料，並註明不計入 Argus 分數", () => {
    render(<PerformancePanel report={REPORT} />);
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText(/不計入 Argus 分數/)).toBeInTheDocument();
    expect(screen.getByText("2.6 秒")).toBeInTheDocument();
    expect(screen.getByText(/這個網址的資料不足，以下是整個網站的資料/)).toBeInTheDocument();
    expect(screen.getByText("Reduce unused JavaScript")).toBeInTheDocument();
  });

  it("沒有真實使用者資料時顯示原因，不顯示數字", () => {
    render(
      <PerformancePanel
        report={{ ...REPORT, field: { period: "過去 28 天", scope: "none", reason: "資料不足的原因" } }}
      />,
    );
    expect(screen.getByText("資料不足的原因")).toBeInTheDocument();
    expect(screen.queryByText("2.6 秒")).not.toBeInTheDocument();
  });

  it("沒有量測時說明原因", () => {
    render(<PerformancePanel report={{}} />);
    expect(screen.getByText(/這次掃描沒有效能量測/)).toBeInTheDocument();
  });
});
