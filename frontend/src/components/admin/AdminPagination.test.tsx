import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AdminPagination } from "./AdminPagination";

describe("AdminPagination", () => {
  it("只有一頁時仍顯示總筆數——使用者要知道「就這麼多」而不是懷疑被截斷", () => {
    render(<AdminPagination page={1} totalPages={1} total={12} onChange={vi.fn()} />);
    expect(screen.getByText("共 12 筆")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("沒有資料時什麼都不顯示", () => {
    const { container } = render(
      <AdminPagination page={1} totalPages={1} total={0} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("總筆數用千分位", () => {
    render(<AdminPagination page={2} totalPages={50} total={1234} onChange={vi.fn()} />);
    expect(screen.getByText(/共 1,234 筆/)).toBeInTheDocument();
    expect(screen.getByText(/2 \/ 50/)).toBeInTheDocument();
  });

  it("第一頁不能再往前，最後一頁不能再往後", () => {
    const { rerender } = render(
      <AdminPagination page={1} totalPages={3} total={60} onChange={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /上一頁/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /下一頁/ })).toBeEnabled();

    rerender(<AdminPagination page={3} totalPages={3} total={60} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /上一頁/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /下一頁/ })).toBeDisabled();
  });

  it("點擊回報目標頁碼", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<AdminPagination page={2} totalPages={5} total={100} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /下一頁/ }));
    expect(onChange).toHaveBeenLastCalledWith(3);
    await user.click(screen.getByRole("button", { name: /上一頁/ }));
    expect(onChange).toHaveBeenLastCalledWith(1);
  });
});
