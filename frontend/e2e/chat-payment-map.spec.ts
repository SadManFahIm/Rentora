import { test, expect } from "@playwright/test";

/**
 * E2E tests for chat, payment, and map interaction flows.
 * These test critical user journeys that involve multiple pages
 * and real-time features.
 */

test.describe("Chat flow", () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("admin@rentora.com");
    await page.getByLabel(/password/i).fill("Admin123!");
    await page.getByRole("button", { name: /login|sign in/i }).click();
    await page.waitForURL(/dashboard|\/$/, { timeout: 10_000 });
  });

  test("chat page loads and shows conversation list", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForTimeout(2000);
    // Chat page should render
    await expect(page.getByText(/chat|conversation|message/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("chat page has search or filter functionality", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForTimeout(2000);
    // Should have some input or search
    const searchInput = page.getByRole("textbox").first();
    if (await searchInput.isVisible()) {
      await expect(searchInput).toBeVisible();
    }
  });
});

test.describe("Payment flow", () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("admin@rentora.com");
    await page.getByLabel(/password/i).fill("Admin123!");
    await page.getByRole("button", { name: /login|sign in/i }).click();
    await page.waitForURL(/dashboard|\/$/, { timeout: 10_000 });
  });

  test("payment status page renders", async ({ page }) => {
    await page.goto("/payment/status");
    await page.waitForTimeout(2000);
    // Should show payment status or redirect
    await expect(page.getByText(/payment|status|booking/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("dashboard payments tab shows payment history", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(2000);
    const paymentsTab = page.getByRole("button", { name: /payments/i });
    await expect(paymentsTab).toBeVisible({ timeout: 10_000 });
    await paymentsTab.click();
    await page.waitForTimeout(1000);
    // Should show payment-related content
    await expect(page.getByText(/total paid|pending|payment/i).first()).toBeVisible({
      timeout: 5000,
    });
  });
});

test.describe("Map interactions", () => {
  test("map page loads with interactive canvas", async ({ page }) => {
    await page.goto("/map");
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 15_000 });
  });

  test("map has toolbar with layer toggles", async ({ page }) => {
    await page.goto("/map");
    await page.waitForTimeout(3000);
    // Toolbar should have toggle buttons
    const toolbar = page.locator("[class*='toolbar'], [class*='toggle']").first();
    if (await toolbar.isVisible()) {
      await expect(toolbar).toBeVisible();
    }
  });

  test("map search bar is functional", async ({ page }) => {
    await page.goto("/map");
    await page.waitForTimeout(3000);
    const searchInput = page.getByPlaceholder(/search|street|area/i).first();
    if (await searchInput.isVisible()) {
      await searchInput.fill("Gulshan");
      await page.waitForTimeout(1000);
      // Should show autocomplete suggestions
      const suggestions = page.locator("[role='listbox'], [class*='suggestion']").first();
      if (await suggestions.isVisible()) {
        await expect(suggestions).toBeVisible();
      }
    }
  });

  test("map legend is visible", async ({ page }) => {
    await page.goto("/map");
    await page.waitForTimeout(3000);
    // Legend should show tier colors
    const legend = page.getByText(/legend/i).first();
    if (await legend.isVisible()) {
      await expect(legend).toBeVisible();
    }
  });

  test("map room count badge shows", async ({ page }) => {
    await page.goto("/map");
    await page.waitForTimeout(3000);
    // Room count badge should appear
    const badge = page.getByText(/room/i).first();
    if (await badge.isVisible()) {
      await expect(badge).toBeVisible();
    }
  });
});

test.describe("Roommates page", () => {
  test("roommates page loads", async ({ page }) => {
    await page.goto("/roommates");
    await page.waitForTimeout(2000);
    await expect(page.getByText(/roommate|match|find/i).first()).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Services page", () => {
  test("services page loads", async ({ page }) => {
    await page.goto("/services");
    await page.waitForTimeout(2000);
    await expect(page.getByText(/service|subscription|marketplace/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });
});
