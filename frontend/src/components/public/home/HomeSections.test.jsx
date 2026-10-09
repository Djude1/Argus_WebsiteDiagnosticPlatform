import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LockIcon, ShieldIcon } from "../../../shared/LineIcons.jsx";
import CompareSlider from "./CompareSlider.jsx";
import CoverageTabs from "./CoverageTabs.jsx";
import ProcessStack from "./ProcessStack.jsx";
import ReportPreview from "./ReportPreview.jsx";

const STEPS = [
  { Icon: LockIcon, short: "授權", title: "授權與網域驗證", desc: "a" },
  { Icon: ShieldIcon, short: "走訪", title: "真實瀏覽器走訪", desc: "b" },
  { Icon: LockIcon, short: "排序", title: "證據與優先順序", desc: "c" },
];

describe("ProcessStack", () => {
  it("按步驟按鈕會把該步驟換到最前面", () => {
    render(<ProcessStack steps={STEPS} />);
    const third = screen.getByRole("button", { name: "步驟 3：證據與優先順序" });
    fireEvent.click(third);
    expect(third).toHaveAttribute("aria-pressed", "true");
    // 只有最前面那張卡對輔助技術可見
    expect(screen.getByRole("heading", { name: "證據與優先順序" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "授權與網域驗證" })).not.toBeInTheDocument();
  });
});

describe("CoverageTabs", () => {
  const items = [
    { key: "seo", code: "SEO", name: "搜尋可見度", Icon: LockIcon, desc: "x", checks: ["title"] },
    { key: "ux", code: "UX", name: "使用體驗", Icon: ShieldIcon, desc: "y", checks: ["axe"] },
  ];

  it("方向鍵切換面向，面板跟著換", () => {
    render(<CoverageTabs items={items} />);
    const first = screen.getByRole("tab", { name: /SEO/ });
    expect(first).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(screen.getByRole("tab", { name: /UX/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("使用體驗");
  });
});

describe("ReportPreview", () => {
  it("點問題會顯示該問題的證據", () => {
    render(<ReportPreview />);
    fireEvent.click(screen.getByRole("button", { name: /表單欄位沒有標籤/ }));
    expect(screen.getByText('<input type="email" placeholder="Email">')).toBeInTheDocument();
  });
});

describe("CompareSlider", () => {
  it("可以用滑桿（鍵盤或拖曳）調整對照位置", () => {
    render(<CompareSlider />);
    const slider = screen.getByRole("slider", { name: "拖曳比較原始頁面與優化後頁面" });
    fireEvent.change(slider, { target: { value: "30" } });
    expect(slider).toHaveValue("30");
  });
});
