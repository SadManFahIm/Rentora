import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Vitest runs without `globals: true`, so RTL's auto-cleanup (which hooks
// into a global afterEach) never fires — without this, rendered DOM leaks
// between tests and queries find stale elements. Clean up explicitly.
afterEach(() => cleanup());

// ---- jsdom stubs that Radix UI (and friends) expect but jsdom lacks ----
// The no-op methods are intentional test doubles.
/* eslint-disable @typescript-eslint/no-empty-function */
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
/* eslint-enable @typescript-eslint/no-empty-function */
