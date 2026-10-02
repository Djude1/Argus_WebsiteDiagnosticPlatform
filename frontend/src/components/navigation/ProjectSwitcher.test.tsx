import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectHomeRedirect } from "../../features/projects/ProjectWorkspace";
import { useArgusStore } from "../../store";
import { ProjectSwitcher, projectSwitchPath } from "./ProjectSwitcher";

vi.mock("../../api", () => ({ api: { get: vi.fn(), post: vi.fn() }, setAccessToken: vi.fn() }));
const { api } = vi.mocked(await import("../../api"));

function project(id: number, name: string, score: number | null = null) {
  return {
    id, name, origin: `https://${name}`, hostname: name, start_url: `https://${name}/`, archived_at: null,
    summary: { latest_score: score },
  };
}
const PROJECTS = [project(1, "a.example", 82), project(2, "b.example")];

function Location() {
  return <p data-testid="location">{useLocation().pathname}</p>;
}

function renderAt(path: string, element: ReactElement) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      {element}
      <Routes>
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useArgusStore.setState({ accessToken: "t", projects: PROJECTS, currentProjectId: 1 });
});

describe("projectSwitchPath", () => {
  it("切換時停留在同一個分頁；掃描詳情與其他頁面回到總覽", () => {
    expect(projectSwitchPath("/projects/1/issues", 2)).toBe("/projects/2/issues");
    expect(projectSwitchPath("/projects/1/pages", 2)).toBe("/projects/2/pages");
    expect(projectSwitchPath("/projects/1", 2)).toBe("/projects/2");
    expect(projectSwitchPath("/scans/9/topology", 2)).toBe("/projects/2");
    expect(projectSwitchPath("/billing", 2)).toBe("/projects/2");
  });
});

describe("ProjectSwitcher", () => {
  it("顯示目前專案，切換到另一個專案後記住它並留在同一個分頁", async () => {
    const user = userEvent.setup();
    renderAt("/projects/1/issues", <ProjectSwitcher />);
    const trigger = screen.getByRole("button", { name: /a\.example/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    await user.click(screen.getByRole("menuitem", { name: /https:\/\/b\.example/ }));
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/2/issues");
    expect(useArgusStore.getState().currentProjectId).toBe(2);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("每個專案顯示最新分數與設定入口，從設定入口進入會切換目前專案", async () => {
    const user = userEvent.setup();
    renderAt("/projects/1", <ProjectSwitcher />);
    await user.click(screen.getByRole("button", { name: /a\.example/ }));
    expect(screen.getByRole("menuitem", { name: /a\.example.*82/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /b\.example.*—/ })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "b.example 的專案設定" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/2/settings");
    expect(useArgusStore.getState().currentProjectId).toBe(2);
  });

  it("專案多時可搜尋，方向鍵在選項間移動", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 8 }, (_, i) => project(i + 1, `site${i + 1}.example`));
    useArgusStore.setState({ projects: many, currentProjectId: 1 });
    renderAt("/projects/1", <ProjectSwitcher />);
    await user.click(screen.getByRole("button", { name: /site1\.example/ }));
    const search = screen.getByRole("searchbox", { name: "搜尋網站專案" });
    expect(search).toHaveFocus();
    await user.type(search, "site7");
    expect(screen.getAllByRole("menuitem", { name: /https:\/\/site\d\.example/ }).map((el) => el.textContent))
      .toEqual([expect.stringContaining("site7.example")]);
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: /https:\/\/site7\.example/ })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "site7.example 的專案設定" })).toHaveFocus();
  });

  it("新增專案入口與 Esc 關閉", async () => {
    const user = userEvent.setup();
    renderAt("/projects/1", <ProjectSwitcher />);
    await user.click(screen.getByRole("button", { name: /a\.example/ }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /a\.example/ }));
    await user.click(screen.getByRole("menuitem", { name: "＋ 新增專案" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/new");
  });
});

describe("ProjectHomeRedirect（舊入口 /dashboard、/scans、/history）", () => {
  it("轉到目前專案的對應分頁", async () => {
    useArgusStore.setState({ projects: null, currentProjectId: 2 });
    api.get.mockResolvedValue({ data: PROJECTS });
    render(
      <MemoryRouter initialEntries={["/scans"]}>
        <Routes>
          <Route path="/scans" element={<ProjectHomeRedirect section="scans" />} />
          <Route path="*" element={<Location />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("location")).toHaveTextContent("/projects/2/scans");
    expect(api.get).toHaveBeenCalledWith("/projects/");
  });

  it("記住的專案已不在清單時用第一個；沒有任何專案時引導新增", async () => {
    useArgusStore.setState({ currentProjectId: 99 });
    const { unmount } = render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<ProjectHomeRedirect />} />
          <Route path="*" element={<Location />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/1");
    unmount();
    useArgusStore.setState({ projects: [] });
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<ProjectHomeRedirect />} />
          <Route path="*" element={<Location />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/projects/new");
  });
});
