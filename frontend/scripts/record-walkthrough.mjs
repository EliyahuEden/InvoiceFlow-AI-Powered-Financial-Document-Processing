// Records the README walkthrough video (docs/demo/invoiceflow-walkthrough.webm) from a running, seeded stack.
// It uploads a sample, asks the AI features questions and records a decision, so run it only against demo data:
//   BASE=http://localhost:3003 node scripts/record-walkthrough.mjs
// With AI keys configured, the AI segments make real model calls (a few cents with gpt-4.1-mini); offline, they
// show the offline answers instead.
// Story: sign-in → risk-first dashboard → live upload of a Hebrew invoice → fields traced on the page → three-way
// match → AI investigation → queue row opens the workspace (shared-element transition) → evidence traced to the source
// → Copilot answers with sources → reviewer decision → policy question with citations → verified audit trail.
import { chromium } from "@playwright/test";
import { mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import path from "node:path";

const base = process.env.BASE ?? "http://localhost:3003";
const password = process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026"; // demo-only credential from the seed
const out = path.resolve("../docs/demo/invoiceflow-walkthrough.webm");
const tmp = path.resolve("../.impeccable/video-tmp");
const size = { width: 1440, height: 900 };
const login = (request) => request.post(`${base}/api/auth/login`, {
  headers: { "X-Requested-With": "invoiceflow" }, data: { email: "finance@kinneret.example", password } });

rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });
const browser = await chromium.launch();

// Warm-up, not recorded: a dev server compiles each route on its first visit, which would show as long pauses.
{
  const warm = await browser.newContext();
  const p = await warm.newPage();
  await login(p.request);
  for (const route of ["/login", "/", "/invoices/upload", "/knowledge", "/audit", "/exceptions"]) {
    await p.goto(`${base}${route}`).catch(() => {});
    await p.waitForTimeout(1500);
  }
  // the first policy question loads the search and reranking models (about 40 s cold), longer than the dev proxy waits
  await p.request.post(`${base}/api/knowledge/ask`, { headers: { "X-Requested-With": "invoiceflow" }, timeout: 180000,
    data: { query: "price tolerance", mode: "hybrid_rerank", k: 5 } }).catch(() => {});
  await warm.close();
}

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
  await page.mouse.wheel(0, 700);
  await pause(3000);
  await page.mouse.wheel(0, -700);
  await pause(800);
});

await step("upload a Hebrew sample", async () => {
  await page.goto(`${base}/invoices/upload`);
  await pause(2000);
  const sample = page.getByRole("listitem").filter({ hasText: "upload_hermon_price_mismatch_he" });
  await sample.scrollIntoViewIfNeeded();
  await pause(800);
  await sample.getByRole("button").click();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  const open = page.getByRole("link", { name: /לחשבונית|Open invoice/ }).first();
  await open.waitFor({ timeout: 120000 }); // processed by the worker, or already uploaded earlier
  await pause(2500);
  await open.click();
});

await step("fields traced on the page", async () => {
  await page.locator('img[alt*="upload_hermon_price_mismatch_he"]').waitFor({ timeout: 20000 });
  await pause(3500);
});

await step("three-way match", async () => {
  await page.getByRole("link", { name: /^התאמה/ }).click();
  await page.getByText("124.00").first().waitFor({ timeout: 15000 });
  await pause(4000);
});

await step("AI investigation", async () => {
  await page.getByRole("link", { name: /חקירת AI/ }).click();
  await page.getByText("סיכום חקירה").waitFor({ timeout: 30000 });
  const empty = page.getByText("אין עדיין סיכום AI.");
  if (await empty.isVisible().catch(() => false)) {
    const run = page.getByRole("button", { name: /הפעלת חקירה/ });
    if (await run.isVisible().catch(() => false)) await run.click();
    await empty.waitFor({ state: "detached", timeout: 150000 });
  }
  await pause(2000);
  await page.mouse.wheel(0, 400);
  await pause(4500);
});

let caseNumber = null;
await step("queue row opens the workspace", async () => {
  await page.goto(`${base}/`);
  await page.locator(".recharts-surface").first().waitFor({ timeout: 20000 });
  await pause(1500);
  const row = page.locator("main ol li a").first();
  await row.scrollIntoViewIfNeeded();
  caseNumber = (await row.locator("[data-vt-source]").textContent())?.trim() ?? null;
  await pause(900);
  await row.click(); // the invoice number morphs into the workspace heading
  await page.locator('[role="region"] img').first().waitFor({ timeout: 20000 });
  await pause(4000); // the document opens on the disputed line
});

await step("evidence traced to the source", async () => {
  const total = page.locator('[data-trace-source="f:total"]');
  await total.scrollIntoViewIfNeeded();
  await pause(800);
  await total.click();
  await pause(3500); // the connector runs from the value to the page
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await pause(1000);
});

await step("Copilot answers with sources", async () => {
  await page.getByRole("button", { name: /שאלו את העוזר|Ask Copilot/ }).click();
  const box = page.getByRole("textbox", { name: /.+/ }).last();
  await box.waitFor({ timeout: 10000 });
  await pause(1200);
  const question = caseNumber ? `למה חשבונית ${caseNumber} נעצרה, ומה כדאי לעשות?` : "אילו חשבוניות ממתינות לבדיקה ולמה?";
  await box.pressSequentially(question, { delay: 30 });
  await pause(500);
  await box.press("Enter");
  await page.locator("[role='dialog'] article").first().waitFor({ timeout: 120000 });
  await pause(5000);
  await page.locator("[role='dialog'] .overflow-y-auto").first().evaluate((el) => el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }));
  await pause(4500);
  await page.keyboard.press("Escape");
  await pause(800);
});

await step("reviewer decision", async () => {
  const note = page.getByLabel("הערת סוקר");
  await note.click();
  await note.pressSequentially("נבדק מול ההזמנה והקבלה; לפי המלצת העוזר", { delay: 30 });
  await pause(800);
  const approve = page.getByRole("button", { name: "אישור הפתרון" });
  const url = page.url();
  await approve.click();
  await page.waitForURL((u) => u.toString() !== url, { timeout: 15000 }).catch(() => {});
  await pause(2500);
});

await step("policy question with citations", async () => {
  await page.goto(`${base}/knowledge`);
  await pause(1500);
  const ask = page.getByRole("textbox", { name: /שאלה|Ask|שאל/ }).first();
  await ask.click();
  await ask.pressSequentially("מהי סטיית המחיר המותרת מול הזמנת רכש?", { delay: 30 });
  await pause(500);
  await ask.press("Enter");
  await page.locator(".knowledge-answer").waitFor({ timeout: 120000 });
  await pause(4000);
  await page.mouse.wheel(0, 450);
  await pause(4000);
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
console.log("saved", out);
