import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PhishingResult from "./PhishingResult.jsx";
import QuickScanResult from "./QuickScanResult.jsx";

describe("QuickScanResult", () => {
  const result = {
    final_url: "https://example.com/",
    overall_score: 58,
    grade: "poor",
    note: "這是單頁快速檢查。",
    categories: [
      { key: "seo", label: "SEO", score: 90 },
      { key: "security", label: "資安", score: 40 },
    ],
    findings: [
      { category: "seo", severity: "low", title: "title 長度不理想", detail: "目前 3 字" },
      { category: "security", severity: "high", title: "未使用 HTTPS", detail: "改用 HTTPS" },
    ],
  };

  it("分數附等級文字，問題依嚴重度排序並標示面向", async () => {
    const onFullScan = vi.fn();
    render(<QuickScanResult result={result} onFullScan={onFullScan} />);
    expect(screen.getByText("不佳")).toBeInTheDocument();
    const items = within(screen.getByText("發現的問題（2）").nextElementSibling).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("高未使用 HTTPS資安");
    expect(items[1]).toHaveTextContent("低title 長度不理想SEO");
    await userEvent.click(screen.getByRole("button", { name: "登入建立完整掃描" }));
    expect(onFullScan).toHaveBeenCalled();
  });
});

describe("PhishingResult", () => {
  it("郵件結果顯示風險等級、長條與寄件資訊", () => {
    render(
      <PhishingResult
        email
        result={{
          risk_score: 82,
          risk_level: "high",
          recommendation: "高風險。不要輸入帳密。",
          from_domain: "paypa1.example",
          reply_to_domain: "",
          url_count: 3,
          attachments: [],
          features: [{ title: "寄件網域與 Reply-To 不一致", evidence: "from=a reply=b", weight: 1.2 }],
        }}
      />,
    );
    expect(screen.getByText("高風險")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "風險分數" })).toHaveAttribute("aria-valuenow", "82");
    expect(screen.getByText("paypa1.example")).toBeInTheDocument();
    expect(screen.getByText("3 個")).toBeInTheDocument();
    expect(screen.getByText("寄件網域與 Reply-To 不一致")).toBeInTheDocument();
  });
});
