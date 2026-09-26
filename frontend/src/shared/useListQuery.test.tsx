import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { nextOrdering, useListQuery } from "./useListQuery";

// 這支 hook 是後台所有列表頁的網址狀態來源。它出過一次靜默失效：
// `user` 參數沒列進 defaults，網址帶著 ?user=5 但列表完全不套用篩選，
// 畫面看起來正常卻是錯的。前端當時沒有測試，只能靠人眼發現。

const DEFAULTS = { page: 1, q: "", status: "", ordering: "-created_at" };

/** 把 hook 的輸出攤平成畫面，方便用 Testing Library 斷言。 */
function Probe({ defaults = DEFAULTS }: { defaults?: typeof DEFAULTS }) {
  const { params, setParam, setParams, resetFilters, hasFilters } = useListQuery(defaults);
  const location = useLocation();
  return (
    <div>
      <output data-testid="params">{JSON.stringify(params)}</output>
      <output data-testid="search">{location.search}</output>
      <output data-testid="hasFilters">{String(hasFilters)}</output>
      <button onClick={() => setParam("status", "failed")}>set-status</button>
      <button onClick={() => setParam("page", 3)}>set-page</button>
      <button onClick={() => setParams({ q: "example" })}>set-q</button>
      <button onClick={() => setParam("status", "")}>clear-status</button>
      <button onClick={resetFilters}>reset</button>
    </div>
  );
}

function renderAt(initialPath: string, defaults = DEFAULTS) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Probe defaults={defaults} />
    </MemoryRouter>,
  );
}

const params = () => JSON.parse(screen.getByTestId("params").textContent || "{}");
const search = () => screen.getByTestId("search").textContent;

describe("useListQuery", () => {
  it("沒有查詢字串時回傳預設值", () => {
    renderAt("/admin/scans");
    expect(params()).toEqual(DEFAULTS);
    expect(screen.getByTestId("hasFilters").textContent).toBe("false");
  });

  it("從網址還原狀態——貼上連結要能看到同一個畫面", () => {
    renderAt("/admin/scans?status=failed&page=2&q=example");
    expect(params()).toMatchObject({ status: "failed", page: 2, q: "example" });
    expect(screen.getByTestId("hasFilters").textContent).toBe("true");
  });

  it("數字型參數會轉成 number，不是字串", () => {
    renderAt("/admin/scans?page=4");
    expect(params().page).toBe(4);
  });

  it("壞掉的數字退回預設而不是 NaN", () => {
    renderAt("/admin/scans?page=abc");
    expect(params().page).toBe(1);
  });

  it("只有非預設值會寫進網址，乾淨狀態不拖著 ?page=1&q=", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans");
    await user.click(screen.getByText("set-status"));
    expect(search()).toBe("?status=failed");
  });

  it("設成預設值時該參數要從網址移除", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans?status=failed");
    await user.click(screen.getByText("clear-status"));
    expect(search()).toBe("");
  });

  it("改篩選條件會回到第一頁——留在第 5 頁常常直接落到空結果", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans?page=5");
    await user.click(screen.getByText("set-q"));
    expect(params().page).toBe(1);
    expect(search()).not.toContain("page=5");
  });

  it("換頁本身不會被重設回第一頁", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans?status=failed");
    await user.click(screen.getByText("set-page"));
    expect(params()).toMatchObject({ page: 3, status: "failed" });
  });

  it("resetFilters 清空所有參數", async () => {
    const user = userEvent.setup();
    renderAt("/admin/scans?status=failed&q=x&page=3");
    await user.click(screen.getByText("reset"));
    expect(search()).toBe("");
    expect(params()).toEqual(DEFAULTS);
  });

  it("分頁不算篩選條件——只有 page 時 hasFilters 為 false", () => {
    renderAt("/admin/scans?page=3");
    expect(screen.getByTestId("hasFilters").textContent).toBe("false");
  });

  it("未宣告在 defaults 的參數會被忽略（這正是 ?user= 當初失效的原因）", () => {
    renderAt("/admin/scans?user=5");
    // hook 只認得 defaults 裡的鍵；user 不在其中，所以讀不到。
    // 這個行為本身是對的——問題在於當時沒人發現參數沒被宣告。
    expect(params()).not.toHaveProperty("user");
    expect(params()).toEqual(DEFAULTS);
  });

  it("把參數加進 defaults 後就讀得到", () => {
    renderAt("/admin/scans?user=5", { ...DEFAULTS, user: "" } as never);
    expect(params()).toMatchObject({ user: "5" });
  });
});

describe("nextOrdering", () => {
  it("第一次點某欄位用降冪——後台大多要看最大的幾筆", () => {
    expect(nextOrdering("-created_at", "amount")).toBe("-amount");
  });

  it("同欄位再點一次反向", () => {
    expect(nextOrdering("-amount", "amount")).toBe("amount");
    expect(nextOrdering("amount", "amount")).toBe("-amount");
  });
});
