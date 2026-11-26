// Captures the upload page's states for design review without uploading anything: the upload and job endpoints are
// answered in the browser (one job finished, one processing, one failed, a duplicate, a rejected file), so no worker
// runs and no AI is called. The finished job points at a real invoice, so the fields it shows are real.
// Usage: BASE=http://localhost:3003 LOCALE=en node scripts/capture-upload-states.mjs <out-dir>
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const base = process.env.BASE ?? "http://localhost:3003";
const locale = process.env.LOCALE ?? "en";
const out = process.argv[2] ?? "../.impeccable/review/upload-states";
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, reducedMotion: "reduce" });
await ctx.addCookies([{ name: "if_locale", value: locale, url: base }]);
const page = await ctx.newPage();
const login = await page.request.post(`${base}/api/auth/login`, { headers: { "X-Requested-With": "invoiceflow" },
  data: { email: "finance@kinneret.example", password: process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026" } }); // demo-only seed credential
if (!login.ok()) throw new Error(`login failed: ${login.status()}`);
const list = await (await page.request.get(`${base}/api/invoices?page_size=1`)).json();
const realId = list.items[0].id;

const replies = [
  { status: 202, body: { invoice_id: realId, job_id: "job-done" } },
  { status: 202, body: { invoice_id: "00000000-0000-0000-0000-000000000002", job_id: "job-processing" } },
  { status: 202, body: { invoice_id: "00000000-0000-0000-0000-000000000003", job_id: "job-failed" } },
  { status: 409, body: { detail: { message: "This exact file was already uploaded.", invoice_id: realId } } },
  { status: 422, body: { detail: "Unsupported file type: only PDF, PNG and JPEG are accepted." } },
];
let n = 0;
await page.route("**/api/invoices/upload", (route) => { const r = replies[n++ % replies.length]; return route.fulfill({ status: r.status, json: r.body }); });
const jobs = {
  "job-done": { status: "succeeded", progress: 100, message: null, error: null, entity_id: realId },
  "job-processing": { status: "running", progress: 62, message: null, error: null, entity_id: null },
  "job-failed": { status: "failed", progress: 30, message: null, error: "The PDF could not be read.", entity_id: null },
};
await page.route("**/api/jobs/*", (route) => route.fulfill({ json: jobs[route.request().url().split("/").pop()] }));

await page.goto(`${base}/invoices/upload`);
await page.getByTestId("file-input").waitFor({ state: "attached" });
await page.waitForTimeout(1200);
await page.screenshot({ path: path.join(out, `upload-idle-${locale}.png`) });

const dt = await page.evaluateHandle(() => new DataTransfer());
await page.dispatchEvent("section[aria-label]", "dragover", { dataTransfer: dt });
await page.waitForTimeout(400);
await page.screenshot({ path: path.join(out, `upload-dragging-${locale}.png`) });
await page.dispatchEvent("section[aria-label]", "dragleave", { dataTransfer: dt });

const file = (name) => ({ name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 review placeholder") });
await page.getByTestId("file-input").setInputFiles(["hermon-oct.pdf", "tavor-24602.pdf", "scan-unreadable.pdf", "hermon-oct-copy.pdf", "notes.docx"].map(file));
await page.waitForTimeout(4500);
await page.screenshot({ path: path.join(out, `upload-jobs-${locale}.png`), fullPage: true });
await browser.close();
console.log("captured upload states to", out);
