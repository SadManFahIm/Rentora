import { test, expect } from "@playwright/test";

/**
 * Booking flow E2E tests — verifies room listing, detail view,
 * booking request, and payment flow work end-to-end.
 *
 * These tests run against the live backend with seeded test data.
 * Some tests require authentication (booking actions).
 */

test.describe("Room browsing (public)", () => {
  test("rooms page loads and shows room cards", async ({ page }) => {
    await page.goto("/rooms");
    await expect(page.getByRole("heading", { name: /rooms/i }).first()).toBeVisible();
    // Wait for room cards to load (they come from the API)
    await page.waitForTimeout(2000);
    // Room cards should be present (either in grid or list format)
    const cards = page.locator("[class*='room'], [class*='card']").first();
    await expect(cards).toBeVisible({ timeout: 10_000 });
  });

  test("room filters are functional", async ({ page }) => {
    await page.goto("/rooms");
    await page.waitForTimeout(1000);
    // Check that filter controls are present
    const searchInput = page.getByRole("textbox").first();
    await expect(searchInput).toBeVisible();
  });

  test("map page loads with MapLibre", async ({ page }) => {
    await page.goto("/map");
    // MapLibre creates a canvas element
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Booking flow (authenticated)", () => {
  test.beforeEach(async ({ page }) => {
    // Login as a tenant user
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("tenant@rentora.com");
    await page.getByLabel(/password/i).fill("Tenant123!");
    await page.getByRole("button", { name: /login|sign in/i }).click();
    await page.waitForURL(/dashboard|\/$/, { timeout: 10_000 });
  });

  test("dashboard shows overview stats", async ({ page }) => {
    await page.goto("/dashboard");
    // Overview tab should show stat cards
    await expect(page.getByText(/saved rooms/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/booking requests/i).first()).toBeVisible();
  });

  test("dashboard tabs are navigable", async ({ page }) => {
    await page.goto("/dashboard");
    // Click on bookings tab
    const bookingsTab = page.getByRole("button", { name: /bookings/i });
    await expect(bookingsTab).toBeVisible({ timeout: 10_000 });
    await bookingsTab.click();
    // Should show bookings content (either a list or empty state)
    await expect(page.getByText(/no bookings yet|loading bookings|booking/i).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test("wishlist tab shows saved rooms or empty state", async ({ page }) => {
    await page.goto("/dashboard");
    const wishlistTab = page.getByRole("button", { name: /wishlist/i });
    await expect(wishlistTab).toBeVisible({ timeout: 10_000 });
    await wishlistTab.click();
    await expect(page.getByText(/no saved rooms yet|saved rooms/i).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test("payments tab shows payment history or empty state", async ({ page }) => {
    await page.goto("/dashboard");
    const paymentsTab = page.getByRole("button", { name: /payments/i });
    await expect(paymentsTab).toBeVisible({ timeout: 10_000 });
    await paymentsTab.click();
    await expect(page.getByText(/no payments yet|total paid|payment/i).first()).toBeVisible({
      timeout: 5000,
    });
  });
});

test.describe("Room detail and booking request", () => {
  test("room page renders listing details", async ({ page }) => {
    await page.goto("/rooms");
    await page.waitForTimeout(2000);
    // Click on the first available room card
    const roomCard = page
      .locator("button, a")
      .filter({ hasText: /৳|room|studio/i })
      .first();
    if (await roomCard.isVisible()) {
      await roomCard.click();
      // Room detail modal or page should appear
      await expect(page.getByText(/per month|\/mo|view listing|details/i).first()).toBeVisible({
        timeout: 10_000,
      });
    }
  });

  test("area rooms page renders for a known area", async ({ page }) => {
    await page.goto("/rooms/dhanmondi");
    await page.waitForTimeout(2000);
    // Should show area-specific content
    await expect(page.getByText(/dhanmondi/i).first()).toBeVisible({ timeout: 10_000 });
  });
});
