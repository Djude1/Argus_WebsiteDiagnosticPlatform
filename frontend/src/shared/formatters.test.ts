import { afterEach, describe, expect, it, vi } from "vitest";

import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatNtd,
  formatNumber,
  formatRelative,
} from "./formatters";

// 這些函式存在的理由是「畫面上不要出現 Invalid Date / NaN」——
// 所以測試重點放在壞輸入的 fallback，而不只是正常路徑。

// 用本地時間建構，格式化也是本地時間，測試不受執行機器的時區影響
const LOCAL = new Date(2026, 8, 25, 14, 5, 30);

describe("formatDateTime / formatDate", () => {
  it("正常日期輸出為 24 小時制、補零", () => {
    // 日期與時間之間的分隔字元來自 ICU 語系資料，不同 ICU 版本／瀏覽器不同
    // （Node 22 + ICU 78 是 U+2009 thin space），所以只要求「某種空白」
    expect(formatDateTime(LOCAL)).toMatch(/^2026\/09\/25\s14:05$/u);
    expect(formatDate(LOCAL)).toBe("2026/09/25");
  });

  it("接受 ISO 字串", () => {
    expect(formatDate(LOCAL.toISOString())).toBe("2026/09/25");
  });

  it.each([null, undefined, "", "not-a-date"])("壞輸入 %j 回傳破折號，不是 Invalid Date", (value) => {
    expect(formatDateTime(value)).toBe("—");
    expect(formatDate(value)).toBe("—");
  });

  it("可自訂 fallback", () => {
    expect(formatDateTime(null, "尚未完成")).toBe("尚未完成");
  });
});

describe("formatRelative", () => {
  afterEach(() => vi.useRealTimers());

  const now = new Date(2026, 8, 25, 12, 0, 0);
  const ago = (sec: number) => new Date(now.getTime() - sec * 1000);

  it.each([
    [30, "30 秒前"],
    [59, "59 秒前"],
    [60, "1 分鐘前"],
    [3599, "59 分鐘前"],
    [3600, "1 小時前"],
    [86399, "23 小時前"],
    [86400, "1 天前"],
  ])("%i 秒前 → %s（單位切換的邊界）", (sec, expected) => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
    expect(formatRelative(ago(sec))).toBe(expected);
  });

  it("未來時間用「後」", () => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
    expect(formatRelative(ago(-120))).toBe("2 分鐘後");
  });

  it("壞輸入回傳 fallback", () => {
    expect(formatRelative("garbage")).toBe("—");
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "0 秒"],
    [59, "59 秒"],
    [60, "1 分"],
    [80, "1 分 20 秒"],
    [59.6, "1 分"],
  ])("%s → %s", (sec, expected) => {
    expect(formatDuration(sec)).toBe(expected);
  });

  it("負數視為 0（時鐘誤差不該顯示負的耗時）", () => {
    expect(formatDuration(-5)).toBe("0 秒");
  });

  it.each([null, undefined, "abc"])("%j 回傳 fallback", (value) => {
    expect(formatDuration(value)).toBe("—");
  });
});

describe("formatNumber / formatNtd", () => {
  it("千分位", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
    expect(formatNtd(1990)).toBe("NT$ 1,990");
  });

  it("0 是有效值，不能被當成空值吃掉", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatNtd(0)).toBe("NT$ 0");
  });

  it("接受數字字串（後端 Decimal 常以字串回傳）", () => {
    expect(formatNtd("1500")).toBe("NT$ 1,500");
  });

  it.each([null, undefined, "", "abc"])("%j 回傳 fallback，不是 NaN", (value) => {
    expect(formatNumber(value)).toBe("—");
    expect(formatNtd(value)).toBe("—");
  });
});
