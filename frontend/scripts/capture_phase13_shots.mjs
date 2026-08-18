// Phase 13 screenshot capture — SMS OTP login, WhatsApp share, area SEO pages.
// Usage: node scripts/capture_phase13_shots.mjs  (backend on :8000, frontend on :3001)
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://127.0.0.1:3001";
const OUT = "../docs/screenshots/";
const SHOTS = [
  ["phase13-area-page.png", "area landing page hero + listings"],
  ["phase13-whatsapp-share.png", "room modal Share on WhatsApp button"],
  ["phase13-sms-login.png", "auth dialog SMS sign-in section"],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function login(page) {
  await page.goto(`${BASE}/auth`, { waitUntil: "networkidle" });
  await sleep(1500);
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
  if (!ok) throw new Error("login failed");
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  fs.mkdirSync(OUT, { recursive: true });

  // --- 3. SMS sign-in section in the auth dialog -------------------------
  // Captured BEFORE login — an authenticated user is redirected away from
  // /auth, so the phone sign-in box is only reachable while signed out.
  await page.goto(`${BASE}/auth`, { waitUntil: "networkidle" });
  await sleep(1800);
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll("button")].find((b) =>
      /^sign in$/i.test((b.textContent || "").trim())
    );
    btn?.click();
  });
  await sleep(1200);
  const smsSection = page.locator("div:has-text('Sign in with your phone')").first();
  if ((await smsSection.count()) > 0) {
    await smsSection.screenshot({ path: `${OUT}phase13-sms-login.png` });
  } else {
    const authDialog = page.locator("[role='dialog']").last();
    if ((await authDialog.count()) > 0) {
      await authDialog.screenshot({ path: `${OUT}phase13-sms-login.png` });
    } else {
      await page.screenshot({ path: `${OUT}phase13-sms-login.png` });
    }
  }
  console.log("shot 3 saved (SMS login)");

  // All three Phase 13 captures are public pages — no login needed (and the
  // shared login helper would burn the auth throttle on repeat runs).

  // --- 1. Area landing page (SEO reach) ----------------------------------
  await page.goto(`${BASE}/rooms/dhanmondi`, { waitUntil: "networkidle" });
  await sleep(2500);
  const title = await page.title();
  console.log("area page title:", title);
  await page.screenshot({ path: `${OUT}phase13-area-page.png`, fullPage: true });
  console.log("shot 1 saved (area page)");

  // --- 2. Room modal WhatsApp share button -------------------------------
  await page.goto(`${BASE}/rooms`, { waitUntil: "networkidle" });
  await sleep(2500);
  // Wait for a real listing card, then click it to open the room modal.
  await page.locator(".group").first().waitFor({ timeout: 20000 }).catch(() => {});
  await page.locator(".group").first().click({ timeout: 10000 }).catch(() => {});
  await sleep(2000);
  const shareBtn = page.locator("button:has-text('Share on WhatsApp')");
  if ((await shareBtn.count()) > 0) {
    await page.locator("[role='dialog']").last().screenshot({ path: `${OUT}phase13-whatsapp-share.png` });
    console.log("shot 2 saved (WhatsApp share)");
  } else {
    await page.screenshot({ path: `${OUT}phase13-whatsapp-share.png` });
    console.warn("dialog/share button not found; full page saved");
  }
  await page.evaluate(() => {
    document.querySelectorAll("[data-state='open']").forEach((el) => {
      const close = el.querySelector("button[aria-label='Close']");
      close?.click();
    });
  });

  await browser.close();
  console.log("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});