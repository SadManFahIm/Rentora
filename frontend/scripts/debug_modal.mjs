import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => {
  if (m.type() === "error") console.log("CONSOLE ERROR:", m.text().slice(0, 300));
});
page.on("pageerror", (e) => console.log("PAGEERROR:", String(e).slice(0, 300)));

await page.goto("http://localhost:3001/");
await page.waitForTimeout(3000);

const info = await page.evaluate(() => {
  const skip = new Set(["Room", "Bangladesh", "", "Avatar"]);
  const imgs = [...document.querySelectorAll("img[alt]")].filter(
    (i) => !skip.has(i.alt) && i.alt.length > 3
  );
  const first = imgs[0];
  let el = first;
  let chain = [];
  for (let i = 0; i < 8 && el; i++) {
    el = el.parentElement;
    chain.push({ tag: el?.tagName, cls: String(el?.className ?? "").slice(0, 60), hasOnclick: !!(el && el.onclick) });
    if (el && typeof el.onclick === "function") break;
  }
  return { imgAlt: first?.alt, chain };
});
console.log("INFO:", JSON.stringify(info, null, 1));

// now click
const clicked = await page.evaluate(() => {
  const skip = new Set(["Room", "Bangladesh", "", "Avatar"]);
  const imgs = [...document.querySelectorAll("img[alt]")].filter(
    (i) => !skip.has(i.alt) && i.alt.length > 3
  );
  for (const img of imgs) {
    let el = img;
    for (let i = 0; i < 8 && el; i++) {
      el = el.parentElement;
      if (el && typeof el.onclick === "function") { el.click(); return img.alt; }
    }
  }
  return null;
});
console.log("CLICKED:", clicked);
await page.waitForTimeout(2500);

const after = await page.evaluate(() => {
  const dialogs = [...document.querySelectorAll('[role="dialog"]')];
  const bodies = [...document.querySelectorAll("body > div")].map((d) => d.className?.toString().slice(0, 60));
  return { dialogCount: dialogs.length, dialogText: dialogs[0]?.innerText?.slice(0, 120), bodyTopClasses: bodies.slice(-4) };
});
console.log("AFTER:", JSON.stringify(after, null, 1));
await browser.close();
