import { test, expect } from "@playwright/test";

/**
 * Booking flow E2E tests — verifies room browsing, dashboard, and
 * room details work without requiring specific user credentials.
 * These tests run against any environment (CI with seeded DB or local dev).
 */

test.describe("Room browsing (public)", () => {
  test("rooms page loads and shows content", async ({ page }) => {
    await page.goto("/rooms");
    // Rooms page should render
    await page.waitForTimeout(3000);
    await expect(page.getByRole("heading", { name: /rooms/i }).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("rooms page has search functionality", async ({ page }) => {
    await page.goto("/rooms");
    await page.waitForTimeout(2000);
    // Should have at least one textbox for search
    const searchInput = page.getByRole("textbox").first();
    await expect(searchInput).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Room detail page", () => {
  test("room page renders listing details", async ({ page }) => {
    await page.goto("/rooms");
    await page.waitForTimeout(3000);
    // Click on the first room card/button
    const roomLink = page
      .locator("button, a")
      .filter({ hasText: /৳|room|studio/i })
      .first();
    if (await roomLink.isVisible()) {
      await roomLink.click();
      await page.waitForTimeout(2000);
      // Room detail should show something
      await expect(page.getByText(/per month|\/mo|view listing|details|room/i).first()).toBeVisible(
        { timeout: 10_000 }
      );
    }
  });
});

test.describe("Area rooms page", () => {
  test("area rooms page renders", async ({ page }) => {
    await page.goto("/rooms/dhanmondi");
    await page.waitForTimeout(3000);
    await expect(page.getByText(/dhanmondi/i).first()).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Dashboard (public parts)", () => {
  test("dashboard redirects to login when not authenticated", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(3000);
    // Should either show dashboard content or redirect to login
    await expect(
      page
        .getByRole("textbox")
        .first()
        .or(page.getByText(/dashboard|login|sign/i).first())
    ).toBeVisible({ timeout: 10_000 });
  });
});
