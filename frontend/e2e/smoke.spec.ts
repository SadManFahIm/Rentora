import { test, expect } from "@playwright/test";

/**
 * Browser-level smoke tests (Tier 4) — verify the app actually boots in a
 * real browser: home renders, navigation works, the Copilot widget opens,
 * and the EN⇄BN language toggle flips the UI. These deliberately avoid
 * auth-gated pages so they run against any environment (CI with a seeded
 * DB, or a local dev box).
 *
 * Some environments inject a floating feedback widget that overlaps the
 * bottom-right corner and eats pointer events, so the Copilot / language
 * toggles are clicked programmatically (``element.click()``) — the widget
 * under test is the app's own React handler.
 */

async function clickByLabel(page: import("@playwright/test").Page, label: string) {
  // Wait for the button to actually exist (React mounts after the load
  // event), then dispatch a programmatic click that bypasses any
  // environment overlay widget eating pointer events.
  await page.waitForFunction((l) => {
    const el = [...document.querySelectorAll("button")].find((b) =>
      b.getAttribute("aria-label")?.toLowerCase().includes(l)
    );
    return !!el;
  }, label);
  return page.evaluate((l) => {
    const el = [...document.querySelectorAll("button")].find((b) =>
      b.getAttribute("aria-label")?.toLowerCase().includes(l)
    );
    if (el) (el as HTMLButtonElement).click();
    return !!el;
  }, label);
}

test("home page boots and renders the hero", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Rentora/);
  // The search bar is the page's primary CTA.
  await expect(page.getByRole("textbox").first()).toBeVisible();
});

test("rooms page renders the search UI", async ({ page }) => {
  await page.goto("/rooms");
  await expect(page.getByRole("textbox").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Rooms/i }).first()).toBeVisible();
});

test("copilot widget opens, shows AI Tools, and closes", async ({ page }) => {
  await page.goto("/");
  expect(await clickByLabel(page, "copilot")).toBe(true);
  // The chat panel appears with an input to type a message.
  const copilotInput = page.getByRole("textbox", { name: /copilot/i });
  await expect(copilotInput).toBeVisible();
  // AI Tools toggle (Tier 4) is visible inside the widget.
  await expect(page.getByRole("button", { name: /AI Tools/i })).toBeVisible();
  await clickByLabel(page, "copilot");
  await expect(copilotInput).toBeHidden();
});

test("language toggle switches the nav to Bangla", async ({ page }) => {
  await page.goto("/");
  expect(await clickByLabel(page, "switch to bangla")).toBe(true);
  // After switching, at least one Bengali nav word appears.
  await expect(page.getByText(/রুম|হোম|ম্যাপ/).first()).toBeVisible();
});
