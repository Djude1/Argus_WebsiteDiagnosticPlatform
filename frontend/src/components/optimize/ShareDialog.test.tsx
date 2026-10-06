import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../api";
import ShareDialog from "./ShareDialog";

vi.mock("../../api", () => ({ api: { post: vi.fn(), delete: vi.fn() }, setAccessToken: vi.fn() }));

const PRIVATE = { id: 7, share_path: "", share_active: false, share_access: "private" };

describe("ShareDialog", () => {
  it("選擇「知道連結的任何人」才產生連結，之後可以複製", async () => {
    const shared = { ...PRIVATE, share_path: "/optimized/abc", share_active: true, share_access: "link" };
    vi.mocked(api.post).mockResolvedValue({ data: shared });
    const onChange = vi.fn();
    const { rerender } = render(<ShareDialog rebuild={PRIVATE} onChange={onChange} onClose={() => {}} />);
    expect(screen.getByRole("button", { name: "複製連結" })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /知道連結的任何人/ }));
    expect(api.post).toHaveBeenCalledWith("/rebuilds/7/share/", { access: "link" });
    expect(onChange).toHaveBeenCalledWith(shared);
    rerender(<ShareDialog rebuild={shared} onChange={onChange} onClose={() => {}} />);
    expect(screen.getByRole("textbox", { name: "分享連結" })).toHaveValue(`${window.location.origin}/optimized/abc`);
    expect(screen.getByRole("button", { name: "複製連結" })).toBeEnabled();
  });

  it("改回「僅限我」就是關閉分享；Esc 可關閉對話框", async () => {
    const shared = { ...PRIVATE, share_path: "/optimized/abc", share_active: true, share_access: "link" };
    vi.mocked(api.delete).mockResolvedValue({ data: { ...shared, share_active: false, share_access: "private" } });
    const onClose = vi.fn();
    render(<ShareDialog rebuild={shared} onChange={() => {}} onClose={onClose} />);
    await userEvent.click(screen.getByRole("radio", { name: /僅限我/ }));
    expect(api.delete).toHaveBeenCalledWith("/rebuilds/7/share/");
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
