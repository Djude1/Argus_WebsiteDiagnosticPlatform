import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { HeroQuickCheck } from "./HeroQuickCheck";

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderAtHome() {
  render(
    <MemoryRouter initialEntries={["/project"]}>
      <Routes>
        <Route path="/project" element={<HeroQuickCheck />} />
        <Route path="/free-tools" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("HeroQuickCheck", () => {
  it("輸入網址後帶到快速檢查頁並預填（不在首頁直接呼叫 API）", async () => {
    renderAtHome();
    await userEvent.type(screen.getByLabelText("要檢查的網址"), " https://example.com/a?b=1 ");
    await userEvent.click(screen.getByRole("button", { name: "免費快速檢查" }));
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/free-tools?url=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1",
    );
  });

  it("沒輸入網址也能進快速檢查頁，不帶空參數", async () => {
    renderAtHome();
    await userEvent.click(screen.getByRole("button", { name: "免費快速檢查" }));
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/free-tools$/);
  });
});
