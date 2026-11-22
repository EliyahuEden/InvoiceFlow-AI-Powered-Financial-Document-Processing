import { expect, test } from "@playwright/test";

test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to regenerate review screenshots");

test("capture the review workflow in both themes and directions", async ({ page, baseURL }) => {
  test.setTimeout(180_000);
  const login = await page.request.post("/api/auth/login", {
    headers: { "X-Requested-With": "invoiceflow" },
    data: { email: "finance@kinneret.example", password: process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026" },
  });
  expect(login.ok()).toBeTruthy();
  const queue = await page.request.get("/api/review/queue?page_size=100");
  const items = (await queue.json()).items as { exception_id: string; finding_types: string[] }[];
  const example = items.find((item) => item.finding_types.some((type) => type.startsWith("QTY_") || type === "PRICE_MISMATCH")) ?? items[0];
  expect(example).toBeDefined();
  if (!example) return;
  for (const locale of ["he", "en"]) {
    await page.context().addCookies([{ name: "if_locale", value: locale, url: baseURL! }]);
    for (const theme of ["light", "dark"]) {
      await page.goto("/");
      await page.evaluate((value) => localStorage.setItem("if_theme", value), theme);
      for (const [name, path] of [["dashboard", "/"], ["queue", "/exceptions"], ["workspace", `/exceptions/${example.exception_id}`]] as const) {
        await page.setViewportSize({ width: 1440, height: 1000 });
        await page.goto(path);
        await expect(page.locator("main .skeleton").first()).toHaveCount(0);
        await expect(page.locator("h1")).toBeVisible();
        if (name === "workspace") {
          const image = page.locator("main img").first();
          await expect(image).toBeVisible();
          await expect(page.getByTestId("discrepancy-table")).toBeVisible();
        } else await expect(page.getByRole("table").first()).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: `../docs/screenshots/review-${name}-${locale}-${theme}.png`, fullPage: name !== "workspace" });
        if (locale === "he") {
          await page.setViewportSize({ width: 375, height: 900 });
          await page.screenshot({ path: `../docs/screenshots/review-${name}-${locale}-${theme}-mobile.png`, fullPage: name !== "workspace" });
        }
      }
    }
  }
});
