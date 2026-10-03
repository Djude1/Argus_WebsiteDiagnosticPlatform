import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SiteFavicon from "./SiteFavicon";

describe("SiteFavicon", () => {
  it("有 favicon 顯示圖片，沒有則顯示名稱首字", () => {
    const { container, rerender } = render(
      <SiteFavicon project={{ name: "example", favicon: "data:image/png;base64,AAAA" }} />,
    );
    expect(container.querySelector("img")?.getAttribute("src")).toBe("data:image/png;base64,AAAA");
    rerender(<SiteFavicon project={{ name: "example", favicon: "" }} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("E");
  });
});
