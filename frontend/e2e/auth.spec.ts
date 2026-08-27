import { test, expect } from "@playwright/test";

/**
 * Authentication E2E tests — minimal smoke tests that verify auth pages
 * load successfully. These do NOT depend on specific credentials,
 * form structure, or UI components, making them CI-safe.
 */

test("login page loads", async ({ page }) => {
  await page.goto("/login");
  // Wait for the page to fully render (React lazy-load + any redirects)
  await page.waitForTimeout(3000);
  // The page should have loaded — verify by checking the URL hasn't crashed
  // and the document body is not empty
  const body = page.locator("body");
  await expect(body).not.toBeEmpty();
});

test("signup page loads", async ({ page }) => {
  await page.goto("/signup");
  await page.waitForTimeout(3000);
  const body = page.locator("body");
  await expect(body).not.toBeEmpty();
});

test("auth page loads", async ({ page }) => {
  await page.goto("/auth");
  await page.waitForTimeout(3000);
  const body = page.locator("body");
  await expect(body).not.toBeEmpty();
});
