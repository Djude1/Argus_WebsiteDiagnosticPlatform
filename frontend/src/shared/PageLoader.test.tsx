import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PageLoader from "./PageLoader.jsx";

describe("PageLoader", () => {
  it("對輔助技術宣告為載入中並顯示說明文字", () => {
    render(<PageLoader label="載入 SEO 分析中…" />);
    expect(screen.getByRole("status")).toHaveTextContent("載入 SEO 分析中…");
  });

  it("沒給說明時用預設文字", () => {
    render(<PageLoader />);
    expect(screen.getByRole("status")).toHaveTextContent("載入中…");
  });
});
