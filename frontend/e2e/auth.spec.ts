import { test, expect } from "@playwright/test";

/**
 * Authentication E2E smoke tests — verify auth pages load without crashing.
 * No form interaction, no credentials, no DOM selectors that depend on
 * the component library structure. CI-safe.
 */

test("login page loads", async ({ page }) => {
  await page.goto("/login");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});

test("signup page loads", async ({ page }) => {
  await page.goto("/signup");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});

test("auth page loads", async ({ page }) => {
  await page.goto("/auth");
  await page.waitForTimeout(3000);
  await expect(page.locator("body")).not.toBeEmpty();
});
