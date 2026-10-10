import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import { AiInsightPanel, AiTriageNote, type AiInsight } from "./AiInsightPanel";

vi.mock("../../api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const ready: AiInsight = {
  status: "ready",
  summary: "網站整體穩定，主要問題在安全標頭。",
  priorities: [
    { title: "補上 HSTS", why: "避免降級攻擊", how: "在伺服器設定加入標頭", rule_ids: ["hsts"] },
  ],
  triage: [
    { rule_id: "pii", title: "頁面外洩個人資料", verdict: "possible_false_positive",
      label: "可能是誤報", reason: "號碼像是圖片檔名" },
  ],
};

const findings = [
  { id: 1, rule_id: "hsts", title: "缺少 HSTS" },
  { id: 2, rule_id: "pii", title: "頁面外洩個人資料" },
];

describe("AiInsightPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("標明是 AI 產生、不影響分數，並顯示診斷、優先處理與複核", async () => {
    const onSelectRule = vi.fn();
    render(
      <AiInsightPanel
        scan={{ id: 9, status: "completed", ai_insight: ready }}
        findings={findings}
        onSelectRule={onSelectRule}
      />,
    );
    expect(screen.getByText("AI 產生，僅供參考，不影響分數")).toBeInTheDocument();
    expect(screen.getByText(ready.summary ?? "")).toBeInTheDocument();
    expect(screen.getByText("補上 HSTS")).toBeInTheDocument();
    expect(screen.getByText("可能是誤報")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "缺少 HSTS" }));
    expect(onSelectRule).toHaveBeenCalledWith("hsts");
  });

  it("沒有結果時可以產生，失敗時顯示原因", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { ai_insight: { status: "generating" } } });
    const { rerender } = render(
      <AiInsightPanel scan={{ id: 9, status: "completed", ai_insight: {} }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "產生 AI 解讀" }));
    expect(api.post).toHaveBeenCalledWith("/scans/9/ai-insight/");
    expect(await screen.findByRole("status")).toHaveTextContent("AI 正在閱讀");

    rerender(
      <AiInsightPanel
        scan={{ id: 10, status: "completed", ai_insight: { status: "failed", reason: "AI 服務暫時無法使用" } }}
      />,
    );
    expect(screen.getByText(/AI 服務暫時無法使用/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新產生" })).toBeInTheDocument();
  });

  it("掃描還沒完成時不顯示", () => {
    const { container } = render(<AiInsightPanel scan={{ id: 9, status: "scanning", ai_insight: {} }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("AiTriageNote", () => {
  it("只在選中的問題有複核時顯示", () => {
    const { rerender } = render(<AiTriageNote insight={ready} finding={{ rule_id: "pii" }} />);
    expect(screen.getByText("AI 複核：可能是誤報")).toBeInTheDocument();
    rerender(<AiTriageNote insight={ready} finding={{ rule_id: "hsts" }} />);
    expect(screen.queryByText(/AI 複核/)).not.toBeInTheDocument();
  });
});
