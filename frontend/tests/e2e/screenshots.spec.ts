import { expect, type Page, test } from "@playwright/test";

// Generates the README screenshots: SCREENSHOTS=1 npx playwright test screenshots
test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to regenerate docs/screenshots");

const OUT = "../docs/screenshots";
const PASSWORD = process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026";

async function login(page: Page, email = "finance@kinneret.example") {
  await page.goto("/login");
  await page.getByLabel(/דוא"ל|Work email/).fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /^(התחברות|Sign in)$/ }).click();
  await expect(page).toHaveURL(/\/$/);
}

async function openInvoice(page: Page, number: string) {
  await page.goto(`/invoices`);
  await page.getByPlaceholder(/חיפוש|Search/).fill(number);
  await page.getByRole("link", { name: number }).first().click();
  await expect(page.getByRole("heading", { name: new RegExp(number) })).toBeVisible();
}

test("capture screenshots", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.mouse.move(1, 1); // off the chart, so no hover tooltip is captured
  await page.locator(".recharts-surface").first().waitFor();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/01-overview.png` });

  await page.goto("/invoices");
  await expect(page.getByRole("table")).toBeVisible();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/02-inbox.png` });

  await openInvoice(page, "HC-8841");
  await page.locator('img[alt*="02_qty_mismatch"]').waitFor();
  await page.getByText("סה\"כ", { exact: true }).first().hover();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/03-invoice-document.png` });

  await page.getByRole("link", { name: /^התאמה/ }).click();
  await expect(page.getByText("כמות מעל המתקבל").first()).toBeVisible();
  await page.screenshot({ path: `${OUT}/04-reconciliation.png` });

  await page.getByRole("link", { name: /חקירת AI/ }).click();
  await expect(page.getByText("סיכום חקירה")).toBeVisible();
  await page.getByRole("link", { name: /פתיחה/ }).first().click();
  await expect(page.getByTestId("discrepancy-table")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/05-exception-ai-summary.png` });

  await page.goto("/knowledge");
  await page.getByPlaceholder(/למשל/).fill("מהי סטיית המחיר המותרת בין החשבונית להזמנת הרכש?");
  await page.getByRole("button", { name: "שאלה" }).click();
  await expect(page.getByText("קטעים שאוחזרו")).toBeVisible({ timeout: 120_000 });
  await page.screenshot({ path: `${OUT}/06-knowledge-ask.png` });

  await page.goto("/evaluation");
  await expect(page.getByText("Field accuracy")).toBeVisible();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/07-evaluation.png`, fullPage: true });

  await page.goto("/observability");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${OUT}/08-observability.png` });

  await page.goto("/investigations");
  await page.getByRole("link", { name: "HC-8841" }).first().click();
  await expect(page.getByText("load_context")).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/09-agent-trace.png` });

  await openInvoice(page, "BW-2026-0425");
  await page.getByRole("button", { name: "שפה" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/10-english-prompt-injection.png` });
  await page.getByRole("button", { name: "Language" }).click();
});

test("capture import, export and account settings", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "if_locale", value: "en", url: baseURL! }]);
  await login(page, "admin@kinneret.example");

  await page.goto("/suppliers");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Import from a spreadsheet" })).toBeVisible();
  await page.screenshot({ path: `${OUT}/11-import.png`, animations: "disabled" });

  await page.goto("/invoices");
  await expect(page.getByRole("table")).toBeVisible();
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await expect(page.getByRole("menu").getByText("Approved for payment, for accounting")).toBeVisible();
  await page.screenshot({ path: `${OUT}/12-export.png`, animations: "disabled" });

  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Add user" })).toBeVisible();
  for (const [heading, file] of [["Two-factor sign-in", "13-two-factor"], ["Team", "14-team"]] as const) {
    const section = page.getByRole("heading", { name: heading, exact: true });
    await expect(section).toBeVisible();
    await section.evaluate((element) => element.scrollIntoView({ block: "center" }));
    await page.screenshot({ path: `${OUT}/${file}.png`, animations: "disabled" });
  }
});
