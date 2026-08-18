/* Capture Tier-3/Tier-4 feature screenshots (README phase gallery).
 *
 * Requires the stack running: backend on :8000, frontend dev server on :3001.
 *   node scripts/capture_tier4_shots.mjs
 *
 * Safe demo data only — no real PII. Outputs flat PNGs into ../docs/screenshots.
 * Clicks are dispatched via element.click() because the TanStack Query
 * devtools overlay intercepts pointer events in this environment.
 */
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, "..", "..", "docs", "screenshots");
mkdirSync(OUT, { recursive: true });

const BASE = "http://localhost:3001";
const PASSWORD = "demo12345";

async function shot(page, name) {
  await page.waitForTimeout(700);
  await page.screenshot({ path: join(OUT, name), fullPage: false });
  console.log("captured", name);
}

/** Dispatch a click via JS — bypasses the tsqd overlay's pointer-event trap. */
async function jsClick(locator) {
  await locator.first().evaluate((el) => el.click());
}

async function login(page, username) {
  await page.goto(`${BASE}/auth`);
  await page.waitForTimeout(1200);
  const inputs = page.locator("input");
  await inputs.nth(0).fill(username);
  await inputs.nth(1).fill(PASSWORD);
  await jsClick(page.getByRole("button", { name: /sign in/i }));
  await page.waitForTimeout(2500);
}

/** Open a real room card's modal via JS click (bypasses overlay). */
async function openRoomModal(page) {
  const res = await page.evaluate(() => {
    const skip = new Set(["Room", "Bangladesh", "", "Avatar"]);
    const imgs = [...document.querySelectorAll("img[alt]")].filter(
      (i) => !skip.has(i.alt) && i.alt.length > 3
    );
    for (const img of imgs) {
      let el = img;
      for (let i = 0; i < 8 && el; i++) {
        el = el.parentElement;
        if (el && typeof el.onclick === "function") {
          const cls = String(el.className ?? "");
          if (
            cls.includes("cursor-pointer") ||
            cls.includes("rounded-xl") ||
            cls.includes("rounded-2xl")
          ) {
            el.click();
            return { ok: true, alt: img.alt };
          }
        }
      }
    }
    return { ok: false, imgCount: imgs.length };
  });
  console.log("openRoomModal:", JSON.stringify(res));
  await page.waitForTimeout(1800);
  const opened = await page
    .getByRole("dialog")
    .count()
    .catch(() => 0);
  if (!opened) throw new Error("room modal did not open");
}

const browser = await chromium.launch();

// ---- 1. RAG Copilot listing Q&A (Tier 3) -----------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(2500);
  await openRoomModal(page);
  await jsClick(page.getByRole("button", { name: /ask copilot about this listing/i }));
  await page.waitForTimeout(1500);
  const input = page.getByPlaceholder(/ask anything/i);
  await input.fill("What is the monthly rent and does it have AC?");
  await input.press("Enter");
  await page.waitForTimeout(3500);
  await shot(page, "phase12.8-copilot-listing-qa.png");
  await page.close();
}

// ---- 2. EN⇄BN language toggle (Tier 3) -------------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(2500);
  await jsClick(page.getByRole("button", { name: /switch to bangla|বাংলা/i }));
  await page.waitForTimeout(1200);
  await shot(page, "phase12.8-lang-toggle.png");
  await page.close();
}

// ---- 3. AI Tools panel — advisor (Tier 4) ----------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(2500);
  await jsClick(page.getByRole("button", { name: /open rentora copilot/i }));
  await page.waitForTimeout(1000);
  await jsClick(page.getByRole("button", { name: /ai tools/i }));
  await page.waitForTimeout(1000);
  await page.getByPlaceholder(/monthly budget/i).fill("15000");
  await page.getByPlaceholder(/monthly income/i).fill("40000");
  const go = page.getByRole("button", { name: /advise|get advice|suggest|recommend/i }).first();
  if ((await go.count()) > 0) await jsClick(go);
  await page.waitForTimeout(2500);
  await shot(page, "phase12.9-ai-tools-advisor.png");
  await page.close();
}

// ---- 4. Compare drawer (Tier 4) --------------------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${BASE}/rooms`);
  await page.waitForTimeout(3500);
  const compareBtns = page.getByTitle(/add to comparison/i);
  const n = await compareBtns.count();
  if (n >= 2) {
    await jsClick(compareBtns.nth(0));
    await page.waitForTimeout(500);
    const again = page.getByTitle(/add to comparison/i);
    await jsClick(again.nth(1));
    await page.waitForTimeout(1000);
  }
  await jsClick(page.getByRole("button", { name: /compare \(\d/i })).catch(() => {});
  await page.waitForTimeout(2000);
  await shot(page, "phase12.9-compare.png");
  await page.close();
}

// ---- 5. Landlord AI widget (Tier 4) ----------------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, "rahim.hossain");
  await page.goto(`${BASE}/dashboard`);
  await page.waitForTimeout(3000);
  const btn = page.getByRole("button", { name: /get (ai )?insight|insights/i }).first();
  if ((await btn.count()) > 0) {
    await jsClick(btn);
    await page.waitForTimeout(2500);
  }
  await shot(page, "phase12.9-landlord-copilot.png");
  await page.close();
}

// ---- 6. Smart alerts / notifications (Tier 4) ------------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, "admin");
  await page.goto(`${BASE}/dashboard`);
  await page.waitForTimeout(3000);
  await jsClick(page.getByRole("button", { name: /notifications/i })).catch(() => {});
  await page.waitForTimeout(1500);
  await shot(page, "phase12.9-smart-alerts.png");
  await page.close();
}

// ---- 7. Completed-bookings trust chip (Tier 3) -----------------------------
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(page, "tenant.verified");
  await page.goto(`${BASE}/dashboard`);
  await page.waitForTimeout(3000);
  await shot(page, "phase12.8-completed-bookings.png");
  await page.close();
}

await browser.close();
console.log("done — all captures in", OUT);
