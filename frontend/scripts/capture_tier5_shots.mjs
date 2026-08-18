// Tier-5 screenshot capture — price recommendation, AI listing draft, Copilot photos.
// Usage: node scripts/capture_tier5_shots.mjs  (backend on :8000, frontend on :3001)
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://127.0.0.1:3001";
const OUT = "../docs/screenshots/";
const SHOTS = [
  ["tier5-price-recommendation.png", ".bg-card:has-text('Price recommendation')"],
  ["tier5-ai-draft.png", "button:has-text('AI draft')"],
  ["tier5-copilot-photos.png", null], // full-page of the copilot widget state
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function login(page) {
  await page.goto(`${BASE}/auth`, { waitUntil: "networkidle" });
  await sleep(1500);
  // If the auth dialog isn't open (e.g. navigated straight to /auth), the
  // navbar Sign In opens it.
  const dialogOpen = await page.evaluate(() => !!document.querySelector("[role='dialog']"));
  if (!dialogOpen) {
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll("button")].find((b) =>
        /^sign in$/i.test((b.textContent || "").trim())
      );
      btn?.click();
    });
    await sleep(1200);
  }
  const userInput = page
    .locator("input[placeholder*='email or username'], input[placeholder*='rahim.hossain']")
    .first();
  const passInput = page.locator("input[type='password']").first();
  if ((await userInput.count()) === 0 || (await passInput.count()) === 0) {
    // fallback: nth inputs
    const inputs = page.locator("input");
    await inputs.nth(0).fill("admin.demo");
    await inputs.nth(1).fill("demo12345");
  } else {
    await userInput.fill("admin.demo");
    await passInput.fill("demo12345");
  }
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll("button")].filter(
      (b) => (b.textContent || "").trim().toLowerCase() === "sign in"
    );
    const btn = btns.find((b) => b.closest("[role='dialog']")) ?? btns[btns.length - 1];
    btn?.click();
  });
  await sleep(3000);
  const ok = await page.evaluate(() => !!localStorage.getItem("rentora_access"));
  if (!ok) {
    // maybe already on dashboard
    await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" });
    await sleep(1500);
    const ok2 = await page.evaluate(() => !!localStorage.getItem("rentora_access"));
    if (!ok2) throw new Error("login failed");
  }
  await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" });
  await sleep(2000);
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  fs.mkdirSync(OUT, { recursive: true });

  await login(page);

  // --- 1. price recommendation card on the listings tab -------------------
  await page.evaluate(() => {
    const tabs = [...document.querySelectorAll("button, [role='tab']")];
    const listTab = tabs.find((b) => /listings/i.test(b.textContent || ""));
    listTab?.click();
  });
  await sleep(1800);
  const recBtn = page.locator("button:has-text('Get recommendation')").first();
  if ((await recBtn.count()) > 0) {
    await recBtn.click();
    await sleep(2500);
  }
  const recCard = page.locator("div:has-text('Price recommendation')").first();
  if ((await recCard.count()) > 0) {
    await recCard.screenshot({ path: `${OUT}tier5-price-recommendation.png` });
    console.log("shot 1 saved");
  } else {
    console.warn("no price-recommendation card found");
  }

  // --- 2. AI draft button on the listing form -----------------------------
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll("button")];
    const add = btns.find((b) => /add listing|list a room|new listing/i.test(b.textContent || ""));
    add?.click();
  });
  await sleep(1500);
  // fill minimal fields so the draft is meaningful
  const inputs = page.locator("input");
  const ic = await inputs.count();
  for (let i = 0; i < Math.min(ic, 4); i++) {
    const ph = await inputs.nth(i).getAttribute("placeholder");
    if (ph && /title/i.test(ph)) await inputs.nth(i).fill("Sunny Studio in Dhanmondi");
    if (ph && /rent|price/i.test(ph)) await inputs.nth(i).fill("15000");
    if (ph && /size|sqft/i.test(ph)) await inputs.nth(i).fill("320");
  }
  const draftBtn = page.locator("button:has-text('AI draft')").first();
  if ((await draftBtn.count()) > 0) {
    await draftBtn.click();
    await sleep(2500);
    // capture the whole dialog so the drafted title/description are visible
    const dialog = page.locator("[role='dialog']").last();
    if ((await dialog.count()) > 0) {
      await dialog.screenshot({ path: `${OUT}tier5-ai-draft.png` });
    } else {
      await page.screenshot({ path: `${OUT}tier5-ai-draft.png` });
    }
    console.log("shot 2 saved");
  }
  await page.evaluate(() => {
    document.querySelectorAll("[data-state='open']").forEach((el) => {
      const close = el.querySelector("button[aria-label='Close']");
      close?.click();
    });
  });

  // --- 3. Copilot photos answer -------------------------------------------
  await page.goto(`${BASE}/rooms`, { waitUntil: "networkidle" });
  await sleep(1800);
  // open the copilot widget and ask about photos of a listing
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll("button")].find((b) =>
      /copilot|ask/i.test(b.textContent || "")
    );
    btn?.click();
  });
  await sleep(1200);
  const input = page
    .locator("input[placeholder*='ask'], textarea[placeholder*='ask'], input:not([type])")
    .last();
  if ((await input.count()) > 0) {
    await input.fill("What does this room look like?");
    await input.press("Enter");
    await sleep(3000);
  }
  await page.screenshot({ path: `${OUT}tier5-copilot-photos.png` });
  console.log("shot 3 saved");

  await browser.close();
  console.log("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
