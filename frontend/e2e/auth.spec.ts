import { test, expect } from "@playwright/test";

/**
 * Authentication E2E tests — verifies the auth pages render correctly
 * and form validation works. These tests do NOT depend on specific
 * user credentials and run against any environment (CI with seeded DB
 * or local dev).
 */

test.describe("Login page", () => {
  test("renders login form with input fields", async ({ page }) => {
    await page.goto("/login");
    // The login form should have at least two text inputs (email + password)
    await expect(page.getByRole("textbox").first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows error on invalid credentials submission", async ({ page }) => {
    await page.goto("/login");
    // Fill with definitely-wrong credentials and submit
    const inputs = page.getByRole("textbox");
    const emailInput = inputs.first();
    await emailInput.fill("nonexistent@test.com");
    // Password field might be type=password (not textbox), find it directly
    const passwordInput = page.locator("input[type='password']").first();
    if (await passwordInput.isVisible()) {
      await passwordInput.fill("WrongPassword123!");
    }
    // Click the submit/login button
    const loginBtn = page.getByRole("button", { name: /login|sign in/i });
    if (await loginBtn.isVisible()) {
      await loginBtn.click();
    }
    // Should show some error message within 10 seconds
    await expect(page.getByText(/invalid|incorrect|not found|wrong|error/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });
});

test.describe("Signup page", () => {
  test("renders signup form", async ({ page }) => {
    await page.goto("/signup");
    // Signup page should render with some input fields
    await expect(page.getByRole("textbox").first()).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Auth page navigation", () => {
  test("auth page renders with form elements", async ({ page }) => {
    await page.goto("/auth");
    // Auth page should render something (either login or signup form)
    await expect(page.getByRole("textbox").first()).toBeVisible({ timeout: 10_000 });
  });
});
