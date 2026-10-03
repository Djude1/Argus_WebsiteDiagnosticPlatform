import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SeverityDonut, scoreGrade, scoreTone } from "./DashboardWidgets";

describe("scoreTone / scoreGrade", () => {
  it("≥80 良好、60–79 中等、<60 待加強，沒有分數為 none", () => {
    expect([scoreTone(80), scoreTone(79), scoreTone(60), scoreTone(59), scoreTone(null)]).toEqual(["good", "medium", "medium", "bad", "none"]);
    expect([scoreGrade(92), scoreGrade(65), scoreGrade(12)]).toEqual(["良好", "中等", "待加強"]);
  });
});

describe("SeverityDonut", () => {
  it("中心顯示總數，圖例列出每個嚴重度的數量與百分比，只畫有數量的段", () => {
    const { container } = render(<SeverityDonut counts={{ high: 1, medium: 10, low: 6, info: 4 }} />);
    expect(screen.getByRole("img", { name: "共 21 個問題的嚴重程度分布" })).toBeInTheDocument();
    expect(container.querySelectorAll(".dash-donut-seg")).toHaveLength(4);
    const legend = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(legend).toContain("中1048%");
    expect(legend).toContain("嚴重00%");
  });

  it("沒有問題時只畫底環", () => {
    const { container } = render(<SeverityDonut counts={{}} />);
    expect(container.querySelectorAll(".dash-donut-seg")).toHaveLength(0);
    expect(screen.getByRole("img", { name: "共 0 個問題的嚴重程度分布" })).toBeInTheDocument();
  });
});
