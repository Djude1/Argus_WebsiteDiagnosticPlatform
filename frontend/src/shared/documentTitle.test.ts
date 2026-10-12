import { describe, expect, it } from "vitest";

import { DEFAULT_DESCRIPTION, SITE_NAME, descriptionForPath, titleForPath } from "./documentTitle";

describe("titleForPath", () => {
  it("公開頁各自有不同的標題", () => {
    const paths = ["/project", "/free-tools", "/purchase", "/download", "/verify", "/partners",
      "/privacy", "/terms", "/scanner", "/reviews", "/login"];
    const titles = paths.map(titleForPath);
    expect(new Set(titles).size).toBe(paths.length);
    titles.forEach((t) => expect(t.endsWith(`｜${SITE_NAME}`)).toBe(true));
  });

  it("動態網址與結尾斜線", () => {
    expect(titleForPath("/projects/7/seo/")).toBe(`SEO 分析｜${SITE_NAME}`);
    expect(titleForPath("/projects/7")).toBe(`專案總覽｜${SITE_NAME}`);
    expect(titleForPath("/projects/new")).toBe(`新增網站專案｜${SITE_NAME}`);
    expect(titleForPath("/scans/3/rebuild/9")).toBe(`頁面優化成果｜${SITE_NAME}`);
    expect(titleForPath("/verify/ARGUS-20261011-56F2")).toBe(`報告查驗｜${SITE_NAME}`);
  });

  it("沒有對應的網址用網站名稱", () => {
    expect(titleForPath("/not-exist")).toBe(SITE_NAME);
  });
});

describe("descriptionForPath", () => {
  const PUBLIC = ["/project", "/free-tools", "/purchase", "/download", "/verify", "/partners",
    "/privacy", "/terms", "/scanner", "/reviews", "/login"];

  it("公開頁的摘要長度在 50 到 160 字之間", () => {
    for (const path of PUBLIC) {
      const length = descriptionForPath(path).length;
      expect(length, path).toBeGreaterThanOrEqual(50);
      expect(length, path).toBeLessThanOrEqual(160);
    }
  });

  it("除了首頁，公開頁的摘要都不同", () => {
    const others = PUBLIC.filter((p) => p !== "/project").map(descriptionForPath);
    expect(new Set(others).size).toBe(others.length);
  });

  it("會員頁沿用預設摘要", () => {
    expect(descriptionForPath("/projects/7/seo")).toBe(DEFAULT_DESCRIPTION);
  });
});
