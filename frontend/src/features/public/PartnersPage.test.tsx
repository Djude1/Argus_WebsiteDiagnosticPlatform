import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PartnersPage } from "./PartnersPage";

// 洽談表單的承諾：送出後有明確成功回饋；後端欄位錯誤會標在對應欄位旁。

vi.mock("../../api", () => ({ api: { post: vi.fn() } }));
const { api } = vi.mocked(await import("../../api"));

function renderPage() {
  return render(
    <MemoryRouter>
      <PartnersPage />
    </MemoryRouter>,
  );
}

async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/^姓名/), "王小明");
  await user.type(screen.getByLabelText(/^公司 \*/), "範例數位");
  await user.type(screen.getByLabelText(/^工作信箱/), "ming@example.com");
  await user.type(screen.getByLabelText(/^需求說明/), "交付前想附上健檢報告");
}

describe("PartnersPage 洽談表單", () => {
  beforeEach(() => vi.clearAllMocks());

  it("送出成功後顯示成功訊息", async () => {
    api.post.mockResolvedValue({ data: { detail: "已收到你的洽談需求，我們會以 Email 與你聯繫。" } });
    const user = userEvent.setup();
    renderPage();
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "送出洽談需求" }));

    expect(await screen.findByRole("heading", { name: "已收到你的洽談需求" })).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith(
      "/content/partner-inquiries/",
      expect.objectContaining({ company: "範例數位", partner_type: "agency", website: "" }),
    );
  });

  it("後端回 400 時把錯誤標在欄位旁", async () => {
    api.post.mockRejectedValue({ response: { status: 400, data: { email: ["請輸入有效的電子郵件地址。"] } } });
    const user = userEvent.setup();
    renderPage();
    await fillRequired(user);
    await user.click(screen.getByRole("button", { name: "送出洽談需求" }));

    expect(await screen.findByText("請輸入有效的電子郵件地址。")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("請檢查標示的欄位");
  });
});
