/**
 * Lighthouse performance gate (Phase 13 — Reach).
 *
 * Runs Lighthouse against a running frontend and fails the build when the
 * Performance score falls below a threshold, so a bad bundle never ships
 * silently. Three passes are run and the median score is used — a single
 * Lighthouse audit swings several points between identical runs, so the
 * median gives a stable gate. Usage:
 *
 *   node scripts/lighthouse-gate.mjs [url] [--min-score N] [--out DIR]
 *
 * Defaults: url http://localhost:5173, min-score 70, JSON reports written to
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
const RUNS = 3;

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

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

async function auditOnce(url, port) {
  const runnerResult = await lighthouse(url, {
    port,
    output: "json",
    logLevel: "info",
    onlyCategories: ["performance"],
  });
  if (!runnerResult) throw new Error(`Lighthouse returned no result for ${url}`);
  return runnerResult.lhr;
}

async function run(url, minScore, outDir) {
  await mkdir(outDir, { recursive: true });
  const scores = [];
  const reports = [];

  for (let i = 0; i < RUNS; i += 1) {
    const chrome = await launchChrome({
      chromeFlags: ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage"],
    });
    try {
      const lhr = await auditOnce(url, chrome.port);
      const score = Math.round((lhr.categories.performance.score ?? 0) * 100);
      scores.push(score);
      const reportPath = path.join(outDir, `lighthouse-${Date.now()}-run${i + 1}.json`);
      await writeFile(reportPath, JSON.stringify(lhr, null, 2), "utf8");
      reports.push(reportPath);
      console.log(`  run ${i + 1}/${RUNS}: performance score ${score}`);
    } finally {
      await chrome.kill();
    }
  }

  const score = median(scores);
  console.log(`Lighthouse performance score: ${score} (median of ${RUNS}, threshold ${minScore})`);
  reports.forEach((p) => console.log(`Report: ${p}`));

  if (score < minScore) {
    console.error(`FAIL: median performance score ${score} < ${minScore}.`);
    process.exit(1);
  }
  console.log("PASS: performance gate met.");
}

const { url, minScore, outDir } = parseArgs(process.argv.slice(2));
run(url, minScore, outDir).catch((err) => {
  console.error("Lighthouse gate failed:", err);
  process.exit(1);
});
