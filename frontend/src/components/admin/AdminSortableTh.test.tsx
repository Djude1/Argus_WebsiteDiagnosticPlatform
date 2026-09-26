import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AdminSortableTh } from "./AdminSortableTh";

function renderTh(ordering: string, onChange = vi.fn()) {
  render(
    <table>
      <thead>
        <tr>
          <AdminSortableTh field="amount" ordering={ordering} onChange={onChange}>
            金額
          </AdminSortableTh>
        </tr>
      </thead>
    </table>,
  );
  return { onChange, th: screen.getByRole("columnheader"), button: screen.getByRole("button") };
}

describe("AdminSortableTh", () => {
  it("非排序中的欄位：aria-sort=none，說明文字告訴使用者可以點", () => {
    const { th, button } = renderTh("-created_at");
    expect(th).toHaveAttribute("aria-sort", "none");
    expect(button).toHaveAccessibleName(/點擊依此欄排序/);
  });

  it("第一次點擊用降冪——後台大多要先看最大的幾筆", async () => {
    const user = userEvent.setup();
    const { onChange, button } = renderTh("-created_at");
    await user.click(button);
    expect(onChange).toHaveBeenCalledWith("-amount");
  });

  it("降冪中：aria-sort=descending，再點切成升冪", async () => {
    const user = userEvent.setup();
    const { onChange, th, button } = renderTh("-amount");
    expect(th).toHaveAttribute("aria-sort", "descending");
    expect(button).toHaveAccessibleName(/降冪排序/);
    await user.click(button);
    expect(onChange).toHaveBeenCalledWith("amount");
  });

  it("升冪中：aria-sort=ascending，再點切回降冪", async () => {
    const user = userEvent.setup();
    const { onChange, th, button } = renderTh("amount");
    expect(th).toHaveAttribute("aria-sort", "ascending");
    await user.click(button);
    expect(onChange).toHaveBeenCalledWith("-amount");
  });

  it("欄位名只是前綴相同時不算排序中（amount_total ≠ amount）", () => {
    const { th } = renderTh("-amount_total");
    expect(th).toHaveAttribute("aria-sort", "none");
  });
});
