#!/usr/bin/env node
/**
 * PWA validation for CI — checks the BUILT app (frontend/build), so it proves
 * the manifest/icons/sw actually ship, not just that the source files exist.
 *
 * Checks:
 *  - manifest.webmanifest parses and has the installability fields
 *  - every declared icon exists and has the advertised pixel size (PNG header)
 *  - a maskable 512 icon is declared
 *  - sw.js was copied into the build
 *  - shortcuts point at routes served by the app (presence check only)
 *
 * Usage: node scripts/validate-pwa.mjs [--dir frontend/build]
 */
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const buildDir = process.argv.includes("--dir") ? process.argv[process.argv.indexOf("--dir") + 1] : join(root, "frontend", "build");

const REQUIRED_STRING_FIELDS = ["name", "short_name", "start_url", "scope", "display", "theme_color", "background_color"];

/** Read the PNG width/height from its IHDR chunk. */
function pngSize(file) {
  const buf = readFileSync(file);
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error(`${file}: not a PNG`);
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

const problems = [];

// ---- manifest exists + parses ----
const manifestPath = join(buildDir, "manifest.webmanifest");
if (!existsSync(manifestPath)) {
  console.error(`❌ ${manifestPath} missing — manifest was not built`);
  process.exit(1);
}
let manifest;
try {
  manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
} catch (e) {
  console.error(`❌ manifest.webmanifest is not valid JSON: ${e.message}`);
  process.exit(1);
}

// ---- required string fields ----
for (const field of REQUIRED_STRING_FIELDS) {
  if (typeof manifest[field] !== "string" || !manifest[field]) problems.push(`missing/non-string "${field}"`);
}
if (manifest.display !== "standalone") problems.push(`display should be "standalone", got "${manifest.display}"`);

// ---- icons exist + real dimensions ----
const icons = Array.isArray(manifest.icons) ? manifest.icons : [];
const seen = new Set();
for (const icon of icons) {
  const src = String(icon.src || "").replace(/^\//, "");
  const file = join(buildDir, src);
  if (!existsSync(file)) {
    problems.push(`icon not in build: ${icon.src}`);
    continue;
  }
  const [w, h] = String(icon.sizes || "0x0").split("x").map(Number);
  try {
    const { width, height } = pngSize(file);
    if (width !== w || height !== h) problems.push(`${icon.src}: declared ${w}x${h} but file is ${width}x${height}`);
    seen.add(`${w}x${h}`);
  } catch (e) {
    problems.push(`${icon.src}: ${e.message}`);
  }
}
if (!seen.has("192x192")) problems.push("no 192x192 icon declared");
if (!seen.has("512x512")) problems.push("no 512x512 icon declared");
if (!icons.some((i) => i.purpose === "maskable")) problems.push("no maskable icon declared");

// ---- service worker shipped ----
if (!existsSync(join(buildDir, "sw.js"))) problems.push("sw.js missing from build");

// ---- robots.txt shipped (SEO) ----
if (!existsSync(join(buildDir, "robots.txt"))) problems.push("robots.txt missing from build");

// ---- shortcuts point at app routes ----
for (const shortcut of Array.isArray(manifest.shortcuts) ? manifest.shortcuts : []) {
  const url = String(shortcut.url || "");
  if (!/^\/(rooms|map|dashboard)/.test(url)) problems.push(`shortcut url outside app routes: ${url}`);
}

if (problems.length) {
  console.error("❌ PWA validation failed:");
  for (const p of problems) console.error(`   - ${p}`);
  process.exit(1);
}

console.log(`✅ PWA validated: ${manifest.name} (${manifest.short_name}) · ${icons.length} icons · ${(manifest.shortcuts || []).length} shortcuts · sw.js ✓ · robots.txt ✓`);
