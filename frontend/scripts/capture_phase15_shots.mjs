// Phase 15 screenshot capture - Communication & Trust AI: chat translate,
// support copilot + TTS, KYC OCR, review AI summary, market report,
// dynamic pricing v2, and fraud rings.
// Usage: node scripts/capture_phase15_shots.mjs (backend :8000, frontend :3000)
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE || "http://localhost:3000";
const API = process.env.API || "http://127.0.0.1:8000/api/v1";
const OUT = "../docs/screenshots/";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Dispatch a click via JS - bypasses the tsqd overlay's pointer-event trap. */
async function jsClick(locator) {
  await locator.first().evaluate((el) => el.click());
}

async function apiToken(email, password) {
  const res = await fetch(`${API}/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(`token failed for ${email}: ${res.status}`);
  return (await res.json()).access;
}

async function setUser(page, token) {
  await page.goto(`${BASE}/auth`, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => localStorage.setItem("rentora_access", t), token);
}

async function snap(page, el, name) {
  await el
    .screenshot({ path: `${OUT}${name}` })
    .catch((e) => console.warn(`shot ${name} failed:`, e.message));
  console.log("saved:", name);
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  fs.mkdirSync(OUT, { recursive: true });

  const rahim = await apiToken("rahim.hossain@rentora.com", "demo12345");
  const tenant = await apiToken("tenant.pending@rentora.com", "demo12345");
  const admin = await apiToken("admin@rentora.com", "demo12345");
  console.log("tokens obtained");

  // --- 1. Chat translate: Bengali message translated to English ----------
  await setUser(page, rahim);
  await page.goto(`${BASE}/chat?room=6`, { waitUntil: "networkidle" });
  await sleep(2500);
  const translateBtns = page.locator("button[aria-label='Translate message']");
  await translateBtns
    .last()
    .waitFor({ timeout: 15000 })
    .catch(() => {});
  await jsClick(translateBtns.last());
  await sleep(3500);
  await page
    .locator("text=/Translated/i")
    .first()
    .waitFor({ timeout: 15000 })
    .catch(() => console.warn("no translated bubble found"));
  await snap(page, page.locator("main, #root").first(), "phase15-chat-translate.png");

  // --- 2. Support copilot: grounded help answer --------------------------
  await page.goto(`${BASE}/rooms`, { waitUntil: "networkidle" });
  await sleep(2500);
  await jsClick(page.getByRole("button", { name: "Open Rentora Copilot" }));
  await sleep(1200);
  await jsClick(page.getByRole("button", { name: /AI Tools/i }));
  await sleep(800);
  await jsClick(page.getByRole("button", { name: /^Support$/i }));
  await sleep(600);
  await page.locator("textarea[aria-label='Support question']").fill("How do I renew my listing?");
  await jsClick(page.getByRole("button", { name: /Get answer/i }));
  await sleep(4500);
  const supportPanel = page
    .locator("text=/Ask the support Copilot/i")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'fixed') or contains(@class,'rounded-2xl')][1]");
  await snap(page, supportPanel, "phase15-copilot-support.png");

  // --- 3. Copilot TTS: assistant reply with Read aloud -------------------
  await jsClick(page.getByRole("button", { name: /AI Tools/i }));
  await sleep(800);
  await jsClick(page.getByRole("button", { name: /Uttara.*room/i }).first());
  await sleep(6000);
  const speakBtn = page.getByRole("button", { name: /Read aloud/i });
  await speakBtn
    .first()
    .waitFor({ timeout: 20000 })
    .catch(() => {});
  const widget = page
    .locator("text=/Rentora Copilot/i")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'fixed')][1]");
  await snap(page, widget, "phase15-copilot-tts.png");

  // --- 4. KYC OCR: AI auto-extract on pending tenant ---------------------
  await setUser(page, tenant);
  await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" });
  await sleep(2500);
  const ocrPanel = page
    .locator("text=/AI auto-extract from your upload/i")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-xl')][1]");
  await ocrPanel.waitFor({ timeout: 15000 }).catch(() => {});
  await snap(page, ocrPanel, "phase15-kyc-ocr.png");

  // --- 5. Review AI summary: room 90009 modal (deep-link opens the modal) ---
  await setUser(page, rahim);
  await page.goto(`${BASE}/rooms/mirpur?room=90009`, { waitUntil: "networkidle" });
  await sleep(3000);
  let summaryCard = page
    .locator("text=/Overall:/i")
    .first()
    .locator(
      "xpath=ancestor::*[contains(@class,'rounded-xl') or contains(@class,'rounded-2xl')][1]"
    );
  if (!(await summaryCard.count().catch(() => 0))) {
    summaryCard = page
      .locator("text=/AI review summary/i")
      .first()
      .locator("xpath=ancestor::*[contains(@class,'rounded-xl')][1]");
  }
  await summaryCard.waitFor({ timeout: 20000 }).catch(() => {});
  await summaryCard.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(1200);
  await snap(page, summaryCard, "phase15-review-ai-summary.png");

  // --- 6. Market report: admin analytics tab -----------------------------
  await setUser(page, admin);
  await page.goto(`${BASE}/dashboard?tab=trust`, { waitUntil: "networkidle" });
  await sleep(2500);
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll("button")].filter((b) =>
      /^Analytics/.test((b.textContent || "").trim())
    );
    btns[0]?.click();
  });
  const reportCard = page
    .locator("text=/Rental market report/i")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-2xl')][1]");
  await reportCard.waitFor({ timeout: 25000 }).catch(() => {});
  await sleep(1500);
  await reportCard.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(1000);
  await snap(page, reportCard, "phase15-market-report.png");

  // --- 7. Dynamic pricing v2: landlord listings --------------------------
  await setUser(page, rahim);
  await page.goto(`${BASE}/dashboard?tab=listings`, { waitUntil: "networkidle" });
  await sleep(3000);
  const priceCard = page
    .locator("text=/Price recommendation/i")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'rounded-2xl')][1]");
  await priceCard.waitFor({ timeout: 15000 }).catch(() => {});
  await priceCard.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(1500);
  await snap(page, priceCard, "phase15-price-v2.png");

  // --- 8. Fraud rings: admin fraud tab -----------------------------------
  await setUser(page, admin);
  await page.goto(`${BASE}/dashboard?tab=fraud`, { waitUntil: "networkidle" });
  await sleep(2500);
  const ringsToggle = page.getByRole("button", { name: /Show fraud rings/i });
  await ringsToggle
    .first()
    .waitFor({ timeout: 15000 })
    .catch(() => {});
  await jsClick(ringsToggle.first());
  await sleep(3500);
  const ringsSection = page
    .locator("text=/Coordinated-account rings/i")
    .first()
    .locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]");
  await ringsSection.waitFor({ timeout: 15000 }).catch(() => {});
  await ringsSection.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(1200);
  await snap(page, ringsSection, "phase15-fraud-rings.png");

  await browser.close();
  console.log("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
