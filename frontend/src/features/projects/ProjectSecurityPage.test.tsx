import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectSecurityPage } from "./ProjectSecurityPage";

vi.mock("../../api", () => ({ api: { get: vi.fn() }, setAccessToken: vi.fn() }));
const { api } = vi.mocked(await import("../../api"));

const PROJECT = { id: 7, name: "a.example", hostname: "a.example", origin: "https://a.example" };

const kinds = (counts: Record<string, number>) =>
  ([
    ["config", "設定建議"], ["exposure", "曝露面"], ["suspected", "疑似弱點"], ["verified", "已驗證弱點"],
  ] as const).map(([kind, label]) => ({ kind, label, description: `${label}說明`, count: counts[kind] || 0 }));

const issue = (key: string, title: string, kind: string, label: string, overrides = {}) => ({
  key, rule_id: key, title, category: "security", severity: "medium", status: "new",
  security_kind: kind, security_kind_label: label, remediation: "修法", pages: 1, ...overrides,
});

function securityData(overrides: Record<string, unknown> = {}) {
  return {
    scan: { id: 3, completed_at: "2026-10-08T00:00:00Z", categories: ["security"] },
    compared_with: null,
    checked: true,
    score: 61,
    coverage: "partial",
    incomplete_checks: ["Nuclei 主動弱點掃描"],
    observatory: { grade: "C", score: 55, tests: [] },
    edge: { provider: "Cloudflare" },
    kinds: kinds({ config: 2, suspected: 1 }),
    issues: [
      issue("csp", "缺少 CSP", "config", "設定建議", { root_cause: "server-headers" }),
      issue("hsts", "缺少 HSTS", "config", "設定建議", { root_cause: "server-headers" }),
      issue("lib", "前端函式庫有已知漏洞", "suspected", "疑似弱點"),
    ],
    missing: [],
    root_causes: [{
      id: "server-headers", title: "網站伺服器的回應標頭設定", where: "網站伺服器的設定",
      summary: "", issues: ["csp", "hsts"], count: 2, severity: "medium", pages: 1,
    }],
    strengths: [{ key: "https", category: "security", title: "全站使用 HTTPS", detail: "說明" }],
    ...overrides,
  };
}

function renderPage(data: unknown) {
  api.get.mockImplementation(async (url: string) =>
    (url === "/projects/7/security/" ? { data } : { data: { results: [] } }) as never);
  return render(
    <MemoryRouter initialEntries={["/projects/7/security"]}>
      <Routes>
        <Route path="/projects/:projectId" element={<Outlet context={{ project: PROJECT }} />}>
          <Route path="security" element={<ProjectSecurityPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("ProjectSecurityPage", () => {
  it("顯示分數、標頭等第、未完成提醒、根本原因與做得好的地方", async () => {
    renderPage(securityData());
    expect(await screen.findByText("資安分數")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Nuclei 主動弱點掃描");
    expect(screen.getByText("Cloudflare")).toBeInTheDocument();
    expect(screen.getByText("網站伺服器的回應標頭設定")).toBeInTheDocument();
    expect(screen.getByText("缺少 CSP、缺少 HSTS")).toBeInTheDocument();
    expect(screen.getByText("全站使用 HTTPS")).toBeInTheDocument();
    // 問題詳情連到問題分析頁，帶資安篩選與這次掃描
    const href = screen.getAllByRole("link", { name: "查看詳情 →" })[0]?.getAttribute("href");
    expect(href).toContain("/projects/7/issues?");
    expect(href).toContain("category=security");
  });

  it("點類型只看該類問題，再點一次取消", async () => {
    const user = userEvent.setup();
    renderPage(securityData());
    await screen.findByText("前端函式庫有已知漏洞");
    const group = screen.getByRole("group", { name: "依類型篩選" });
    await user.click(within(group).getByRole("button", { name: /疑似弱點/ }));
    expect(screen.getByText("前端函式庫有已知漏洞")).toBeInTheDocument();
    expect(screen.queryByText("缺少 CSP")).not.toBeInTheDocument();
    await user.click(within(group).getByRole("button", { name: /疑似弱點/ }));
    expect(screen.getAllByText("缺少 CSP").length).toBeGreaterThan(0);
  });

  it("掃描沒有勾資安時說明原因，不顯示分數", async () => {
    renderPage(securityData({ checked: false }));
    expect(await screen.findByText("這次掃描沒有勾選「資安」")).toBeInTheDocument();
    expect(screen.queryByText("資安分數")).not.toBeInTheDocument();
  });
});
