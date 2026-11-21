import { expect, test } from "@playwright/test";

const stage = process.env.DESIGN_CAPTURE;
test.skip(stage !== "before" && stage !== "after", "set DESIGN_CAPTURE=before or after to capture the redesign");

test("capture core and representative document, AI and record screens", async ({ page, baseURL }) => {
  test.setTimeout(360_000);
  const login = await page.request.post("/api/auth/login", {
    headers: { "X-Requested-With": "invoiceflow" },
    data: { email: "finance@kinneret.example", password: process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026" },
  });
  expect(login.ok()).toBeTruthy();
  const get = async (path: string) => {
    const response = await page.request.get(path);
    expect(response.ok(), path).toBeTruthy();
    return response.json();
  };
  const queue = await get("/api/review/queue?page_size=100");
  const example = queue.items.find((item: { finding_types: string[] }) => item.finding_types.some((type) => type.startsWith("QTY_") || type === "PRICE_MISMATCH")) ?? queue.items[0];
  expect(example).toBeDefined();
  const invoice = await get(`/api/invoices/${example.invoice_id}`);
  const pos = await get("/api/purchase-orders?page_size=100");
  const routes: [string, string][] = [
    ["dashboard", "/"], ["queue", "/exceptions"], ["workspace", `/exceptions/${example.exception_id}`],
    ["inbox", "/invoices"], ["upload", "/invoices/upload"], ["extraction", `/invoices/${invoice.id}/review`],
    ["knowledge", "/knowledge"], ["evaluation", "/evaluation"],
    ["purchase-order", `/purchase-orders/${invoice.purchase_order?.id ?? pos.items[0].id}`],
  ];
  for (const locale of ["en", "he"]) {
    await page.context().addCookies([{ name: "if_locale", value: locale, url: baseURL! }]);
    await page.goto("/");
    for (const theme of ["light", "dark"]) {
      await page.evaluate((value) => localStorage.setItem("if_theme", value), theme);
      for (const [name, path] of routes) {
        await page.setViewportSize({ width: 1440, height: 1000 });
        await page.goto(path);
        await expect(page.locator("h1").first()).toBeVisible();
        await expect(page.locator("main .skeleton").first()).toHaveCount(0);
        if (name === "knowledge") {
          await page.getByPlaceholder(/למשל/).fill(locale === "he" ? "מהי סטיית המחיר המותרת בין החשבונית להזמנת הרכש?" : "What price variance is allowed between an invoice and its purchase order?");
          await page.getByRole("button", { name: /^(שאלה|Ask)$/ }).click();
          await expect(page.getByText(/קטעים שאוחזרו|Retrieved passages/).first()).toBeVisible();
        }
        if (name === "workspace" || name === "extraction") {
          await expect(page.locator("main img").first()).toBeVisible();
          await expect.poll(() => page.locator("main img").first().evaluate((element) => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
        }
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: `../docs/screenshots/command-center/${stage}/${name}-${locale}-${theme}.png`, fullPage: !["workspace", "extraction"].includes(name) });
        if (locale === "he" && ["dashboard", "queue", "workspace"].includes(name)) {
          await page.setViewportSize({ width: 375, height: 900 });
          await page.screenshot({ path: `../docs/screenshots/command-center/${stage}/${name}-${locale}-${theme}-mobile.png`, fullPage: name !== "workspace" });
        }
      }
    }
  }
});
