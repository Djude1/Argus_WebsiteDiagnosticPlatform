import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { issuesToCsv, ProjectPagesPage } from "./ProjectPages";

vi.mock("../../api", () => ({ api: { get: vi.fn() }, setAccessToken: vi.fn() }));
const { api } = vi.mocked(await import("../../api"));

const PROJECT = { id: 7, name: "a.example", hostname: "a.example", origin: "https://a.example" };

function page(id: number, overrides: Record<string, unknown>) {
  return {
    id, url: `https://a.example/p${id}`, title: `頁 ${id}`, status_code: 200, load_time_ms: 800,
    depth: 1, blocked_reason: "", has_screenshot: false, findings: 0, max_severity: null,
    by_category: {}, ...overrides,
  };
}

function renderPagesTab() {
  return render(
    <MemoryRouter initialEntries={["/projects/7/pages"]}>
      <Routes>
        <Route path="/projects/:projectId" element={<Outlet context={{ project: PROJECT }} />}>
          <Route path="pages" element={<ProjectPagesPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.get.mockImplementation(async (url: string) => {
    if (url === "/projects/7/pages/") {
      return {
        data: {
          scan: { id: 3, completed_at: "2026-10-01T00:00:00Z", categories: ["seo"] },
          site_level_findings: 2,
          pages: [
            page(1, { findings: 1, max_severity: "low", by_category: { seo: 1 } }),
            page(2, { findings: 3, max_severity: "high", by_category: { seo: 3 } }),
            page(3, { status_code: 404, load_time_ms: 4200 }),
          ],
        },
      };
    }
    return { data: { results: [] } };
  });
});

describe("issuesToCsv", () => {
  it("跳脫逗號、引號與換行，並以 BOM 開頭讓 Excel 正確顯示中文", () => {
    const csv = issuesToCsv([
      {
        severity: "high", category: "seo", title: '標題含 "引號", 與逗號', status: "new",
        streak: 2, pages: 1, urls: ["https://a.example/"], remediation: "第一行\n第二行", rule_id: "r1",
      },
    ]);
    expect(csv.startsWith("﻿")).toBe(true);
    const [header = "", row = ""] = csv.slice(1).split("\r\n");
    expect(header.split(",")[0]).toBe("嚴重度");
    expect(row).toContain('"標題含 ""引號"", 與逗號"');
    expect(row).toContain('"第一行\n第二行"');
    expect(row.startsWith("高,SEO,")).toBe(true);
  });
});

describe("ProjectPagesPage", () => {
  it("預設依問題數排序，可篩選錯誤頁並搜尋", async () => {
    const user = userEvent.setup();
    renderPagesTab();
    const rows = await screen.findAllByRole("row");
    // 表頭之後第一列是問題最多的頁 2
    expect(within(rows[1]!).getByText("頁 2")).toBeInTheDocument();
    expect(screen.getByText(/另有 2 個站台層級的發現/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /錯誤／被阻擋 1/ }));
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText("頁 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^全部/ }));
    await user.type(screen.getByRole("searchbox"), "p1");
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText("頁 1")).toBeInTheDocument();
  });

  it("點表頭切換排序", async () => {
    const user = userEvent.setup();
    renderPagesTab();
    await screen.findAllByRole("row");
    await user.click(screen.getByRole("button", { name: /載入時間/ }));
    expect(within(screen.getAllByRole("row")[1]!).getByText("頁 3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /載入時間/ }));
    expect(within(screen.getAllByRole("row")[1]!).getByText("頁 1")).toBeInTheDocument();
  });
});
