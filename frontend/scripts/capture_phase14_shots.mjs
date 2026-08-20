// Phase 14 screenshot capture - AI v3: photo intelligence (VisionCard on the
// landlord dashboard) and image search (upload a photo, find look-alike rooms).
// Usage: node scripts/capture_phase14_shots.mjs (backend :8000, frontend :3001)
import { chromium } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const BASE = "http://127.0.0.1:3001";
const OUT = "../docs/screenshots/";
const TMP = path.join(os.tmpdir(), "rentora-phase14-query.png");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function login(page, username, password) {
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
    await inputs.nth(0).fill(username);
    await inputs.nth(1).fill(password);
  } else {
    await userInput.fill(username);
    await passInput.fill(password);
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

async function saveQueryImage(page) {
  // Re-use a real listing photo as the search query so matches are certain.
  const src = await page
    .locator(".group img")
    .first()
    .getAttribute("src")
    .catch(() => null);
  if (!src) throw new Error("no listing image found");
  const abs = src.startsWith("http") ? src : `http://127.0.0.1:8000${src}`;
  const res = await fetch(abs);
  if (!res.ok) throw new Error(`image fetch failed: ${res.status}`);
  fs.writeFileSync(TMP, Buffer.from(await res.arrayBuffer()));
  console.log("query image saved from:", abs);
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  fs.mkdirSync(OUT, { recursive: true });

  // --- 1. Landlord dashboard: photo intelligence panel -------------------
  await login(page, "rahim.hossain", "demo12345");
  await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" });
  await sleep(2500);
  await page
    .getByRole("button", { name: /^listings$/i })
    .first()
    .click({ timeout: 10000 })
    .catch(() => {});
  await sleep(2000);
  const panel = page.locator(
    "xpath=//div[contains(@class,'rounded-2xl') and contains(.,'Photo intelligence')]"
  );
  await panel
    .first()
    .waitFor({ timeout: 20000 })
    .catch(() => {});
  const analyzeBtn = panel.first().getByRole("button", { name: /analyze photos/i });
  if ((await analyzeBtn.count()) > 0) {
    await analyzeBtn.first().click();
    await sleep(4000);
    await panel
      .first()
      .getByRole("button", { name: /ai draft from photos/i })
      .click();
    await sleep(3000);
  }
  await panel
    .first()
    .screenshot({ path: `${OUT}phase14-vision-panel.png` })
    .catch((e) => console.warn("panel shot failed:", e.message));
  console.log("shot 1 saved (vision panel)");

  // --- 2. Rooms page: image search dialog with a chosen photo ------------
  await page.goto(`${BASE}/rooms`, { waitUntil: "networkidle" });
  await sleep(2500);
  await saveQueryImage(page);
  await page.getByRole("button", { name: "Image search" }).click();
  await sleep(1200);
  await page.locator("input[type='file']").setInputFiles(TMP);
  await sleep(1500);
  await page
    .locator("[role='dialog']")
    .last()
    .screenshot({
      path: `${OUT}phase14-image-search-dialog.png`,
    });
  console.log("shot 2 saved (image search dialog)");

  // --- 3. Image search results with match badges -------------------------
  await page.getByRole("button", { name: /find similar rooms/i }).click();
  await sleep(5000);
  const resultsBar = page.locator("text=/visual matches for your photo/");
  await resultsBar
    .first()
    .waitFor({ timeout: 20000 })
    .catch(() => {});
  await page
    .locator("main, #root")
    .first()
    .screenshot({
      path: `${OUT}phase14-image-search-results.png`,
      clip: undefined,
    });
  console.log("shot 3 saved (image search results)");

  await browser.close();
  console.log("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
