import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { expect, type Page, test } from "@playwright/test";

// WCAG 2.2 A/AA scan with axe-core on the rendered screens, in both languages and both themes.
// axe finds only part of the barriers (keyboard, screen-reader and zoom checks stay manual), but a serious or
// critical axe violation is always a real defect, so those fail the test.
const AXE = path.join(process.cwd(), "node_modules", "axe-core", "axe.min.js");
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

type Violation = { id: string; impact: string; help: string; nodes: { target: string[]; html: string }[] };

// The app keeps a live-update connection open, so "network idle" never comes: wait for the content instead.
async function settled(page: Page): Promise<void> {
  await page.waitForLoadState("load");
  await page.locator("main").first().waitFor();
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout: 10_000 }).catch(() => undefined);
  await page.waitForTimeout(600);
}

async function scan(page: Page): Promise<Violation[]> {
  await settled(page);
  await page.addScriptTag({ path: AXE });
  return page.evaluate(async (tags) => {
    // @ts-expect-error axe is injected above
    const result = await window.axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] });
    return result.violations.map((v: Violation) => ({
      id: v.id, impact: v.impact, help: v.help,
      nodes: v.nodes.slice(0, 4).map((n) => ({ target: n.target, html: n.html.slice(0, 160) })),
    }));
  }, TAGS);
}

test("core screens have no serious or critical accessibility violations", async ({ page }) => {
  test.setTimeout(600_000);
  const base = test.info().project.use.baseURL!;
  const found: Record<string, Violation[]> = {};
  mkdirSync("test-results", { recursive: true });
  const record = (key: string, v: Violation[]) => {
    if (v.length) found[key] = v;
    writeFileSync("test-results/a11y-report.json", JSON.stringify(found, null, 2));
  };

  for (const locale of ["he", "en"]) {
    await page.context().addCookies([{ name: "if_locale", value: locale, url: base }]);
    for (const p of ["/login", "/signup", "/forgot-password"]) {
      await page.goto(p);
      record(`${locale} light ${p}`, await scan(page));
    }
  }

  await page.context().addCookies([{ name: "if_locale", value: "en", url: base }]);
  await page.goto("/login");
  await page.getByLabel("Work email").fill("admin@kinneret.example");
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);

  const get = async (url: string) => (await page.request.get(url)).json();
  const invoices = await get("/api/invoices?page_size=50");
  const invoice = invoices.items.find((i: { status: string }) => i.status === "exception") ?? invoices.items[0];
  const detail = await get(`/api/invoices/${invoice.id}`);
  const exceptions = await get("/api/exceptions?page_size=50");
  const paths = ["/", "/invoices", "/invoices/upload", "/exceptions", "/settings", "/knowledge", "/audit", "/suppliers",
    `/invoices/${invoice.id}`, `/invoices/${invoice.id}/review`, `/invoices/${invoice.id}/reconciliation`,
    ...(exceptions.items.length ? [`/exceptions/${exceptions.items[0].id}`] : []),
    ...(detail.document ? [`/documents/${detail.document.id}`] : [])];

  for (const locale of ["he", "en"]) {
    await page.context().addCookies([{ name: "if_locale", value: locale, url: base }]);
    for (const theme of ["light", "dark"]) {
      await page.evaluate((value) => localStorage.setItem("if_theme", value), theme);
      for (const p of paths) {
        await page.goto(p);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        record(`${locale} ${theme} ${p}`, await scan(page));
      }
    }
  }

  const blocking = Object.entries(found).flatMap(([where, vs]) =>
    vs.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${where}: ${v.id} (${v.nodes.length})`));
  expect(blocking, "serious/critical axe violations (details in test-results/a11y-report.json)").toEqual([]);
});
