import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AdminEmptyState, AdminErrorState, AdminSkeleton } from "./AdminStates";

describe("AdminSkeleton", () => {
  it("對輔助技術宣告為載入中", () => {
    render(<AdminSkeleton label="載入使用者" />);
    expect(screen.getByRole("status")).toHaveTextContent("載入使用者");
  });

  it("table 變體依 rows 產生列數（加一列表頭）", () => {
    const { container } = render(<AdminSkeleton variant="table" rows={4} />);
    expect(container.querySelectorAll(".admin-skeleton-row")).toHaveLength(5);
  });
});

describe("AdminEmptyState", () => {
  it("有 actionLabel 與 onAction 時給出口", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    render(<AdminEmptyState title="沒有符合的結果" actionLabel="清除篩選" onAction={onAction} />);
    await user.click(screen.getByRole("button", { name: "清除篩選" }));
    expect(onAction).toHaveBeenCalled();
  });

  it("只有 actionLabel 沒有 onAction 時不放一顆按了沒反應的按鈕", () => {
    render(<AdminEmptyState title="尚無資料" actionLabel="建立" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("AdminErrorState", () => {
  it("以 role=alert 宣告，無訊息時用預設文字", () => {
    render(<AdminErrorState />);
    expect(screen.getByRole("alert")).toHaveTextContent("載入失敗");
  });

  it("有 onRetry 時一定有重試鍵——錯誤永遠要留下一步", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<AdminErrorState message="訂單載入失敗" onRetry={onRetry} />);
    await user.click(screen.getByRole("button", { name: "重試" }));
    expect(onRetry).toHaveBeenCalled();
  });
});
