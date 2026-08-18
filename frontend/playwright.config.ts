import { defineConfig, devices } from "@playwright/test";

/**
 * Browser-level E2E (Tier 4) — the second, real-browser layer on top of the
 * tagged Django API E2E suites.
 *
 * Requires the backend (http://localhost:8000) and the Vite dev server
 * (http://localhost:3000) to be running. `npx playwright test` boots the
 * frontend automatically via `webServer`; the backend is expected to be up
 * (see the CI job / README runbook).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3001",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // Rentora dev server on a dedicated port (3000 may be taken by another
    // local app) — strictPort fails fast instead of silently serving the
    // wrong app.
    command: "npm run dev -- --port 3001 --strictPort",
    url: "http://localhost:3001",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
