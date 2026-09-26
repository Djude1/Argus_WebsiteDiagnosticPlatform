import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FormEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { AdminField, AdminModal } from "./AdminModal";

// AdminModal 的註解承諾了幾件事：Esc 與遮罩可關、focus 被困在對話框內、
// 關閉後 focus 回到原處、傳 onSubmit 時 Enter 能送出。這裡逐一驗證。

function Harness({ onClose = vi.fn(), open = true, onSubmit }: {
  onClose?: () => void;
  open?: boolean;
  onSubmit?: (e: FormEvent) => void;
}) {
  return (
    <>
      <button type="button">開啟前的焦點</button>
      <AdminModal
        open={open}
        onClose={onClose}
        title="調整點數"
        onSubmit={onSubmit}
        footer={<button type="submit">確認</button>}
      >
        <input aria-label="數量" />
      </AdminModal>
    </>
  );
}

describe("AdminModal", () => {
  it("open=false 時完全不渲染", () => {
    render(<Harness open={false} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("以 title 作為對話框的可及名稱", () => {
    render(<Harness />);
    expect(screen.getByRole("dialog", { name: "調整點數" })).toHaveAttribute("aria-modal", "true");
  });

  it("開啟時 focus 移到第一個可聚焦元素（關閉鈕）", () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: "關閉" })).toHaveFocus();
  });

  it("Esc 關閉", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("點遮罩關閉，但點對話框內部不關閉", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);

    await user.click(screen.getByRole("textbox", { name: "數量" }));
    expect(onClose).not.toHaveBeenCalled();

    const backdrop = screen.getByRole("dialog").parentElement!;
    await user.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Tab 在對話框內循環，不會跑到背後的頁面", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const close = screen.getByRole("button", { name: "關閉" });
    const input = screen.getByRole("textbox", { name: "數量" });
    const submit = screen.getByRole("button", { name: "確認" });

    expect(close).toHaveFocus();
    await user.tab();
    expect(input).toHaveFocus();
    await user.tab();
    expect(submit).toHaveFocus();
    await user.tab(); // 最後一個 → 繞回第一個
    expect(close).toHaveFocus();
    await user.tab({ shift: true }); // 第一個往回 → 最後一個
    expect(submit).toHaveFocus();
  });

  it("關閉後 focus 回到開啟前的元素", () => {
    const { rerender } = render(<Harness open={false} />);
    const trigger = screen.getByRole("button", { name: "開啟前的焦點" });
    trigger.focus();

    rerender(<Harness open />);
    expect(trigger).not.toHaveFocus();
    rerender(<Harness open={false} />);
    expect(trigger).toHaveFocus();
  });

  it("傳 onSubmit 時包成 form，輸入框按 Enter 即送出", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn((e: FormEvent) => e.preventDefault());
    render(<Harness onSubmit={onSubmit} />);
    await user.type(screen.getByRole("textbox", { name: "數量" }), "100{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});

describe("AdminField", () => {
  it("label 綁到輸入元件，提示與錯誤都用 aria-describedby 連上——讀螢幕軟體才唸得到", () => {
    render(
      <AdminField id="amt" label="數量" hint="正數為加點" error="不可為 0" required>
        {(props: Record<string, string | undefined>) => <input {...props} />}
      </AdminField>,
    );
    const input = screen.getByLabelText(/數量/);
    expect(input).toHaveAccessibleDescription("正數為加點 不可為 0");
    expect(screen.getByText("（必填）")).toBeInTheDocument();
  });

  it("沒有提示也沒有錯誤時不帶空的 aria-describedby", () => {
    render(
      <AdminField id="n" label="名稱">
        {(props: Record<string, string | undefined>) => <input {...props} />}
      </AdminField>,
    );
    expect(screen.getByLabelText("名稱")).not.toHaveAttribute("aria-describedby");
  });
});
