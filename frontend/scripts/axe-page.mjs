// Quick WCAG 2.2 A/AA axe scan of one page in he/en, light/dark, desktop/phone against a local dev stack (seed login).
// Usage: node scripts/axe-page.mjs exceptions   (BASE defaults to http://localhost:3003)
import { chromium } from "@playwright/test";
import path from "node:path";
const base = process.env.BASE ?? "http://localhost:3003";
const route = `/${(process.argv[2] ?? "").replace(/^\/+/, "")}`; // "exceptions" or "/exceptions"
const AXE = path.join(process.cwd(), "node_modules", "axe-core", "axe.min.js");
const browser = await chromium.launch();
let bad = 0;
for (const locale of ["he", "en"]) for (const theme of ["light", "dark"]) for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  const ctx = await browser.newContext({ viewport: vp, colorScheme: theme, reducedMotion: "reduce" });
  await ctx.addInitScript((t) => { try { localStorage.setItem("if_theme", t); } catch {} }, theme);
  await ctx.addCookies([{ name: "if_locale", value: locale, url: base }]);
  const page = await ctx.newPage();
  await page.request.post(`${base}/api/auth/login`, { headers: { "X-Requested-With": "invoiceflow" }, data: { email: process.env.EMAIL ?? "finance@kinneret.example", password: process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026" } });
  await page.goto(`${base}${route}`);
  await page.waitForFunction(() => document.querySelectorAll(".skeleton").length === 0, null, { timeout: 30000 });
  await page.waitForTimeout(800);
  await page.addScriptTag({ path: AXE });
  const v = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] }, resultTypes: ["violations"] })).violations
    .map((x) => ({ id: x.id, impact: x.impact, n: x.nodes.length, sample: x.nodes[0]?.target?.join(" "), summary: x.nodes[0]?.failureSummary?.slice(0, 160) })));
  const serious = v.filter((x) => ["serious", "critical"].includes(x.impact));
  bad += serious.length;
  console.log(locale, theme, vp.width, v.length ? JSON.stringify(v) : "clean");
  await ctx.close();
}
await browser.close();
console.log("serious/critical:", bad);
process.exitCode = bad ? 1 : 0;
