import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScoreBreakdownPanel } from "./ScoreBreakdownPanel";

const DATA = {
  available: true,
  overall_score: 65,
  scoring_version: "2",
  current_scoring_version: "2",
  decay_constant: 50,
  weights: { critical: 60, high: 35, medium: 12, low: 4, info: 0 },
  matches: true,
  categories: [
    {
      category: "seo",
      score: 73,
      recomputed_score: 73,
      base: 100,
      base_source: "",
      penalty: 16,
      deductions: [
        { rule_id: "seo-a", title: "缺少 meta description", severity: "medium", weight: 12, occurrences: 3, score_without: 92 },
        { rule_id: "seo-b", title: "圖片缺少 alt", severity: "low", weight: 4, occurrences: 1, score_without: 79 },
      ],
      in_base: 0,
      info: 2,
      coverage: "completed",
      incomplete_checks: [],
    },
    {
      category: "aeo",
      score: 80,
      recomputed_score: 80,
      base: 80,
      base_source: "aeo_answerability",
      penalty: 0,
      deductions: [],
      in_base: 4,
      info: 0,
      coverage: "partial",
      incomplete_checks: ["AEO 問答檢測"],
    },
  ],
};

describe("ScoreBreakdownPanel", () => {
  it("逐維度列出基準分、扣分項目、只修好該項的分數與未完成檢查", () => {
    render(<ScoreBreakdownPanel data={DATA} />);
    expect(screen.getByText("缺少 meta description")).toBeInTheDocument();
    expect(screen.getByText("3 處")).toBeInTheDocument();
    expect(screen.getByText("92 分")).toBeInTheDocument();
    expect(screen.getByText(/扣分權重合計 16/)).toBeInTheDocument();
    expect(screen.getByText(/可回答性分數/)).toBeInTheDocument();
    expect(screen.getByText(/4 筆逐題問答結果已反映在基準分/)).toBeInTheDocument();
    expect(screen.getByText("部分評估")).toBeInTheDocument();
    expect(screen.getByText(/沒有完整完成的檢查：AEO 問答檢測/)).toBeInTheDocument();
    expect(screen.queryByText(/較早版本的計分規則/)).not.toBeInTheDocument();
  });

  it("舊公式算的分數會提示，未計分時顯示說明", () => {
    const { unmount } = render(<ScoreBreakdownPanel data={{ ...DATA, matches: false }} />);
    expect(screen.getByText(/較早版本的計分規則/)).toBeInTheDocument();
    unmount();
    render(<ScoreBreakdownPanel data={{ ...DATA, available: false, categories: [] }} />);
    expect(screen.getByText(/掃描完成並計分後/)).toBeInTheDocument();
  });
});
