// Captures the knowledge page answered, for design review, without calling a paid model: the passages come from the
// real (local, free) retrieval endpoint, and the answer is the top passage quoted verbatim, the way the offline
// extractive mode answers. Usage: BASE=http://localhost:3003 LOCALE=en [THEME=dark] [MOBILE=1] node scripts/capture-knowledge-states.mjs <out-dir>
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const base = process.env.BASE ?? "http://localhost:3003";
const locale = process.env.LOCALE ?? "en";
const theme = process.env.THEME ?? "light";
const mobile = !!process.env.MOBILE;
const out = process.argv[2] ?? "../.impeccable/review/knowledge-states";
const question = locale === "he" ? "מהי סטיית המחיר המותרת בין חשבונית להזמנת רכש?" : "What are the payment terms in the BlueWave agreement?";
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 }, deviceScaleFactor: 1, reducedMotion: "reduce", colorScheme: theme });
await ctx.addInitScript((t) => { try { localStorage.setItem("if_theme", t); } catch {} }, theme);
await ctx.addCookies([{ name: "if_locale", value: locale, url: base }]);
const page = await ctx.newPage();
const login = await page.request.post(`${base}/api/auth/login`, { headers: { "X-Requested-With": "invoiceflow" },
  data: { email: "finance@kinneret.example", password: process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026" } }); // demo-only seed credential
if (!login.ok()) throw new Error(`login failed: ${login.status()}`);
const t0 = Date.now();
const api = process.env.API_BASE ?? "http://localhost:8010"; // straight to the API: the dev proxy gives up after ~30 s while models load
const found = await (await page.request.post(`${api}/api/knowledge/search`, { headers: { "X-Requested-With": "invoiceflow" }, data: { query: question, mode: "hybrid", k: 5 }, timeout: 240_000 })).json(); // the first search loads the local models
const latency = Date.now() - t0;
const hits = found.hits.map((h) => ({ ...h, preview: h.text.slice(0, 320) }));
const top = hits[0];
const answer = {
  answer: top ? top.text.split(/(?<=[.!?])\s/).slice(0, 2).join(" ") : "", abstained: !top, conflict_detected: false, mode: "offline-extractive",
  citations: hits.slice(0, 2).map((h) => ({ title: h.title, page: h.page, quote: h.text.slice(0, 180), document_id: h.document_id, chunk_id: h.chunk_id, doc_type: h.doc_type, effective_date: h.effective_date })),
  retrieval: { mode: "hybrid", latency_ms: latency, hits },
};
await page.route("**/api/knowledge/ask", (route) => route.fulfill({ json: answer }));
await page.goto(`${base}/knowledge`);
await page.getByRole("button", { name: question }).click();
await page.locator(".knowledge-answer").waitFor();
await page.waitForTimeout(800);
const suffix = `${locale}${theme === "dark" ? "-dark" : ""}${mobile ? "-mobile" : ""}`;
await page.screenshot({ path: path.join(out, `knowledge-answer-${suffix}.png`), fullPage: true });
await browser.close();
console.log("captured knowledge answer to", out);
