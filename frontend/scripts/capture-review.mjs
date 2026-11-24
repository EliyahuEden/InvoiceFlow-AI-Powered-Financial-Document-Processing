// Captures the Aurora review screenshots (design finish review) from a running app. Read-only: signs in with the
// demo account and visits pages. Usage: BASE=http://localhost:3003 node scripts/capture-review.mjs <out-dir>
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const base = process.env.BASE ?? "http://localhost:3003";
const out = process.argv[2] ?? ".impeccable/review";
const password = process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026"; // demo-only credential from the seed
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
async function shoot(name, url, { width, height, theme = "light", fullPage = true, charts = false, before }) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, reducedMotion: "reduce" });
  const page = await ctx.newPage();
  await page.addInitScript((t) => { try { localStorage.setItem("if_theme", t); } catch {} }, theme);
  await page.request.post(`${base}/api/auth/login`, { headers: { "X-Requested-With": "invoiceflow" },
    data: { email: "finance@kinneret.example", password } });
  await page.goto(`${base}${url}`);
  await page.locator("main").first().waitFor();
  // Data first: wait until loading skeletons are gone.
  await page.waitForFunction(() => document.querySelectorAll(".skeleton").length === 0, null, { timeout: 30000 })
    .catch(() => console.warn(`still loading on ${url}`));
  // Recharts mounts lazily and measures after first paint. On pages that show charts, require at least one drawn
  // chart and fail rather than save a blank panel as evidence.
  if (charts) await page.waitForFunction(() => {
    const boxes = [...document.querySelectorAll(".recharts-responsive-container")];
    return boxes.length > 0 && boxes.every((c) => (c.querySelector("svg.recharts-surface")?.getBoundingClientRect().width ?? 0) > 0);
  }, null, { timeout: 20000 });
  await page.waitForTimeout(1500);
  if (before) { await before(page); await page.waitForTimeout(800); }
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage });
  await ctx.close();
}

const queue = await (async () => {
  const ctx = await browser.newContext();
  const r = await ctx.request.post(`${base}/api/auth/login`, { headers: { "X-Requested-With": "invoiceflow" },
    data: { email: "finance@kinneret.example", password } });
  if (!r.ok()) throw new Error(`login failed: ${r.status()}`);
  const q = await (await ctx.request.get(`${base}/api/review/queue?page_size=20`)).json();
  await ctx.close();
  return q.items ?? [];
})();
const caseId = (queue.find((i) => (i.finding_types ?? []).includes("QUANTITY_EXCEEDS_RECEIVED")) ?? queue[0])?.exception_id;

await shoot("desktop", "/", { width: 1440, height: 900, charts: true });
await shoot("mobile", "/", { width: 375, height: 812, charts: true });
await shoot("desktop-dark", "/", { width: 1440, height: 900, theme: "dark", charts: true });
// viewport-sized: full-page capture mis-renders the sticky, height-capped document column
if (caseId) await shoot("workspace-desktop", `/exceptions/${caseId}`, { width: 1600, height: 1000, fullPage: false });
// the evidence trace in use: pick the invoice total, so the connector and the zoomed, centred highlight are visible
if (caseId) await shoot("workspace-traced", `/exceptions/${caseId}`, { width: 1600, height: 1000, fullPage: false,
  before: async (page) => {
    const row = page.locator('[data-trace-source="f:total"]');
    await row.scrollIntoViewIfNeeded();
    await row.click();
    await page.locator("svg.fixed path").waitFor({ timeout: 5000 });
  } });
await shoot("upload-desktop", "/invoices/upload", { width: 1440, height: 900 });
await shoot("login-desktop", "/login", { width: 1440, height: 900, fullPage: false });
await browser.close();
console.log("captured to", out);
