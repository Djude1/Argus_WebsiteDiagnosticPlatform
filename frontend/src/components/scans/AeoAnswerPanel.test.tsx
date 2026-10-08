import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AeoAnswerPanel } from "./AeoAnswerPanel";

const evaluated = {
  status: "evaluated",
  questions_total: 2,
  answered_ratio: 0.5,
  evidence_ratio: 1,
  counts: { answered: 1, insufficient: 1, conflict: 0, missing: 0 },
  questions: [
    {
      key: "contact_phone", text: "聯絡電話是多少？", verdict: "answered", verdict_label: "可回答",
      reason: "找到具體答案：02-2322-6000",
      confidence: "confirmed", confidence_label: "確認",
      limitation: "答案值逐字出現在引用的原文中；仍需確認是否為最新資訊。",
      evidence: [{ url: "https://x.example/", location: "頁尾", quote: "聯絡電話：02-2322-6000" }],
    },
    {
      key: "apply_deadline", text: "申請或報名截止日期是何時？", verdict: "insufficient",
      verdict_label: "資訊不足", reason: "有提到日期但沒有標明年度", evidence: [],
    },
  ],
};

describe("AeoAnswerPanel", () => {
  it("未充分評估時只顯示原因，不顯示題數與比例", () => {
    render(<AeoAnswerPanel report={{ status: "insufficient", reason: "正文合計只有 20 字" }} />);
    expect(screen.getByText(/未充分評估：正文合計只有 20 字/)).toBeInTheDocument();
    expect(screen.queryByText("可回答")).not.toBeInTheDocument();
  });

  it("沒有檢測結果（舊掃描）時不顯示", () => {
    const { container } = render(<AeoAnswerPanel report={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("展開題目後顯示判定理由與原文證據", async () => {
    const user = userEvent.setup();
    render(<AeoAnswerPanel report={evaluated} />);
    expect(screen.getByText(/有答案的問題比例 50%/)).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /聯絡電話是多少？/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("聯絡電話：02-2322-6000")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://x.example/" })).toHaveAttribute("target", "_blank");
  });
});

describe("AeoAnswerPanel 的 AEO 問答分頁模式（withFilter）", () => {
  it("可依判定篩選題目；沒有符合時提示", async () => {
    const user = userEvent.setup();
    render(<AeoAnswerPanel report={evaluated} withFilter />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "資訊不足 1" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("申請或報名截止日期是何時？")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "衝突 0" }));
    expect(screen.getByText("沒有符合的題目。")).toBeInTheDocument();
  });

  it("不重複顯示標題與計數（頁首已有）", () => {
    render(<AeoAnswerPanel report={evaluated} withFilter />);
    expect(screen.queryByRole("heading", { name: "AEO 問答檢測" })).not.toBeInTheDocument();
    expect(screen.queryByText(/有答案的問題比例/)).not.toBeInTheDocument();
  });

  it("可回答的題目顯示可信度與判定限制；沒有可信度的題目不顯示", async () => {
    const user = userEvent.setup();
    render(<AeoAnswerPanel report={evaluated} />);
    expect(screen.getAllByText(/可信度：/)).toHaveLength(1);
    expect(screen.getByText("可信度：確認")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /聯絡電話是多少/ }));
    expect(screen.getByText(/判定限制：答案值逐字出現在引用的原文中/)).toBeInTheDocument();
  });
});

describe("AeoAnswerPanel 的引用可得性", () => {
  const withCitation = {
    ...evaluated,
    citation: { counts: { citable: 0, limited: 0, not_citable: 1 }, citable_ratio: 0 },
    questions: [
      {
        ...evaluated.questions[0],
        citation: {
          status: "not_citable", label: "無法被引用",
          reasons: ["頁面禁止擷取摘要（nosnippet，meta robots）"],
        },
      },
      evaluated.questions[1],
    ],
  };

  it("只標出無法或受限引用的題目，展開後列出原因，並顯示可引用比例", async () => {
    const user = userEvent.setup();
    render(<AeoAnswerPanel report={withCitation} />);
    expect(screen.getByText(/答案可被搜尋引擎與 AI 引用的比例 0%/)).toBeInTheDocument();
    expect(screen.getAllByText("無法被引用")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /聯絡電話是多少/ }));
    expect(screen.getByText(/無法被引用：頁面禁止擷取摘要/)).toBeInTheDocument();
  });

  it("可被引用的題目不另加標示；舊報告沒有引用資料時不顯示比例", () => {
    const citable = {
      ...evaluated,
      questions: [
        { ...evaluated.questions[0], citation: { status: "citable", label: "可被引用", reasons: [] } },
      ],
    };
    render(<AeoAnswerPanel report={citable} />);
    expect(screen.queryByText("可被引用")).not.toBeInTheDocument();
    expect(screen.queryByText(/引用的比例/)).not.toBeInTheDocument();
  });
});
