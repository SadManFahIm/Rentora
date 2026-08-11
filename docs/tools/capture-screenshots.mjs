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
    // with the ranked results.
    user: "rahim.hossain",
    route: "/rooms?q=%E0%A7%A7%E0%A7%A6%20%E0%A6%B9%E0%A6%BE%E0%A6%9C%E0%A6%BE%E0%A6%B0%20%E0%A6%8F%E0%A6%B0%20%E0%A6%AE%E0%A6%A7%E0%A7%8D%E0%A6%AF%E0%A7%87%20uttara%20student%20room",
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
  // Email-OTP 2FA step: enable 2FA, sign in through the REAL login form
  // (token injection would bypass the challenge), screenshot the code step,
  // then disable 2FA again so the demo accounts stay in their default state.
  {
    otpLogin: { username: "rahim.hossain", password: DEMO_PASSWORD },
    out: "otp-verification.png",
    waitMs: 4500,
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
