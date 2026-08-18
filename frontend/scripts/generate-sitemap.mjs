/**
 * Sitemap generator (Phase 13 — SEO reach).
 *
 * Derives the area slugs from the single source of truth in
 * `src/data/areas.ts` (extracting the `area:` strings with the same slug
 * rule the app uses) and rewrites `public/sitemap.xml`. Run after adding or
 * renaming an area:
 *
 *   npm run generate:sitemap
 *
 * `SITEMAP_BASE_URL` overrides the default production placeholder
 * (https://rentora.example.com) until the real domain is live.
 */

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const AREAS_SRC = path.join(ROOT, "src", "data", "areas.ts");
const SITEMAP = path.join(ROOT, "public", "sitemap.xml");
const BASE_URL = (process.env.SITEMAP_BASE_URL || "https://rentora.example.com").replace(/\/$/, "");

const areaToSlug = (area) => area.trim().toLowerCase().replace(/\s+/g, "-");

async function main() {
  const source = await readFile(AREAS_SRC, "utf8");
  const areaMatches = [...source.matchAll(/^\s*area:\s*"([^"]+)",$/gm)].map((m) => m[1]);

  const corePaths = ["/", "/rooms", "/map", "/roommates", "/chat"];
  const areaPaths = areaMatches.map((a) => `/rooms/${areaToSlug(a)}`);

  const paths = [...corePaths, ...areaPaths];
  const urls = paths
    .map(
      (p) =>
        `  <url>\n    <loc>${BASE_URL}${p === "/" ? "/" : p}</loc>\n    <changefreq>daily</changefreq>\n    <priority>${p === "/" ? "1.0" : "0.8"}</priority>\n  </url>`
    )
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`;

  await writeFile(SITEMAP, xml, "utf8");
  console.log(
    `Generated ${SITEMAP} with ${paths.length} URLs (${areaMatches.length} area pages) for ${BASE_URL}`
  );
}

main().catch((err) => {
  console.error("Failed to generate sitemap:", err);
  process.exit(1);
});