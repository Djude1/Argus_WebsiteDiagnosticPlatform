import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { CoinHistory } from "./CoinHistory";

// 點數紀錄的承諾：每筆顯示項目、正負點數與餘額；掃描相關的交易可連到該次掃描；沒有紀錄時明講。

describe("CoinHistory", () => {
  it("列出掃描預扣與結算退款，並連到掃描", () => {
    render(
      <MemoryRouter>
        <CoinHistory
          transactions={[
            { id: 2, kind_label: "掃描退款", amount: 14, balance_after: 494, scan_job: 7,
              scan_origin: "https://example.com", created_at: "2026-10-08T02:00:00Z" },
            { id: 1, kind_label: "掃描預扣", amount: -20, balance_after: 480, scan_job: 7,
              scan_origin: "https://example.com", created_at: "2026-10-08T01:00:00Z" },
          ]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("+14")).toBeInTheDocument();
    expect(screen.getByText("-20")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "https://example.com" });
    expect(links[0]).toHaveAttribute("href", "/scans/7");
  });

  it("沒有紀錄時顯示說明", () => {
    render(<MemoryRouter><CoinHistory transactions={[]} /></MemoryRouter>);
    expect(screen.getByText("還沒有點數紀錄。")).toBeInTheDocument();
  });
});
