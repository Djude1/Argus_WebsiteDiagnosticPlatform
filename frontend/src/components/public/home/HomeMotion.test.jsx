import { act, screen } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { expect, it, vi } from "vitest";

import { usePrefersReducedMotion } from "./HomeMotion";

function MotionPreference() {
  const reduced = usePrefersReducedMotion();
  return <p>{reduced ? "減少動態" : "一般動態"}</p>;
}

it("減少動態偏好不破壞預先渲染接手，且掛載後及偏好變更都會生效", async () => {
  const original = window.matchMedia;
  let listener;
  const media = { matches: true, addEventListener: vi.fn((_, callback) => { listener = callback; }), removeEventListener: vi.fn() };
  window.matchMedia = vi.fn(() => media);
  const container = document.createElement("div");
  container.innerHTML = renderToString(<MotionPreference />);
  document.body.append(container);
  const errors = [];
  let root;
  await act(async () => {
    root = hydrateRoot(container, <MotionPreference />, { onRecoverableError: (error) => errors.push(error) });
  });
  expect(errors).toEqual([]);
  expect(screen.getByText("減少動態")).toBeInTheDocument();
  await act(async () => { media.matches = false; listener(); });
  expect(screen.getByText("一般動態")).toBeInTheDocument();
  await act(async () => root.unmount());
  expect(media.removeEventListener).toHaveBeenCalledWith("change", listener);
  container.remove();
  window.matchMedia = original;
});
