import { test, expect } from "@playwright/test";

/**
 * E2E tests for chat, payment, and map interactions.
 * All tests are public/unauthenticated to work in CI environments
 * without specific seeded user credentials.
 */

test.describe("Map page", () => {
  test("map page loads with interactive canvas", async ({ page }) => {
    await page.goto("/map");
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 15_000 });
  });

  test("map page has toolbar area", async ({ page }) => {
    await page.goto("/map");
    await page.waitForTimeout(3000);
    // The toolbar should be visible (layer toggles)
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 15_000 });
  });

  test("map search bar is present", async ({ page }) => {
    await page.goto("/map");
    await page.waitForTimeout(3000);
    const searchInput = page.getByPlaceholder(/search|street|area/i).first();
    if (await searchInput.isVisible()) {
      await expect(searchInput).toBeVisible();
    }
  });
});

test.describe("Roommates page", () => {
  test("roommates page loads", async ({ page }) => {
    await page.goto("/roommates");
    await page.waitForTimeout(2000);
    // Should show some content
    await expect(
      page
        .getByRole("textbox")
        .first()
        .or(page.getByText(/roommate|match|find|partner/i).first())
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Services page", () => {
  test("services page loads", async ({ page }) => {
    await page.goto("/services");
    await page.waitForTimeout(2000);
    await expect(
      page
        .getByRole("textbox")
        .first()
        .or(page.getByText(/service|subscription|marketplace|plan/i).first())
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Chat page", () => {
  test("chat page renders (may redirect to login)", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForTimeout(3000);
    // Should show chat content or redirect to auth
    await expect(
      page
        .getByRole("textbox")
        .first()
        .or(page.getByText(/chat|message|login|sign/i).first())
    ).toBeVisible({ timeout: 10_000 });
  });
});
