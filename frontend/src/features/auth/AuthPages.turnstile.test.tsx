import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { LoginPage, PasswordResetRequestPage } from "./AuthPages";

// 啟用 Turnstile 時的承諾：通過人機驗證前不能送出；token 跟著請求送到後端；
// 每次送出後重設元件（token 只能用一次）；忘記密碼被 403 擋下時留在表單顯示原因。

vi.mock("../../api", () => ({ api: { get: vi.fn(), post: vi.fn() }, setAccessToken: vi.fn() }));
vi.mock("@react-oauth/google", () => ({ GoogleLogin: () => null }));
const { api } = vi.mocked(await import("../../api"));

type RenderOptions = { action: string; callback: (token: string) => void };
const turnstile = {
  render: vi.fn((_el: HTMLElement, options: RenderOptions) => {
    turnstile.last = options;
    return "widget-1";
  }),
  reset: vi.fn(),
  remove: vi.fn(),
  last: null as RenderOptions | null,
};

function solve(token: string) {
  act(() => turnstile.last?.callback(token));
}

beforeEach(() => {
  vi.clearAllMocks();
  (window as unknown as { turnstile: typeof turnstile }).turnstile = turnstile;
  api.get.mockResolvedValue({ data: { enabled: true, site_key: "0x4AAAAAAA-test" } } as never);
  useArgusStore.setState({ accessToken: null });
});

describe("LoginPage 人機驗證", () => {
  it("驗證完成前登入鈕停用，送出時附上 token，失敗後重設元件", async () => {
    api.post.mockRejectedValue({ response: { status: 403, data: { detail: "人機驗證未通過或已過期，請重新驗證後再送出。" } } });
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage googleOAuthEnabled={false} />
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText("Email"), "member@example.com");
    await user.type(screen.getByPlaceholderText("輸入密碼"), "StrongPass123!");
    const submit = screen.getByRole("button", { name: "登入" });
    expect(submit).toBeDisabled();
    expect(turnstile.render).toHaveBeenCalledWith(expect.any(HTMLElement), expect.objectContaining({ sitekey: "0x4AAAAAAA-test", action: "login" }));

    solve("token-abc");
    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(api.post).toHaveBeenCalledWith("/auth/email-login/", {
      email: "member@example.com",
      password: "StrongPass123!",
      "cf-turnstile-response": "token-abc",
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("人機驗證未通過");
    expect(turnstile.reset).toHaveBeenCalledWith("widget-1");
    expect(submit).toBeDisabled();
  });

  it("切到新帳號分頁時改用 signup 動作", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage googleOAuthEnabled={false} />
      </MemoryRouter>,
    );
    await screen.findByRole("button", { name: "登入" });
    await user.click(screen.getByRole("tab", { name: "新帳號" }));
    expect(turnstile.last?.action).toBe("signup");
    expect(screen.getByRole("button", { name: "建立帳號" })).toBeDisabled();
  });
});

describe("PasswordResetRequestPage 人機驗證", () => {
  it("被 403 擋下時留在表單顯示原因，不顯示「已寄出」", async () => {
    api.post.mockRejectedValue({ response: { status: 403, data: { detail: "人機驗證未通過或已過期，請重新驗證後再送出。" } } });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <PasswordResetRequestPage />
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText("Email"), "member@example.com");
    await screen.findByRole("button", { name: "寄出重設連結" });
    expect(turnstile.last?.action).toBe("password_reset");
    solve("token-xyz");
    await user.click(screen.getByRole("button", { name: "寄出重設連結" }));
    expect(api.post).toHaveBeenCalledWith("/auth/password-reset/request/", {
      email: "member@example.com",
      "cf-turnstile-response": "token-xyz",
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("人機驗證未通過");
    expect(screen.getByRole("button", { name: "寄出重設連結" })).toBeDisabled();
  });
});
