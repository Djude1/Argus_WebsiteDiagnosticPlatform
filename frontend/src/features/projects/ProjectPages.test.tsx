import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { issuesToCsv, ProjectIssuesPage, ProjectPagesPage, ProjectScansPage } from "./ProjectPages";

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
    if (url === "/projects/7/issues/") {
      return {
        data: {
          scan: { id: 3, completed_at: "2026-10-01T00:00:00Z", categories: ["seo", "security"] },
          compared_with: null,
          missing: [],
          issues: [
            issue("a", { severity: "high", category: "security", title: "缺少 CSP", remediation: "設定 content-security-policy" }),
            issue("b", { severity: "medium", category: "seo", title: "H1 數量不正確" }),
            issue("c", { severity: "low", category: "seo", title: "缺少 canonical" }),
          ],
        },
      };
    }
    return { data: { results: [] } };
  });
});

function issue(key: string, overrides: Record<string, unknown>) {
  return {
    key, rule_id: key, status: "new", streak: 1, pages: 1, urls: ["https://a.example/"], description: "說明",
    remediation: "修法", ...overrides,
  };
}

function renderIssuesTab(path = "/projects/7/issues") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:projectId" element={<Outlet context={{ project: PROJECT }} />}>
          <Route path="issues" element={<ProjectIssuesPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

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

describe("ProjectIssuesPage", () => {
  it("網址的 ?q= 只列出符合的問題，清除搜尋後回到全部", async () => {
    const user = userEvent.setup();
    renderIssuesTab("/projects/7/issues?q=CSP");
    expect(await screen.findByText("缺少 CSP")).toBeInTheDocument();
    expect(screen.queryByText("H1 數量不正確")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "清除搜尋" }));
    expect(screen.getByText("H1 數量不正確")).toBeInTheDocument();
  });

  it("依嚴重度分組顯示分組列，點嚴重度數量只看該級", async () => {
    const user = userEvent.setup();
    renderIssuesTab();
    await screen.findByText("缺少 CSP");
    await user.click(screen.getByRole("button", { name: /依嚴重度分組/ }));
    const groups = Array.from(document.querySelectorAll(".issue-group-row")).map((row) => row.textContent?.replace(/\s+/g, ""));
    expect(groups).toEqual(["高1個問題", "中1個問題", "低1個問題"]);
    await user.click(within(document.querySelector(".issue-summary-sev") as HTMLElement).getByRole("button", { name: /低/ }));
    expect(screen.getByText("缺少 canonical")).toBeInTheDocument();
    expect(screen.queryByText("缺少 CSP")).not.toBeInTheDocument();
  });
});

describe("ProjectIssuesPage 本次未出現", () => {
  it("只有覆蓋完整的項目標「已修好」，其餘標示實際狀態", async () => {
    api.get.mockImplementation(async (url: string) => (url !== "/projects/7/issues/" ? { data: { results: [] } } : {
      data: {
        scan: { id: 3, completed_at: "2026-10-01T00:00:00Z", categories: ["security"] },
        compared_with: { id: 2, completed_at: "2026-09-20T00:00:00Z" },
        issues: [],
        missing: [
          { key: "h", rule_id: "h", title: "缺少 HSTS", category: "security", severity: "medium",
            status: "resolved", status_label: "已修好" },
          { key: "x", rule_id: "x", title: "反射型 XSS", category: "security", severity: "high",
            status: "inconclusive", status_label: "無法判定" },
        ],
      },
    }));
    renderIssuesTab();
    const section = await screen.findByRole("heading", { name: /本次未出現/ });
    const list = section.closest("section") as HTMLElement;
    expect(within(list).getByText("已修好")).toBeInTheDocument();
    expect(within(list).getByText("無法判定")).toBeInTheDocument();
  });
});

describe("ProjectScansPage 示範專案", () => {
  it("示範專案不顯示建立掃描表單，改引導新增自己的網站", async () => {
    render(
      <MemoryRouter initialEntries={["/projects/7/scans"]}>
        <Routes>
          <Route path="/projects/:projectId" element={<Outlet context={{ project: { ...PROJECT, is_demo: true, summary: {} } }} />}>
            <Route path="scans" element={<ProjectScansPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "示範專案不能建立掃描" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "新增你的網站" })).toHaveAttribute("href", "/projects/new");
    expect(screen.queryByRole("button", { name: "建立掃描" })).not.toBeInTheDocument();
    expect(screen.getByText("示範")).toBeInTheDocument();
  });
});
