import { describe, expect, it } from "vitest";

import { keywordGap, untargetedQueries, type GscQuery } from "./seoKeywordGap";

const q = (query: string, impressions: number, position: number, page = "https://a.tw/", clicks = 0): GscQuery =>
  ({ query, impressions, position, page, clicks });

describe("keywordGap", () => {
  it("彙總包含關鍵字的搜尋詞，依最佳平均排名分段", () => {
    const [gap] = keywordGap(
      [{ keyword: "咖啡豆", best_page: { url: "https://a.tw/beans/" } }],
      [q("台北 咖啡豆", 300, 14.2, "https://a.tw/beans", 5), q("咖啡豆推薦", 120, 18, "https://a.tw/beans", 2), q("手沖壺", 50, 3)],
    );
    expect(gap).toMatchObject({
      status: "second", queries: 2, impressions: 420, clicks: 7, bestPosition: 14.2, bestQuery: "台北 咖啡豆",
      landingMismatch: "",
    });
    expect(gap?.advice).toMatch(/第 2 頁/);
  });

  it("不分大小寫與全形空白；第 1 頁沒有分段建議", () => {
    const [gap] = keywordGap([{ keyword: "Pour　Over", best_page: null }], [q("best pour over kettle", 80, 6.5)]);
    expect(gap?.status).toBe("first");
    expect(gap?.advice).toBe("");
  });

  it("Google 帶到的頁面（曝光最多的搜尋詞）與內容最相關的頁面不同時提示", () => {
    const [gap] = keywordGap(
      [{ keyword: "課程", best_page: { url: "https://a.tw/class" } }],
      [q("手沖課程", 200, 25, "https://a.tw/"), q("咖啡課程 台北", 20, 9, "https://a.tw/class")],
    );
    expect(gap).toMatchObject({ status: "first", landingMismatch: "https://a.tw/", bestQuery: "咖啡課程 台北" });
    expect(gap?.advice).toMatch(/主題的主頁/);
  });

  it("沒有相關搜尋詞時依頁面有沒有提到給不同建議", () => {
    const gaps = keywordGap(
      [{ keyword: "冷萃", best_page: { url: "https://a.tw/cold" } }, { keyword: "濾掛", best_page: null }],
      [q("咖啡豆", 10, 5)],
    );
    expect(gaps.map((g) => g.status)).toEqual(["none", "none"]);
    expect(gaps[0]?.advice).toMatch(/頁面有提到/);
    expect(gaps[1]?.advice).toMatch(/建立專門的頁面/);
  });
});

describe("untargetedQueries", () => {
  it("排除包含目標關鍵字（或被目標包含）的字詞，依曝光排序", () => {
    const rows = untargetedQueries(
      ["咖啡豆", "台北手沖課程"],
      [q("咖啡豆推薦", 900, 4), q("手沖課程", 300, 8), q("拿鐵做法", 500, 12), q("耳掛", 500, 7), q("無曝光", 0, 1)],
    );
    expect(rows.map((r) => r.query)).toEqual(["耳掛", "拿鐵做法"]);
  });
});
