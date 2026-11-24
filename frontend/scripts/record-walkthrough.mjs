// Records the README walkthrough video (docs/demo/invoiceflow-walkthrough.webm) from a running, seeded, OFFLINE stack.
// It uploads a sample and records a decision, so run it only against a disposable stack (the e2e stack on :3001):
//   BASE=http://localhost:3001 node scripts/record-walkthrough.mjs
// Story: sign-in → risk-first dashboard → live upload of a Hebrew invoice → fields traced on the page → three-way match
// → cited AI investigation → the investigation workspace (evidence traced to the source) → a reviewer decision → the
// verified, hash-chained audit trail.
import { chromium } from "@playwright/test";
import { mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import path from "node:path";

const base = process.env.BASE ?? "http://localhost:3001";
const password = process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026"; // demo-only credential from the seed
const out = path.resolve("../docs/demo/invoiceflow-walkthrough.webm");
const tmp = path.resolve("../.impeccable/video-tmp");
const size = { width: 1440, height: 900 };

rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: size, recordVideo: { dir: tmp, size }, deviceScaleFactor: 1 });
await ctx.addInitScript(() => { try { localStorage.setItem("if_theme", "light"); } catch {} });
const page = await ctx.newPage();
const pause = (ms) => page.waitForTimeout(ms);
const step = async (name, fn) => {
  try { await fn(); console.log("✓", name); } catch (e) { console.warn("✗", name, String(e).split("\n")[0]); }
};

await step("sign-in", async () => {
  await page.goto(`${base}/login`);
  await pause(2500);
  await page.getByLabel(/דוא"ל|Work email/).pressSequentially("finance@kinneret.example", { delay: 25 });
  await page.getByLabel(/סיסמה|Password/).fill(password);
  await pause(400);
  await page.getByRole("button", { name: /כניסה|Sign in/ }).click();
  await page.waitForURL(/\/$/);
});

await step("dashboard", async () => {
  await page.mouse.move(1300, 400); // rest the pointer on the sidebar, not on the chart (no hover tooltip)
  await page.locator(".recharts-surface").first().waitFor({ timeout: 20000 });
  await pause(4500);
  await page.mouse.wheel(0, 500);
  await pause(2500);
  await page.mouse.wheel(0, -500);
  await pause(800);
});

let invoiceHref = null;
await step("upload a Hebrew sample", async () => {
  await page.goto(`${base}/invoices/upload`);
  await pause(2000);
  const sample = page.getByRole("listitem").filter({ hasText: "upload_hermon_price_mismatch_he" });
  await sample.scrollIntoViewIfNeeded();
  await pause(800);
  await sample.getByRole("button").click();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  const open = page.getByRole("link", { name: /לחשבונית|Open invoice/ }).first();
  await open.waitFor({ timeout: 120000 });
  await pause(2500);
  invoiceHref = await open.getAttribute("href");
  await open.click();
});

await step("fields traced on the page", async () => {
  await page.locator('img[alt*="upload_hermon_price_mismatch_he"]').waitFor({ timeout: 20000 });
  await pause(2000);
  const fields = page.locator("[data-field], [aria-describedby]").filter({ hasText: /\d/ });
  const n = Math.min(await fields.count(), 4);
  for (let i = 0; i < n; i++) { await fields.nth(i).hover().catch(() => {}); await pause(900); }
  await pause(1000);
});

await step("three-way match", async () => {
  await page.getByRole("link", { name: /^התאמה/ }).click();
  await page.getByText("124.00").first().waitFor({ timeout: 15000 });
  await pause(4000);
});

await step("cited AI investigation", async () => {
  await page.getByRole("link", { name: /חקירת AI/ }).click();
  await page.getByText("סיכום חקירה").waitFor({ timeout: 90000 });
  await pause(4500);
});

await step("investigation workspace", async () => {
  const queue = await (await page.request.get(`${base}/api/review/queue?page_size=20`)).json();
  const item = (queue.items ?? []).find((i) => (i.finding_types ?? []).includes("QUANTITY_EXCEEDS_RECEIVED")) ?? queue.items?.[0];
  await page.goto(`${base}/exceptions/${item.exception_id}`);
  await page.locator('[role="region"] img').first().waitFor({ timeout: 20000 });
  await pause(4000); // the document opens on the disputed line
  const total = page.locator('[data-trace-source="f:total"]');
  await total.scrollIntoViewIfNeeded();
  await pause(800);
  await total.click();
  await pause(3500); // the connector runs from the value to the page
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await pause(1200);
});

await step("reviewer decision", async () => {
  const note = page.getByLabel("הערת סוקר");
  await note.click();
  await note.pressSequentially("זיכוי על 10 יחידות שלא התקבלו", { delay: 35 });
  await pause(800);
  const approve = page.getByRole("button", { name: "אישור הפתרון" });
  const url = page.url();
  await approve.click();
  await page.waitForURL((u) => u.toString() !== url, { timeout: 15000 }).catch(() => {});
  await pause(2500);
});

await step("verified audit trail", async () => {
  await page.goto(`${base}/audit`);
  await pause(2000);
  await page.getByRole("button", { name: /אימות שרשרת|Verify chain/ }).click();
  await page.locator("main .text-ok").first().waitFor({ timeout: 15000 }); // "chain intact · N records"
  await pause(4500);
});

await ctx.close();
await browser.close();
const video = readdirSync(tmp).find((f) => f.endsWith(".webm"));
if (!video) throw new Error("no video was recorded");
renameSync(path.join(tmp, video), out);
rmSync(tmp, { recursive: true, force: true });
console.log("saved", out, invoiceHref ? `(uploaded ${invoiceHref})` : "");
