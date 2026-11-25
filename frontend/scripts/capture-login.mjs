// Captures the sign-in screen (signed out) for design review: desktop and phone, Hebrew and English.
// Usage: BASE=http://localhost:3003 node scripts/capture-login.mjs <out-dir>
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const base = process.env.BASE ?? "http://localhost:3003";
const out = process.argv[2] ?? "../.impeccable/review";
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const shots = [
  ["login-desktop-he", "he", { width: 1440, height: 900 }],
  ["login-desktop-en", "en", { width: 1440, height: 900 }],
  ["login-tablet-he", "he", { width: 820, height: 1180 }],
  ["login-mobile-he", "he", { width: 390, height: 844 }],
  ["login-mobile-en", "en", { width: 390, height: 844 }],
];
for (const [name, locale, viewport] of shots) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: "reduce" });
  await ctx.addCookies([{ name: "if_locale", value: locale, url: base }]);
  const page = await ctx.newPage();
  await page.goto(`${base}/login`);
  await page.locator("#email").waitFor();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  await ctx.close();
}
await browser.close();
console.log("captured", shots.length, "to", out);
