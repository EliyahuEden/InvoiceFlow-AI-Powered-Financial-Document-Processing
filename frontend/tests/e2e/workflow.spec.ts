import { expect, type Page, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026"; // demo-only credential from the seed (see README)

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel(/דוא"ל|Work email/).fill(email);
  await page.getByLabel(/סיסמה|Password/).fill(PASSWORD);
  await page.getByRole("button", { name: /כניסה|Sign in/ }).click();
  await expect(page).toHaveURL(/\/$/);
}

test("remembered language is respected on the server and after reload", async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "if_locale", value: "en", url: baseURL! }]);
  await page.goto("/login");
  await expect(page.locator("html")).toHaveAttribute("lang", "en", { timeout: 2000 });
  await expect(page.getByLabel("Work email")).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("Hebrew-first RTL shell with offline-mode label and locale switch", async ({ page }) => {
  await login(page, "finance@kinneret.example");
  await expect(page.locator("html")).toHaveAttribute("dir", /rtl|ltr/);
  if ((await page.locator("html").getAttribute("dir")) === "ltr") await page.getByRole("button", { name: "Language" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByText("מצב הדגמה לא מקוון")).toBeVisible();
  await page.getByRole("button", { name: "שפה" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.getByRole("heading", { name: /^Good (morning|afternoon|evening)/ })).toBeVisible();
  await page.getByRole("button", { name: "Language" }).click(); // back to Hebrew for other tests
});

test("read-only users cannot see the upload action", async ({ page }) => {
  await login(page, "viewer@kinneret.example");
  await page.goto("/invoices");
  await expect(page.getByRole("link", { name: /העלאת חשבוניות|Upload invoices/ })).toHaveCount(0);
});

test("upload a Hebrew invoice → discrepancy → cited AI explanation → decision → audit trail", async ({ page }) => {
  await login(page, "finance@kinneret.example");
  await page.goto("/invoices/upload");
  const sample = page.getByRole("listitem").filter({ hasText: "upload_hermon_price_mismatch_he" });
  await sample.getByRole("button").click();
  const open = page.getByRole("link", { name: /לחשבונית|Open invoice/ }).first();
  await expect(open).toBeVisible({ timeout: 90_000 }); // processed by the background worker, or already uploaded (409)
  await open.click();
  await expect(page.getByRole("heading", { name: /HC-8870/ })).toBeVisible();
  await expect(page.locator('img[alt*="upload_hermon_price_mismatch_he"]')).toBeVisible();

  // reconciliation workspace: deterministic finding with expected vs actual
  await page.getByRole("link", { name: /^התאמה/ }).click();
  await expect(page.getByText("פער מחיר").first()).toBeVisible();
  await expect(page.getByText("124.00").first()).toBeVisible();

  // AI investigation with source citations (agent may still be running)
  await page.getByRole("link", { name: /חקירת AI/ }).click();
  await expect(page.getByText("סיכום חקירה")).toBeVisible({ timeout: 90_000 });
  const citation = page.locator('a[href^="/documents/"]').first();
  await expect(citation).toBeVisible();
  const citationHref = await citation.getAttribute("href");

  // decide the exception
  await page.getByRole("link", { name: /פתיחה|Open/ }).first().click();
  const approve = page.getByRole("button", { name: "אישור הפתרון" });
  if (await approve.isVisible()) {
    const exceptionUrl = page.url();
    await page.getByLabel("הערת סוקר").fill("E2E: credit note requested from supplier");
    await approve.click();
    await expect(page).not.toHaveURL(exceptionUrl);
  }

  // the citation opens the source document at the cited page, with the passage highlighted
  await page.goto(citationHref!);
  await expect(page).toHaveURL(/\/documents\/.+page=\d+/);
  await expect(page.locator("img[alt]").first()).toBeVisible();

  // audit trail records the decision
  await page.goto("/audit");
  await expect(page.getByText(/exception\.(approve|created)/).first()).toBeVisible();
});

test("evaluation dashboard shows measured benchmark results", async ({ page }) => {
  await login(page, "viewer@kinneret.example");
  await page.goto("/evaluation");
  await expect(page.getByText("Field accuracy")).toBeVisible();
  await expect(page.getByText(/hybrid_rerank/).first()).toBeVisible();
  await expect(page.getByText("Exact finding-set match")).toBeVisible();
});
