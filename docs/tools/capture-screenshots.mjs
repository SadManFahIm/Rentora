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
const OUT_DIR = process.env.OUT_DIR ?? path.join(process.cwd(), "docs", "screenshots");

const ROOT = path.join(import.meta.dirname, "..", ".."); // repo root
const MANAGE_PY = path.join(ROOT, "backend", "manage.py");
const PY = process.env.PYTHON ?? (process.platform === "win32"
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
    "Chrome not found — set CHROME_PATH or install Google Chrome."
  );
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
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--user-data-dir=" + path.join(process.cwd(), ".tmp-chrome-profile"),
      "--window-size=1440,1100",
      "about:blank",
    ],
    { stdio: "ignore" }
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
    { method: "PUT" }
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

  for (const cap of CAPTURES) {
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
    await navigate(`${FRONTEND}${cap.route}`, cap.waitMs ?? 4000);

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
  }

  ws.close();
  chrome.kill();
  console.log("\nDone. Commit docs/screenshots/*.png with your README change.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
