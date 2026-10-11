import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CopyButton } from "./CopyButton";

describe("CopyButton", () => {
  afterEach(() => vi.useRealTimers());

  it("複製後顯示已複製，2 秒後恢復原文字", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<CopyButton text="證據內容" label="複製 Evidence" />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "複製 Evidence" }));
    });
    expect(writeText).toHaveBeenCalledWith("證據內容");
    expect(screen.getByRole("button", { name: "已複製" })).toBeTruthy();

    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByRole("button", { name: "複製 Evidence" })).toBeTruthy();
  });

  it("無法複製時顯示複製失敗", async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("x")) } });
    document.execCommand = vi.fn().mockReturnValue(false);
    render(<CopyButton text="x" label="複製給 AI 的提示詞" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "複製給 AI 的提示詞" }));
    });
    expect(screen.getByRole("button", { name: "複製失敗" })).toBeTruthy();
  });
});
