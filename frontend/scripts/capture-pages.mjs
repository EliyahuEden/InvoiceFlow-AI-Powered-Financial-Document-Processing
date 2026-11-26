// Captures every authenticated page (full page) for design review, signed in through "Try the demo".
// Usage: BASE=https://invoiceflow-demo.duckdns.org LOCALE=en node scripts/capture-pages.mjs <out-dir> [route-filter]
// Local stack (no visitor demo): SEED=1 signs in with the seeded demo account. THEME=dark, MOBILE=1 for the other variants.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const base = process.env.BASE ?? "http://localhost:3003";
const locale = process.env.LOCALE ?? "en";
const theme = process.env.THEME ?? "light";
const out = process.argv[2] ?? "../.impeccable/review/pages";
const only = process.argv[3];
mkdirSync(out, { recursive: true });
const routes = [
  ["00-overview", "/"], ["01-exceptions", "/exceptions"], ["02-invoices", "/invoices"], ["03-upload", "/invoices/upload"],
  ["04-investigations", "/investigations"], ["05-suppliers", "/suppliers"], ["06-purchase-orders", "/purchase-orders"],
  ["07-knowledge", "/knowledge"], ["08-evaluation", "/evaluation"], ["09-observability", "/observability"],
  ["10-settings", "/settings"], ["11-audit", "/audit"],
].filter(([name]) => !only || name.includes(only));

const browser = await chromium.launch();
const mobile = !!process.env.MOBILE;
const ctx = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 }, deviceScaleFactor: 1, reducedMotion: "reduce", colorScheme: theme });
await ctx.addInitScript((t) => { try { localStorage.setItem("if_theme", t); } catch {} }, theme);
await ctx.addCookies([{ name: "if_locale", value: locale, url: base }]);
const page = await ctx.newPage();
if (process.env.SEED) {
  const r = await page.request.post(`${base}/api/auth/login`, { headers: { "X-Requested-With": "invoiceflow" },
    data: { email: process.env.EMAIL ?? "finance@kinneret.example", password: process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026" } }); // demo-only seed credential
  if (!r.ok()) throw new Error(`login failed: ${r.status()}`);
} else {
  await page.goto(`${base}/login`);
  await page.getByRole("button", { name: /^(כניסה לדמו|Enter the demo)$/ }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 90_000 });
}
// DETAILS=1 adds one real detail page of each kind, found through the list APIs
if (process.env.DETAILS) {
  const first = async (path, pick = (j) => j.items?.[0]?.id) => { try { return pick(await (await page.request.get(`${base}${path}`)).json()); } catch { return null; } };
  const details = [
    ["20-invoice", await first("/api/invoices?page_size=1"), "/invoices/"], ["21-exception", await first("/api/review/queue?page_size=1", (j) => j.items?.[0]?.exception_id), "/exceptions/"],
    ["22-purchase-order", await first("/api/purchase-orders?page_size=1"), "/purchase-orders/"], ["23-supplier", await first("/api/suppliers?page_size=1"), "/suppliers/"],
    ["24-knowledge-doc", await first("/api/knowledge/documents"), "/knowledge/"], ["25-investigation", await first("/api/agent/runs?page_size=1"), "/investigations/"],
  ];
  for (const [name, id, prefix] of details) if (id && (!only || name.includes(only))) routes.push([name, prefix + id]);
}
for (const [name, route] of routes) {
  await page.goto(`${base}${route}${process.env.HASH ?? ""}`); // HASH=#team opens a section
  await page.locator("main").first().waitFor();
  await page.waitForFunction(() => document.querySelectorAll(".skeleton").length === 0, null, { timeout: 30000 }).catch(() => console.warn("still loading", route));
  // charts load after the page: wait until every chart has drawn its lines
  await page.waitForFunction(() => [...document.querySelectorAll(".recharts-responsive-container")].every((c) => c.querySelector("path.recharts-curve, path.recharts-rectangle")), null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(out, `${name}${process.env.SUFFIX ?? ""}.png`), fullPage: true });
  console.log("captured", name);
}
await browser.close();
