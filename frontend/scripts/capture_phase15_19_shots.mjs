// Phase 15 tail + Phase 16-19.2 screenshot capture.
//  15: market report (admin, trust -> analytics)
//  16: similar rooms carousel (room modal deep link, embeddings runtime)
//  17: fraud graph GraphNode changelist (Django admin)
//  18: AI Command dashboard (admin front-end tab)
//  19.1: Property Intelligence inspector (Django admin)
//  19.2: AI Rental Agent grounded chat + bookmark consent (tenant)
// Usage: node scripts/capture_phase15_19_shots.mjs
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = process.env.BASE || "http://localhost:3001";
const API = process.env.API || "http://127.0.0.1:8000/api/v1";
const ADMIN = process.env.ADMIN || "http://127.0.0.1:8000";
const OUT = "../docs/screenshots/";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function jsClick(locator) {
  await locator.first().evaluate((el) => el.click());
}

async function waitForCount(locator, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await locator.count().catch(() => 0)) return true;
    await sleep(500);
  }
  return false;
}

async function apiToken(email, password) {
  const res = await fetch(`${API}/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (res.status === 429)
    throw new Error(`auth rate-limited for ${email} — restart backend to reset`);
  if (!res.ok) throw new Error(`token failed for ${email}: ${res.status}`);
  return (await res.json()).access;
}

async function setUser(page, token) {
  // Visit /auth once to bootstrap the SPA, store the token, then reload so the
  // app boots authenticated (avoids the 401 /auth/user race).
  await page.goto(`${BASE}/auth`, { waitUntil: "domcontentloaded" });
  await page.evaluate((t) => localStorage.setItem("rentora_access", t), token);
  await page.reload({ waitUntil: "domcontentloaded" });
}

async function snap(page, el, name) {
  await el
    .screenshot({ path: `${OUT}${name}` })
    .catch((e) => console.warn(`shot ${name} failed:`, e.message));
  console.log("saved:", name);
}

async function adminLogin(page) {
  await page.goto(`${ADMIN}/admin/login/`, { waitUntil: "domcontentloaded" });
  await page.locator("#id_username").fill("admin");
  await page.locator("#id_password").fill("demo12345");
  await jsClick(page.locator("input[type=submit]"));
  await page
    .locator("main#content, #content")
    .first()
    .waitFor({ timeout: 20000 })
    .catch(() => console.warn("admin login may have failed"));
  await sleep(1500);
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  fs.mkdirSync(OUT, { recursive: true });

  // Never let the Conditional UI hammer the auth rate limit.
  await page.route("**/auth/passkey/**", (route) => route.abort());

  const rahim = await apiToken("rahim.hossain@rentora.com", "demo12345");
  const tenant = await apiToken("tenant.pending@rentora.com", "demo12345");
  const admin = await apiToken("admin@rentora.com", "demo12345");
  console.log("tokens obtained");

  // --- 1. Phase 15 tail: market report (admin, trust -> analytics) --------
  await setUser(page, admin);
  await page.goto(`${BASE}/dashboard?tab=trust`, { waitUntil: "networkidle" });
  await sleep(3000);
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll("button")].find((b) =>
      /^Analytics\s*$/.test((b.textContent || "").trim())
    );
    btn?.click();
  });
  let reportCard = page
    .locator("text=/Rental market report/i")
    .first()
    .locator(
      "xpath=ancestor::*[contains(@class,'rounded-2xl') or contains(@class,'rounded-xl')][1]"
    );
  await reportCard
    .waitFor({ timeout: 25000 })
    .catch(() => console.warn("market report card not found"));
  await sleep(2000);
  await reportCard.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(1200);
  await snap(page, reportCard, "phase15-market-report.png");

  // --- 2. Phase 16: similar rooms carousel (room modal deep link) ---------
  await setUser(page, rahim);
  await page.goto(`${BASE}/rooms/mirpur?room=90009`, { waitUntil: "networkidle" });
  await sleep(3500);
  const similar = page.locator("text=Similar Rooms").first();
  await similar.waitFor({ timeout: 25000 }).catch(() => console.warn("similar rooms not found"));
  let similarSection = similar.locator("xpath=ancestor::*[contains(@class,'rounded')][1]");
  await similarSection.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(1500);
  await snap(page, similarSection, "phase16-similar-rooms.png");

  // --- 3. Phase 17: fraud graph GraphNode changelist (Django admin) -------
  await adminLogin(page);
  await page.goto(`${ADMIN}/admin/fraud/graphnode/`, { waitUntil: "networkidle" });
  await page
    .locator("text=/Host: Hasan/i")
    .first()
    .waitFor({ timeout: 20000 })
    .catch(() => console.warn("graph nodes not listed"));
  await sleep(1500);
  await snap(page, page.locator("#content").first(), "phase17-fraud-graph-admin.png");

  // --- 4. Phase 18: AI Command dashboard (admin front-end) ----------------
  await setUser(page, admin);
  await page.goto(`${BASE}/dashboard?tab=ai`, { waitUntil: "networkidle" });
  await sleep(3500);
  const aiHeading = page.locator("text=AI Intelligence").first();
  await aiHeading.waitFor({ timeout: 25000 }).catch(() => console.warn("AI panel not found"));
  let aiPanel = aiHeading.locator(
    "xpath=ancestor::*[contains(@class,'rounded-2xl') or contains(@class,'rounded-xl')][1]"
  );
  await aiPanel.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(1500);
  // Fall back to the main column if the ancestor lookup misses the panel.
  if ((await aiPanel.boundingBox().catch(() => null)) === null) {
    aiPanel = page.locator("main, #root").first();
  }
  await snap(page, aiPanel, "phase18-ai-dashboard.png");

  // --- 5. Phase 19.1: Property Intelligence inspector (Django admin) ------
  await page.goto(`${ADMIN}/admin/rooms/room/90009/property-intelligence/`, {
    waitUntil: "networkidle",
  });
  await page
    .locator("text=/Property Intelligence/i")
    .first()
    .waitFor({ timeout: 25000 })
    .catch(() => console.warn("property intelligence page not found"));
  await sleep(2000);
  await snap(page, page.locator("#content").first(), "phase19-1-property-intelligence.png");

  // --- 6. Phase 19.2: AI Rental Agent grounded chat + consent -------------
  await setUser(page, tenant);
  await page.goto(`${BASE}/rooms`, { waitUntil: "networkidle" });
  await sleep(2500);
  const copilotBtn = page.getByRole("button", { name: "Open Rentora Copilot" });
  await waitForCount(copilotBtn, 20000);
  if (await copilotBtn.count()) {
    await jsClick(copilotBtn);
    await sleep(1500);
  }
  // The rooms nav has its own "AI Tools" entry (links to a non-route 404); the
  // toggler we want lives INSIDE the Copilot dialog, so scope the search there.
  const opened = await page.evaluate(() => {
    const dlg = [...document.querySelectorAll("div.fixed")].find(
      (d) =>
        (d.textContent || "").includes("Rentora Copilot") &&
        (d.textContent || "").includes("AI Tools")
    );
    const btn =
      dlg &&
      [...dlg.querySelectorAll("button")].find((b) => (b.textContent || "").trim() === "AI Tools");
    if (!btn) return false;
    btn.click();
    return true;
  });
  if (!opened) console.warn("AI Tools toggler not found inside Copilot dialog");
  await sleep(2500);
  await page
    .locator("text=/await approval/i")
    .first()
    .waitFor({ timeout: 25000 })
    .catch(() => console.warn("rental agent proposal not shown"));
  await page
    .locator("text=/Premium Studio - Mirpur 10/i")
    .first()
    .waitFor({ timeout: 15000 })
    .catch(() => console.warn("grounded card not shown"));
  await sleep(1500);
  const agentPanel = page
    .locator("text=/Rentora AI Rental Agent/i")
    .first()
    .locator("xpath=ancestor::*[contains(@class,'fixed')][1]");
  await agentPanel.waitFor({ timeout: 10000 }).catch(() => {});
  const target = (await agentPanel.boundingBox().catch(() => null))
    ? agentPanel
    : page.locator("body");
  await snap(page, target, "phase19-2-rental-agent.png");

  await browser.close();
  console.log("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
