import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useArgusStore } from "../../store";
import { AccountSetupPage, LoginPage, RequireAuth } from "./AuthPages";

// 註冊一律先經 Google 授權（取得 signup_token），再設定用戶名與密碼；
// Google 登入遇到尚未註冊的帳號（409）直接進入第二步；舊帳號缺用戶名或密碼時導到補設頁。

vi.mock("../../api", () => ({ api: { get: vi.fn(), post: vi.fn() }, setAccessToken: vi.fn() }));
vi.mock("@react-oauth/google", () => ({
  GoogleLogin: ({ onSuccess, text }: { onSuccess: (r: { credential: string }) => void; text: string }) => (
    <button type="button" onClick={() => onSuccess({ credential: "google-cred" })}>google-{text}</button>
  ),
}));
const { api } = vi.mocked(await import("../../api"));
const SIGNUP = { code: "registration_required", signup_token: "tok", email: "ming@example.com", suggested_handle: "ming" };

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockResolvedValue({ data: { enabled: false, site_key: "" } } as never);
  useArgusStore.setState({ accessToken: null, authReady: true, profile: null });
});

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage googleOAuthEnabled />} />
        <Route path="/dashboard" element={<p>dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("註冊流程", () => {
  it("註冊分頁：Google 授權後設定用戶名與密碼才建立帳號", async () => {
    api.post.mockImplementation(((url: string) =>
      Promise.resolve(url === "/auth/register/google/" ? { data: SIGNUP } : { data: { access: "jwt" } })) as never);
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole("tab", { name: "註冊" }));
    expect(screen.queryByLabelText("Email 或用戶名")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "google-signup_with" }));

    expect(await screen.findByDisplayValue("ming@example.com")).toHaveAttribute("readonly");
    const handle = screen.getByLabelText("用戶名");
    expect(handle).toHaveValue("ming");
    await user.clear(handle);
    await user.type(handle, "Ming_01");
    await user.type(screen.getByPlaceholderText("設定密碼"), "StrongPass123!");
    await user.type(screen.getByPlaceholderText("再輸入一次"), "StrongPass123!");
    await user.click(screen.getByRole("button", { name: "建立帳號" }));

    expect(api.post).toHaveBeenLastCalledWith("/auth/register/", {
      signup_token: "tok", handle: "ming_01", password: "StrongPass123!",
    });
    expect(await screen.findByText("dashboard")).toBeInTheDocument();
  });

  it("登入分頁的 Google 遇到未註冊帳號時直接進入設定用戶名與密碼", async () => {
    api.post.mockRejectedValue({ response: { status: 409, data: SIGNUP } });
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole("button", { name: "google-signin_with" }));
    expect(await screen.findByText(/還沒有註冊/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "註冊" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("用戶名")).toHaveValue("ming");
  });

  it("可以用用戶名登入", async () => {
    api.post.mockResolvedValue({ data: { access: "jwt" } } as never);
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText("Email 或用戶名"), "ming");
    await user.type(screen.getByPlaceholderText("輸入密碼"), "StrongPass123!");
    await user.click(screen.getByRole("button", { name: "登入" }));
    expect(api.post).toHaveBeenCalledWith("/auth/email-login/", { email: "ming", password: "StrongPass123!" });
  });
});

describe("舊帳號補設", () => {
  it("缺用戶名與密碼時一律先導到補設頁，完成後回到原本頁面", async () => {
    const needs = { email: "g@example.com", handle: "", has_password: false, needs_setup: true };
    api.get.mockResolvedValueOnce({ data: needs } as never).mockResolvedValue({
      data: { ...needs, handle: "gina", has_password: true, needs_setup: false },
    } as never);
    api.post.mockResolvedValue({ data: {} } as never);
    useArgusStore.setState({ accessToken: "jwt", authReady: true, profile: null });
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<RequireAuth><p>projects</p></RequireAuth>} />
          <Route path="/account/setup" element={<RequireAuth><AccountSetupPage /></RequireAuth>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "完成帳號設定" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("用戶名"), "gina");
    await user.type(screen.getByPlaceholderText("設定密碼"), "StrongPass123!");
    await user.type(screen.getByPlaceholderText("再輸入一次"), "StrongPass123!");
    await user.click(screen.getByRole("button", { name: "完成設定" }));
    expect(api.post).toHaveBeenCalledWith("/auth/me/setup/", { handle: "gina", password: "StrongPass123!" });
    await waitFor(() => expect(screen.getByText("projects")).toBeInTheDocument());
  });
});
