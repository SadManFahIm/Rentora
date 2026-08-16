import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// i18n (Tier 3): dictionaries load synchronously so translated components
// render real English strings in tests (never raw keys).
import "../i18n";

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

// jsdom lacks pointer-capture APIs that Radix (e.g. Select's trigger) calls
// on pointerdown — without these the dropdown never opens under test.
if (typeof Element !== "undefined") {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
}
/* eslint-enable @typescript-eslint/no-empty-function */
