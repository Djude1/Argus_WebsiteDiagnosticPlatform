import { describe, expect, it } from "vitest";

import { COST_PER_PAGE_NTD, planEconomics } from "./planEconomics";

// 用 billing/migrations/0002_seed_plans_and_wallets.py 的種子方案驗算。
// 後端五維全選每頁 10 coin（5 維 × ARGUS_COIN_PER_CATEGORY 預設 2）。

describe("planEconomics", () => {
  it.each([
    // 名稱, 售價, coin, 預期成本, 預期毛利率, 預期頁數
    ["入門", 100, 100, 6.7, 93, 10],
    ["標準", 450, 500, 33.5, 93, 50],
    ["進階", 800, 1000, 67, 92, 100],
    ["旗艦", 1500, 2200, 147.4, 90, 220],
  ])("%s方案 NT$%i / %i coin → 成本 NT$%s、毛利 %i%%、約 %i 頁", (_, price, coin, cost, pct, pages) => {
    const e = planEconomics({ price_ntd: price, coin_amount: coin }, 10);
    expect(e.cost).toBe(cost);
    expect(e.marginPct).toBe(pct);
    expect(e.pagesEstimate).toBe(pages);
    expect(e.tone).toBe("good");
  });

  it("成本以「頁」計：coin_per_page 變了，成本跟著變（原本把每 coin 當每頁，高估 10 倍）", () => {
    const tenPerPage = planEconomics({ price_ntd: 1500, coin_amount: 2200 }, 10);
    const onePerPage = planEconomics({ price_ntd: 1500, coin_amount: 2200 }, 1);
    expect(onePerPage.cost).toBeCloseTo(tenPerPage.cost * 10, 0);
    expect(tenPerPage.cost).toBeCloseTo((2200 / 10) * COST_PER_PAGE_NTD, 1);
  });

  it("毛利率門檻：80% 以上健康、50% 以上偏低、其餘須重新定價", () => {
    // 1000 coin = 100 頁 = NT$67 成本
    expect(planEconomics({ price_ntd: 400, coin_amount: 1000 }, 10).tone).toBe("good"); // 83%
    expect(planEconomics({ price_ntd: 150, coin_amount: 1000 }, 10).tone).toBe("warn"); // 55%
    expect(planEconomics({ price_ntd: 100, coin_amount: 1000 }, 10)).toMatchObject({
      tone: "bad", toneLabel: "須重新定價",
    }); // 33%
  });

  it("售價 0（免費方案）或欄位未填時不會算出 NaN", () => {
    expect(planEconomics({ price_ntd: 0, coin_amount: 100 }, 10).marginPct).toBe(0);
    expect(planEconomics({}, 10)).toMatchObject({ cost: 0, margin: 0, marginPct: 0, pagesEstimate: 0 });
  });

  it("coin_per_page 異常（0）時不除以零", () => {
    expect(planEconomics({ price_ntd: 100, coin_amount: 100 }, 0).pagesEstimate).toBe(0);
  });
});
