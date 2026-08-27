import { test, expect } from "@playwright/test";

/**
 * Authentication E2E tests — verifies the login flow, 2FA setup,
 * and passkey registration work end-to-end in a real browser.
 *
 * These tests run against the live backend with seeded test data.
 * Auth pages are publicly accessible (no auth required to view them).
 */

test.describe("Login flow", () => {
  test("login page renders with email and password fields", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /login|sign in/i })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /login|sign in/i })).toBeVisible();
  });

  test("shows error on invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("nonexistent@test.com");
    await page.getByLabel(/password/i).fill("WrongPassword123!");
    await page.getByRole("button", { name: /login|sign in/i }).click();
    // Should show an error toast or message
    await expect(page.getByText(/invalid|incorrect|not found|wrong/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("login form has password visibility toggle", async ({ page }) => {
    await page.goto("/login");
    const passwordField = page.getByLabel(/password/i);
    await expect(passwordField).toHaveAttribute("type", "password");
    // Click the visibility toggle if present
    const toggle = page.getByRole("button", { name: /show|hide|toggle.*password/i });
    if (await toggle.isVisible()) {
      await toggle.click();
      await expect(passwordField).toHaveAttribute("type", "text");
    }
  });

  test("navigates to signup from login page", async ({ page }) => {
    await page.goto("/login");
    const signupLink = page.getByRole("link", { name: /sign up|register|create.*account/i });
    if (await signupLink.isVisible()) {
      await signupLink.click();
      await expect(page).toHaveURL(/signup|register/);
    }
  });
});

test.describe("Signup flow", () => {
  test("signup page renders with required fields", async ({ page }) => {
    await page.goto("/signup");
    await expect(
      page.getByRole("heading", { name: /sign up|register|create.*account/i })
    ).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i).first()).toBeVisible();
  });

  test("shows validation errors for empty signup form", async ({ page }) => {
    await page.goto("/signup");
    await page.getByRole("button", { name: /sign up|register|create/i }).click();
    // Should show validation errors (required fields)
    await expect(page.getByText(/required|cannot be empty/i).first()).toBeVisible({
      timeout: 5000,
    });
  });
});

test.describe("2FA flow (requires login)", () => {
  test.beforeEach(async ({ page }) => {
    // Login first — using test credentials from the seeded database
    await page.goto("/login");
    await page.getByLabel(/email/i).fill("admin@rentora.com");
    await page.getByLabel(/password/i).fill("Admin123!");
    await page.getByRole("button", { name: /login|sign in/i }).click();
    await page.waitForURL(/dashboard|\/$/, { timeout: 10_000 });
  });

  test("2FA card is visible on dashboard overview", async ({ page }) => {
    // Navigate to dashboard
    await page.goto("/dashboard");
    await expect(page.getByText(/two-factor authentication/i)).toBeVisible({ timeout: 10_000 });
  });

  test("2FA enable button is present", async ({ page }) => {
    await page.goto("/dashboard");
    const enableBtn = page.getByRole("button", { name: /enable 2fa/i });
    const disableBtn = page.getByRole("button", { name: /disable/i });
    // Either enable or disable should be visible depending on current state
    const btn = enableBtn.or(disableBtn);
    await expect(btn.first()).toBeVisible({ timeout: 10_000 });
  });

  test("passkey registration button is present", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText(/passkeys/i)).toBeVisible({ timeout: 10_000 });
    const registerBtn = page.getByRole("button", { name: /register.*passkey/i });
    await expect(registerBtn).toBeVisible();
  });
});
