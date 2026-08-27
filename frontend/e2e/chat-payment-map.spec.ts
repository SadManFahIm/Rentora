import { test, expect } from "@playwright/test";

/**
 * E2E smoke tests for map, chat, roommates, and services pages.
 * All tests are public/unauthenticated and only verify the page loads.
 */

test("map page loads", async ({ page }) => {
  await page.goto("/map");
  await page.waitForTimeout(5000);
  // Map should have a canvas element (MapLibre)
  await expect(page.locator("canvas").first()).toBeVisible({ timeout: 15_000 });
});

test("roommates page loads", async ({ page }) => {
  await page.goto("/roommates");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});

test("services page loads", async ({ page }) => {
  await page.goto("/services");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});

test("chat page loads or redirects", async ({ page }) => {
  await page.goto("/chat");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});
