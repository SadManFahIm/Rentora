/**
 * Lighthouse performance gate (Phase 13 — Reach).
 *
 * Runs Lighthouse against a running frontend and fails the build when the
 * Performance score falls below a threshold, so a bad bundle never ships
 * silently. Usage:
 *
 *   node scripts/lighthouse-gate.mjs [url] [--min-score N] [--out DIR]
 *
 * Defaults: url http://localhost:5173, min-score 70, JSON report written to
 * scripts/.lighthouse/. Lighthouse launches a local Chrome via
 * chrome-launcher (its own dependency) — no manual Chrome setup needed.
 * Exit code 0 on pass, 1 on fail (CI fails the job).
 */

import { fileURLToPath } from "node:url";
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import lighthouse from "lighthouse";
import { launch as launchChrome } from "chrome-launcher";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function parseArgs(argv) {
  const url = argv.find((a) => a.startsWith("http")) ?? "http://localhost:5173";
  const minArg = argv.find((a) => a.startsWith("--min-score="));
  const minScore = minArg ? Number(minArg.split("=")[1]) : 70;
  const outArg = argv.find((a) => a.startsWith("--out="));
  const outDir = outArg
    ? path.resolve(ROOT, outArg.split("=")[1])
    : path.join(ROOT, "scripts", ".lighthouse");
  return { url, minScore, outDir };
}

async function run(url, minScore, outDir) {
  const chrome = await launchChrome({
    chromeFlags: ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage"],
  });

  let runnerResult;
  try {
    runnerResult = await lighthouse(url, {
      port: chrome.port,
      output: "json",
      logLevel: "info",
      onlyCategories: ["performance"],
    });
  } finally {
    await chrome.kill();
  }

  if (!runnerResult) {
    console.error("Lighthouse returned no result for", url);
    process.exit(1);
  }

  const score = Math.round((runnerResult.lhr.categories.performance.score ?? 0) * 100);
  await mkdir(outDir, { recursive: true });
  const reportPath = path.join(outDir, `lighthouse-${Date.now()}.json`);
  await writeFile(reportPath, JSON.stringify(runnerResult.lhr, null, 2), "utf8");

  console.log(`Lighthouse performance score: ${score} (threshold ${minScore})`);
  console.log(`Report: ${reportPath}`);

  if (score < minScore) {
    console.error(`FAIL: performance score ${score} < ${minScore}.`);
    process.exit(1);
  }
  console.log("PASS: performance gate met.");
}

const { url, minScore, outDir } = parseArgs(process.argv.slice(2));
run(url, minScore, outDir).catch((err) => {
  console.error("Lighthouse gate failed:", err);
  process.exit(1);
});