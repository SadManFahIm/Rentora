import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  INSTALL_DISMISS_COOLDOWN_MS,
  PWA_DISMISS_KEY,
  PWA_SHORTCUTS,
  PWA_UPDATE_DISMISS_KEY,
  UPDATE_DISMISS_COOLDOWN_MS,
  fetchManifest,
  installDismissed,
  isStandalone,
  markInstallDismissed,
  markUpdateDismissed,
  updateDismissed,
  validateManifest,
} from "./pwa";

describe("pwa dismissal policy", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("allows the install CTA when nothing has been dismissed", () => {
    expect(installDismissed()).toBe(false);
  });

  it("hides the install CTA after dismissal, then re-allows it after the cooldown", () => {
    const now = Date.now();
    markInstallDismissed(now);
    expect(installDismissed(now + 1000)).toBe(true);
    expect(installDismissed(now + INSTALL_DISMISS_COOLDOWN_MS + 1)).toBe(false);
  });

  it("treats a corrupted timestamp as not dismissed", () => {
    localStorage.setItem(PWA_DISMISS_KEY, "not-a-number");
    expect(installDismissed()).toBe(false);
  });

  it("applies the same cooldown semantics to the update banner", () => {
    const now = Date.now();
    markUpdateDismissed(now);
    expect(updateDismissed(now + 1000)).toBe(true);
    expect(updateDismissed(now + UPDATE_DISMISS_COOLDOWN_MS + 1)).toBe(false);
    expect(localStorage.getItem(PWA_UPDATE_DISMISS_KEY)).toBe(String(now));
  });
});

describe("isStandalone", () => {
  it("returns true when display-mode: standalone matches", () => {
    const matchMedia = vi.fn(() => ({ matches: true }));
    expect(isStandalone(matchMedia)).toBe(true);
  });

  it("returns false in a normal browser tab", () => {
    const matchMedia = vi.fn(() => ({ matches: false }));
    expect(isStandalone(matchMedia)).toBe(false);
  });
});

describe("validateManifest", () => {
  it("accepts a complete installable manifest", () => {
    const problems = validateManifest({
      name: "Rentora",
      short_name: "Rentora",
      start_url: "/",
      scope: "/",
      display: "standalone",
      theme_color: "#ea580c",
      background_color: "#ffffff",
      icons: [
        { src: "/icons/icon-192.png", sizes: "192x192", purpose: "any" },
        { src: "/icons/icon-512.png", sizes: "512x512", purpose: "any" },
        { src: "/icons/maskable-512.png", sizes: "512x512", purpose: "maskable" },
      ],
    });
    expect(problems).toEqual([]);
  });

  it("flags missing required fields, sizes and maskable icon", () => {
    const problems = validateManifest({ icons: [] });
    expect(problems).toContain('missing or non-string "name"');
    expect(problems).toContain("no 192x192 icon");
    expect(problems).toContain("no 512x512 icon");
    expect(problems).toContain("no maskable icon");
    expect(problems).toContain('display should be "standalone"');
  });
});

describe("fetchManifest", () => {
  it("fetches and returns the manifest JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ name: "Rentora" }), { status: 200 }))
    );
    const manifest = await fetchManifest("/");
    expect(manifest.name).toBe("Rentora");
    vi.unstubAllGlobals();
  });

  it("throws when the manifest cannot be fetched", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("nope", { status: 404 }))
    );
    await expect(fetchManifest("/")).rejects.toThrow(/manifest fetch failed/);
    vi.unstubAllGlobals();
  });
});

describe("PWA_SHORTCUTS", () => {
  it("points only at real app routes", () => {
    const urls = PWA_SHORTCUTS.map((s) => s.url);
    expect(urls).toContain("/rooms");
    expect(urls).toContain("/map");
    expect(urls).toContain("/dashboard?tab=listings");
  });
});
