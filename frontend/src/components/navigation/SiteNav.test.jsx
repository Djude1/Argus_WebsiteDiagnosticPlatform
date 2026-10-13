import { act, render, screen, within } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import SiteNav, { SiteThemeToggle } from "./SiteNav";
import { ThemeToggle } from "./NavActions";
import { useArgusStore } from "../../store";

function renderNav(items = [{ to: "/project", label: "產品介紹" }, { to: "/download", label: "下載 APP" }]) {
  return render(<MemoryRouter initialEntries={["/project"]}><SiteNav items={items} actions={null} /></MemoryRouter>);
}

describe("公開頁行動導覽", () => {
  it("展開後可用 Escape 收合並把焦點還給選單按鈕", async () => {
    const user = userEvent.setup();
    renderNav();
    const button = screen.getByRole("button", { name: "開啟導覽選單" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    screen.getByRole("link", { name: "下載 APP" }).focus();
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();
  });

  it("選擇頁面後收合且更新目前頁面", async () => {
    const user = userEvent.setup();
    renderNav();
    const button = screen.getByRole("button", { name: "開啟導覽選單" });
    await user.click(button);
    const download = screen.getByRole("link", { name: "下載 APP" });
    await user.click(download);
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(download).toHaveAttribute("aria-current", "page");
  });

  it("沒有公開頁連結的會員工具列不出現空選單", () => {
    renderNav([]);
    expect(screen.queryByRole("button", { name: "開啟導覽選單" })).not.toBeInTheDocument();
  });
});

describe("日間偏好的預先渲染接手", () => {
  for (const { Component, label } of [
    { Component: SiteThemeToggle, label: "切換至夜間模式" },
    { Component: ThemeToggle, label: "切換為夜間主題" },
  ]) {
    it(`${label} 不會因日夜圖示不同而重畫`, async () => {
      useArgusStore.setState({ theme: "dark" });
      const container = document.createElement("div");
      container.innerHTML = renderToString(<Component />);
      document.body.append(container);
      useArgusStore.setState({ theme: "light" });
      const errors = [];
      let root;
      await act(async () => {
        root = hydrateRoot(container, <Component />, { onRecoverableError: (error) => errors.push(error) });
      });
      expect(errors).toEqual([]);
      expect(within(container).getByRole("button", { name: label })).toBeInTheDocument();
      await act(async () => root.unmount());
      container.remove();
      useArgusStore.setState({ theme: "dark" });
    });
  }
});
