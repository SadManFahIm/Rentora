#!/usr/bin/env node
/**
 * capture-screenshots.mjs — regenerate README screenshots for Rentora.
 *
 * Drives a headless Chrome via the DevTools Protocol, logs in as the given
 * users (tokens are minted through Django's manage.py shell, so the rate
 * limiter on /auth/login/ is never hit), navigates to the target pages,
 * and saves full-page PNGs into docs/screenshots/.
 *
 * Usage (from the repo root, with backend + frontend dev servers running):
 *
 *     node docs/tools/capture-screenshots.mjs
 *
 * Requirements:
 *   - Node.js 22+ (uses the built-in fetch + WebSocket)
 *   - Google Chrome (auto-detected on Windows/macOS/Linux)
 *   - Backend running on :8000, frontend on :3001 (or override below)
 *
 * The demo users must exist and share the password set in DEMO_PASSWORD.
 * Screenshots land in docs/screenshots/ — commit them together with any
 * README changes they accompany.
 */
import { spawn } from "node:child_process";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

// ---- Config (override via env) ----
const FRONTEND = process.env.FRONTEND_URL ?? "http://localhost:3001";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const DEMO_PASSWORD = process.env.DEMO_PASSWORD ?? "demo12345";
const DBG_PORT = Number(process.env.CHROME_DBG_PORT ?? 9333);
const OUT_DIR =
  process.env.OUT_DIR ?? path.join(process.cwd(), "docs", "screenshots");

const ROOT = path.join(import.meta.dirname, "..", ".."); // repo root
const MANAGE_PY = path.join(ROOT, "backend", "manage.py");
const PY =
  process.env.PYTHON ??
  (process.platform === "win32"
    ? path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
    : path.join(ROOT, "backend", "venv", "bin", "python"));

/** A single capture: login user, route, click optional tab, output file. */
const CAPTURES = [
  {
    user: "rahim.hossain",
    route: "/roommates",
    out: "roommates-matching.png",
    waitMs: 4500,
  },
  {
    // Public: no token needed — MapLibre map with room markers + landmarks,
    // street-search autocomplete open to show the new Phase 7 search box.
    user: null,
    route: "/map",
    out: "map-view.png",
    waitMs: 10000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const input = document.querySelector('input[aria-label="Search for a street, area or station"]');
      if (!input) return 'no-input';
      input.focus();
      input.value = 'gulshan';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      return 'typed';
    })()`,
    afterLoadMs: 1400,
  },
  {
    // Dark theme variant — prefs stored under the same key the UI store uses.
    user: null,
    route: "/map",
    out: "map-view-dark.png",
    waitMs: 10000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: true }, version: 0 }));
      return 'dark';
    })()`,
  },
  {
    user: "tanvir.islam",
    route: "/dashboard",
    click: "fraud",
    out: "fraud-detection.png",
    waitMs: 4000,
    afterClickMs: 3000,
  },
  // No token: the auth dialog shows in its logged-out state.
  {
    user: null,
    route: "/auth",
    out: "auth-login.png",
    waitMs: 3500,
  },
  // KYC document upload — the landlord's KycCard (Dashboard -> Overview).
  {
    user: "kyc.demo",
    route: "/dashboard",
    out: "kyc-upload.png",
    waitMs: 4500,
  },
  // KYC admin review panel + decision trail (Dashboard -> KYC -> History).
  {
    user: "admin",
    route: "/dashboard?tab=kyc",
    click: "history",
    out: "kyc-admin-panel.png",
    waitMs: 4500,
    afterClickMs: 2500,
  },
  // KYC review SLA stats — the queue-health strip on the Applications view.
  {
    user: "admin",
    route: "/dashboard?tab=kyc",
    out: "kyc-sla.png",
    waitMs: 4500,
  },
  // KYC 30-day decision trend — the History view's SVG chart: bars are
  // decisions per day, the line is average review hours.
  {
    user: "admin",
    route: "/dashboard?tab=kyc",
    click: "history",
    out: "kyc-trend-chart.png",
    waitMs: 4500,
    afterClickMs: 2500,
  },
  // KYC verified badge in dark mode — the KycCard + trust badge styled for
  // the dark theme (RoomCard verified pill visible in the listing grid).
  {
    user: "kyc.demo",
    route: "/rooms",
    out: "verified-badge-dark.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: true }, version: 0 }));
      return 'dark';
    })()`,
  },
  // Mobile viewport — verified badge + KYC card on a phone-sized screen.
  {
    user: "kyc.demo",
    route: "/dashboard",
    out: "kyc-mobile.png",
    waitMs: 4500,
    viewport: { width: 390, height: 844, deviceScaleFactor: 2, mobile: true },
    resetViewport: true,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  {
    // Phase 10 — dashboard growth cards: referral invite + browser push.
    user: "rahim.hossain",
    route: "/dashboard",
    out: "phase10-dashboard-growth.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  {
    // Phase 10 — landlord listing insights tab (views, wishlists, price vs area).
    user: "rahim.hossain",
    route: "/dashboard?tab=insights",
    out: "phase10-insights.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  {
    // Phase 10 — Search v2: saved-search bar on the Rooms page (dropdown open).
    user: "rahim.hossain",
    route: "/rooms?q=studio",
    out: "phase10-saved-search.png",
    waitMs: 4000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const btn = [...document.querySelectorAll('button')].find(b =>
        b.textContent.includes('Saved searches'));
      if (btn) { btn.click(); return 'opened'; }
      return 'no-btn';
    })()`,
    afterLoadMs: 900,
  },
  {
    // Phase 11 — AI smart search: the query arrives via the URL (?q=...),
    // then afterLoad flips the AI Search toggle on, so the smart request
    // carries the query and the "AI understood" chips (budget, area) render
    // with the ranked results. The Bangla *word* query (দশ হাজার + উত্তরা)
    // exercises the number-word + area-alias parsing added in PR #32.
    user: "rahim.hossain",
    route: "/rooms?q=%E0%A6%A6%E0%A6%B6%20%E0%A6%B9%E0%A6%BE%E0%A6%9C%E0%A6%BE%E0%A6%B0%20%E0%A6%8F%E0%A6%B0%20%E0%A6%AE%E0%A6%A7%E0%A7%8D%E0%A6%AF%E0%A7%87%20%E0%A6%89%E0%A6%A4%E0%A7%8D%E0%A6%A4%E0%A6%B0%E0%A6%BE",
    out: "phase11-ai-search.png",
    waitMs: 6000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const btn = [...document.querySelectorAll('button')].find(b =>
        b.textContent.trim() === 'AI Search');
      if (!btn) return 'no-ai-btn';
      btn.click();
      return 'ai-on';
    })()`,
    afterLoadMs: 2500,
  },
  // Phase 11+ — voice search: the microphone button sits inside the search
  // input. Headless Chrome exposes webkitSpeechRecognition, so the mic
  // renders in its idle (ready-to-listen) state.
  {
    user: "rahim.hossain",
    route: "/rooms?q=studio",
    out: "voice-search.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const mic = document.querySelector('button[aria-label="Search by voice"]');
      return mic ? 'mic-visible' : 'no-mic';
    })()`,
    afterLoadMs: 400,
  },
  // Phase 11+ — price intelligence: the seeded Premium Studio (Mirpur) is
  // listed at ৳22,000 while the market model predicts ~৳15.6k, so its card
  // carries the "41% above market" badge (high-confidence prediction only).
  {
    user: "rahim.hossain",
    route: "/rooms?area=Mirpur",
    out: "price-anomaly.png",
    waitMs: 5500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Phase 11+ — listing quality: the landlord Insights table now carries the
  // 0-100 quality score column with level + suggestions popover on tap.
  {
    user: "rahim.hossain",
    route: "/dashboard?tab=insights",
    out: "listing-quality.png",
    waitMs: 5000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Phase 12+ — admin fraud operations: summary cards, risk filters,
  // sortable table, expandable evidence, and audited review actions.
  {
    user: "admin",
    route: "/dashboard",
    click: "fraud",
    out: "fraud-admin.png",
    waitMs: 4500,
    afterClickMs: 3000,
  },
  // Phase 11+ — AI saved-search matching: a new listing triggered a
  // "Highly relevant room found" notification; open the bell dropdown to
  // show the match reason (area/budget/similar-to-views chips).
  {
    user: "rahim.hossain",
    route: "/rooms?q=studio",
    out: "saved-search-match.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const bell = [...document.querySelectorAll('button')]
        .find(b => b.querySelector('.lucide-bell'));
      if (bell) { bell.click(); return 'opened'; }
      return 'no-bell';
    })()`,
    afterLoadMs: 1000,
  },
  // Email-OTP 2FA step: enable 2FA, sign in through the REAL login form
  // (token injection would bypass the challenge), screenshot the code step,
  // then disable 2FA again so the demo accounts stay in their default state.
  {
    otpLogin: { username: "rahim.hossain", password: DEMO_PASSWORD },
    out: "otp-verification.png",
    waitMs: 4500,
  },
  // Phase 11+ — Rentora Copilot: open the floating widget and fire the
  // Bangla example query so the assistant reply (intent chips + retrieved
  // listing cards) is on screen.
  {
    user: "rahim.hossain",
    route: "/rooms",
    out: "copilot.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(async () => {
      const open = [...document.querySelectorAll('button')]
        .find(b => b.getAttribute('aria-label') === 'Open Rentora Copilot');
      if (!open) return 'no-open-btn';
      open.click();
      await new Promise(r => setTimeout(r, 600));
      const chip = [...document.querySelectorAll('button')]
        .find(b => b.textContent.includes('Uttara'));
      if (!chip) return 'no-chip';
      chip.click();
      return 'queried';
    })()`,
    afterLoadMs: 4500,
  },
  // Phase 11+ — AI pricing suggestion v2: expand a room's "Suggestion" row
  // on the landlord Insights tab to show range, demand, confidence,
  // time-to-rent and the explicit "Use price" action.
  {
    user: "rahim.hossain",
    route: "/dashboard?tab=insights",
    out: "pricing-suggestion.png",
    waitMs: 5000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const btn = [...document.querySelectorAll('button')]
        .find(b => b.textContent.trim() === 'Suggestion');
      if (btn) { btn.click(); return 'expanded'; }
      return 'no-suggestion-btn';
    })()`,
    afterLoadMs: 2500,
  },
  // Phase 7 v2 — intelligent map: AI Smart Search. Open the AI Map panel
  // and fire the Bangla example chip so the parsed intent chips + real
  // matched rooms render next to the map (which flies to Uttara).
  {
    user: "rahim.hossain",
    route: "/map",
    out: "map-intel-ai-search.png",
    waitMs: 8000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(async () => {
      const open = [...document.querySelectorAll('button')]
        .find(b => b.textContent.includes('AI Map'));
      if (!open) return 'no-ai-map-btn';
      open.click();
      await new Promise(r => setTimeout(r, 800));
      const chip = [...document.querySelectorAll('button')]
        .find(b => b.textContent.includes('উত্তরায়'));
      if (!chip) return 'no-chip';
      chip.click();
      return 'queried';
    })()`,
    afterLoadMs: 4500,
  },
  // Phase 7 v2 — area intelligence: Areas tab with an area selected so the
  // stats card (rent, demand, metro access, trend) + compare chips render.
  {
    user: "rahim.hossain",
    route: "/map",
    out: "map-intel-areas.png",
    waitMs: 8000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(async () => {
      const open = [...document.querySelectorAll('button')]
        .find(b => b.textContent.includes('AI Map'));
      if (!open) return 'no-ai-map-btn';
      open.click();
      await new Promise(r => setTimeout(r, 800));
      const areas = [...document.querySelectorAll('button')]
        .find(b => b.textContent.trim() === 'Areas');
      if (!areas) return 'no-areas-tab';
      areas.click();
      await new Promise(r => setTimeout(r, 1200));
      const chip = [...document.querySelectorAll('button')]
        .find(b => /Uttara|Mirpur|Dhanmondi/.test(b.textContent) && b.textContent.includes('·'));
      if (!chip) return 'no-area-chip';
      chip.click();
      return 'area-selected';
    })()`,
    afterLoadMs: 2500,
  },
  // Phase 7 v2 — affordability: Budget tab with the slider set to ৳10,000
  // so the per-area % bars render.
  {
    user: "rahim.hossain",
    route: "/map",
    out: "map-intel-affordability.png",
    waitMs: 8000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(async () => {
      const open = [...document.querySelectorAll('button')]
        .find(b => b.textContent.includes('AI Map'));
      if (!open) return 'no-ai-map-btn';
      open.click();
      await new Promise(r => setTimeout(r, 800));
      const budgetTab = [...document.querySelectorAll('button')]
        .find(b => b.textContent.trim() === 'Budget');
      if (!budgetTab) return 'no-budget-tab';
      budgetTab.click();
      await new Promise(r => setTimeout(r, 1200));
      const slider = document.querySelector('#aff-budget');
      if (!slider) return 'no-slider';
      const proto = Object.getPrototypeOf(slider);
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(slider, '10000');
      slider.dispatchEvent(new Event('input', { bubbles: true }));
      slider.dispatchEvent(new Event('change', { bubbles: true }));
      return 'budget-set';
    })()`,
    afterLoadMs: 2500,
  },
  // Phase 11+ — duplicate-image fraud admin: filter the Fraud Operations
  // panel by the duplicate_image detector to show the matched-listing chips.
  // Demo data: two listings share one photo (seeded via the scan demo).
  {
    user: "admin",
    route: "/dashboard",
    click: "fraud",
    out: "duplicate-image-fraud.png",
    waitMs: 4500,
    afterClickMs: 3000,
    afterClick: `(() => {
      const sel = [...document.querySelectorAll('select')]
        .find(s => [...s.options].some(o => o.value === 'duplicate_image'));
      if (!sel) return 'no-filter';
      sel.value = 'duplicate_image';
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return 'filtered';
    })()`,
  },
  // ================= Phase 12 — Trust & Safety V2 =================
  // Tenant KYC (start): the tenant-facing identity-verification card in its
  // Start Verification state (document type + upload) for a new tenant with
  // no record yet. Seeded via backend/scripts/seed_phase12_demo.py.
  {
    user: "tenant.new",
    route: "/dashboard",
    out: "tenant-kyc-upload.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Tenant KYC (pending): the Reviewing state once a document is submitted.
  {
    user: "tenant.pending",
    route: "/dashboard",
    out: "tenant-kyc-pending.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Verified tenant badge: the chat header shows the BadgeCheck
  // "Identity verified tenant" mark next to an identity-verified tenant's
  // name (landlord's side of the seeded direct room).
  {
    user: "rahim.hossain",
    route: "/chat?room=6",
    out: "verified-tenant-badge.png",
    waitMs: 5000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Report / block UI: the conversation header ⋮ menu (Report user / Block
  // user), opened via its aria-label.
  {
    user: "rahim.hossain",
    route: "/chat?room=6",
    out: "report-block.png",
    waitMs: 5000,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const btn = document.querySelector('button[aria-label="Conversation options"]');
      if (btn) { btn.click(); return 'menu-open'; }
      return 'no-btn';
    })()`,
    afterLoadMs: 800,
  },
  // Chat safety feed: Trust Center -> Chat Safety sub-tab shows the seeded
  // MEDIUM / HIGH / CRITICAL assessments (metadata only, no raw content).
  {
    user: "admin",
    route: "/dashboard?tab=trust",
    out: "chat-safety-feed.png",
    waitMs: 4500,
    afterLoad: `(() => {
      const btn = [...document.querySelectorAll('button')]
        .find(b => b.textContent.trim() === 'Chat Safety');
      if (btn) { btn.click(); return 'opened'; }
      return 'no-btn';
    })()`,
    afterLoadMs: 1500,
  },
  // Review moderation queue: the held review (spam-ish contact info) with
  // risk signals + approve/reject actions.
  {
    user: "admin",
    route: "/dashboard?tab=moderation",
    out: "moderation-reviews.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Photo moderation queue: switch to the Photos queue to show the flagged
  // duplicate-image photo.
  {
    user: "admin",
    route: "/dashboard?tab=moderation",
    out: "moderation-photos.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const btn = [...document.querySelectorAll('button')]
        .find(b => b.textContent.trim().toLowerCase() === 'photos');
      if (btn) { btn.click(); return 'photos'; }
      return 'no-btn';
    })()`,
    afterLoadMs: 1500,
  },
  // Dispute resolution (admin): the dispute list with evidence + the
  // deposit decision affordance (release / refund / partial).
  {
    user: "admin",
    route: "/dashboard?tab=disputes",
    out: "dispute-admin.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Deposit protection (participant): the tenant's dispute card on the
  // approved booking that carries the paid security deposit.
  {
    user: "tenant.verified",
    route: "/dashboard?tab=disputes",
    out: "deposit-protection.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Admin Trust & Safety Operations Center: overview cards aggregating
  // every queue (KYC, chat safety, reports, moderation, disputes).
  {
    user: "admin",
    route: "/dashboard?tab=trust",
    out: "trust-center.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
  },
  // Audit trail: Trust Center -> Audit Trail sub-tab (append-only trail of
  // every Phase 12 decision).
  {
    user: "admin",
    route: "/dashboard?tab=trust",
    out: "audit-trail.png",
    waitMs: 4500,
    beforeCapture: `(() => {
      localStorage.setItem('rentora-ui',
        JSON.stringify({ state: { darkMode: false }, version: 0 }));
      return 'light';
    })()`,
    afterLoad: `(() => {
      const btn = [...document.querySelectorAll('button')]
        .find(b => b.textContent.trim() === 'Audit Trail');
      if (btn) { btn.click(); return 'opened'; }
      return 'no-btn';
    })()`,
    afterLoadMs: 1500,
  },
];

// ---- Helpers ----
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  for (const c of candidates) {
    try {
      fs.accessSync(c);
      return c;
    } catch {
      /* try next */
    }
  }
  throw new Error(
    "Chrome not found — set CHROME_PATH or install Google Chrome.",
  );
}

/** Enable/disable email-OTP 2FA for a user via Django shell. */
function setUserOtp(username, enabled) {
  const script = [
    "from django.contrib.auth import get_user_model;",
    `u = get_user_model().objects.get(username='${username}');`,
    `u.otp_enabled = ${enabled ? "True" : "False"};`,
    "u.save(update_fields=['otp_enabled'])",
  ].join(" ");
  execSync(`"${PY}" "${MANAGE_PY}" shell -c "${script}"`, {
    encoding: "utf8",
    cwd: path.join(ROOT, "backend"),
  });
}

/** Mint a JWT access token for a user via Django shell (bypasses login rate limits). */
function mintToken(username) {
  const script = [
    "from rest_framework_simplejwt.tokens import RefreshToken;",
    "from django.contrib.auth import get_user_model;",
    `u = get_user_model().objects.get(username='${username}');`,
    "print(str(RefreshToken.for_user(u).access_token))",
  ].join(" ");
  return execSync(`"${PY}" "${MANAGE_PY}" shell -c "${script}"`, {
    encoding: "utf8",
    cwd: path.join(ROOT, "backend"),
  })
    .trim()
    .split("\n")
    .pop()
    .trim();
}

// ---- Chrome + CDP plumbing ----
async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const chrome = spawn(
    findChrome(),
    [
      "--headless=new",
      `--remote-debugging-port=${DBG_PORT}`,
      "--no-first-run",
      "--no-default-browser-check",
      // MapLibre renders through WebGL — headless needs software GL
      // (SwiftShader) or the vector-tile map captures as a black canvas.
      "--use-gl=angle",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--disable-dev-shm-usage",
      "--user-data-dir=" + path.join(process.cwd(), ".tmp-chrome-profile"),
      "--window-size=1440,1100",
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  let ready = false;
  for (let i = 0; i < 40; i++) {
    try {
      await fetch(`http://127.0.0.1:${DBG_PORT}/json/version`);
      ready = true;
      break;
    } catch {
      await sleep(250);
    }
  }
  if (!ready) throw new Error("Chrome debugging port not ready");

  const target = await fetch(
    `http://127.0.0.1:${DBG_PORT}/json/new?about:blank`,
    { method: "PUT" },
  ).then((r) => r.json());

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = rej;
  });

  let msgId = 0;
  const pending = new Map();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve) => {
      const id = ++msgId;
      pending.set(id, resolve);
      ws.send(JSON.stringify({ id, method, params }));
    });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    return r.result?.result?.value;
  };

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });

  const navigate = async (url, waitMs) => {
    await send("Page.navigate", { url });
    await sleep(waitMs);
  };
  const setViewport = async (vp) => {
    await send("Emulation.setDeviceMetricsOverride", {
      width: vp.width,
      height: vp.height,
      deviceScaleFactor: vp.deviceScaleFactor ?? 1,
      mobile: vp.mobile ?? false,
    });
  };
  const shot = async (file) => {
    const r = await send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
    });
    const abs = path.join(OUT_DIR, file);
    fs.writeFileSync(abs, Buffer.from(r.result.data, "base64"));
    console.log(`✅ ${file} -> ${path.relative(ROOT, abs)}`);
  };
  const injectToken = (token) =>
    evaluate(`(() => {
      localStorage.setItem('rentora_access', '${token}');
      localStorage.setItem('rentora_refresh', 'x');
      return 'ok';
    })()`);

  // React controlled inputs need the native value setter + input event.
  const fillLoginForm = async (username, password) => {
    await evaluate(`(() => {
      const setVal = (el, val) => {
        const proto = Object.getPrototypeOf(el);
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const inputs = [...document.querySelectorAll('input')];
      const email = inputs.find(i => i.placeholder && i.placeholder.includes('email'));
      const pw = inputs.find(i => i.type === 'password');
      if (email) setVal(email, '${username}');
      if (pw) setVal(pw, '${password}');
      return 'filled';
    })()`);
    await sleep(400);
    const clicked = await evaluate(`(() => {
      const btn = [...document.querySelectorAll('button')]
        .find(b => b.textContent.trim() === 'Sign In');
      if (btn) { btn.click(); return 'clicked'; }
      return 'not-found';
    })()`);
    if (clicked !== "clicked") console.warn("⚠️  Sign In button not found");
  };

  for (const cap of CAPTURES) {
    // 2FA OTP step — sign in through the real form.
    if (cap.otpLogin) {
      const { username, password } = cap.otpLogin;
      setUserOtp(username, true);
      try {
        await navigate(`${FRONTEND}/`, 2500);
        await evaluate(`(() => {
          localStorage.removeItem('rentora_access');
          localStorage.removeItem('rentora_refresh');
          return 'cleared';
        })()`);
        await navigate(`${FRONTEND}/auth`, cap.waitMs ?? 4000);
        await fillLoginForm(username, password);
        await sleep(2500);
        await shot(cap.out);
      } finally {
        setUserOtp(username, false);
      }
      continue;
    }

    await navigate(`${FRONTEND}/`, 2500);
    if (cap.user) {
      const token = mintToken(cap.user);
      await injectToken(token);
    } else {
      // Logged-out capture: make sure no stale session survives.
      await evaluate(`(() => {
        localStorage.removeItem('rentora_access');
        localStorage.removeItem('rentora_refresh');
        return 'cleared';
      })()`);
    }
    if (cap.viewport) {
      await setViewport(cap.viewport);
    }
    if (cap.beforeCapture) {
      await evaluate(cap.beforeCapture);
    }
    await navigate(`${FRONTEND}${cap.route}`, cap.waitMs ?? 4000);

    if (cap.afterLoad) {
      await evaluate(cap.afterLoad);
      await sleep(cap.afterLoadMs ?? 1200);
    }

    if (cap.click) {
      const label = cap.click;
      const clicked = await evaluate(`(() => {
        const btn = [...document.querySelectorAll('button')]
          .find(b => b.textContent.trim().toLowerCase() === '${label}');
        if (btn) { btn.click(); return 'clicked'; }
        return 'not-found';
      })()`);
      if (clicked !== "clicked") {
        console.warn(`⚠️  tab "${label}" not found on ${cap.route}`);
      } else {
        console.log(`   clicked "${label}" tab`);
      }
      await sleep(cap.afterClickMs ?? 2500);
    }

    if (cap.afterClick) {
      await evaluate(cap.afterClick);
      await sleep(cap.afterClickMs ?? 1200);
    }

    await shot(cap.out);

    if (cap.resetViewport) {
      // Back to the desktop viewport so later captures aren't shot mobile-sized.
      await setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
    }
  }

  ws.close();
  chrome.kill();
  console.log("\nDone. Commit docs/screenshots/*.png with your README change.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
