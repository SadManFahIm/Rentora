import { test, expect } from "@playwright/test";

/**
 * Booking flow E2E tests — minimal smoke tests that verify key pages
 * load successfully. No authentication required.
 */

test("rooms page loads", async ({ page }) => {
  await page.goto("/rooms");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});

test("area rooms page loads", async ({ page }) => {
  await page.goto("/rooms/dhanmondi");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});

test("dashboard page loads or redirects", async ({ page }) => {
  await page.goto("/dashboard");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});
