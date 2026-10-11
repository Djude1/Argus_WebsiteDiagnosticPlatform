import { describe, expect, it } from "vitest";

import { filenameFromDisposition } from "./download";

describe("filenameFromDisposition", () => {
  it("讀取後端給的報告檔名", () => {
    expect(
      filenameFromDisposition('attachment; filename="argus-report-20261011-E03E.pdf"', "x.pdf"),
    ).toBe("argus-report-20261011-E03E.pdf");
  });

  it("支援 UTF-8 編碼的檔名", () => {
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%E5%A0%B1%E5%91%8A.pdf", "x.pdf")).toBe("報告.pdf");
  });

  it("沒有標頭時用預設檔名", () => {
    expect(filenameFromDisposition(undefined, "argus-report.pdf")).toBe("argus-report.pdf");
  });
});
