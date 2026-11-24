import { readFile } from "node:fs/promises";
import { randomInt } from "node:crypto";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, baseURL }) => {
  await page.context().addCookies([{ name: "if_locale", value: "en", url: baseURL! }]);
  await page.goto("/login");
  const email = page.getByLabel("Work email");
  const password = page.getByLabel("Password", { exact: true });
  await expect(async () => {
    await email.fill("admin@kinneret.example");
    await password.fill(process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026");
    await expect(email).toHaveValue("admin@kinneret.example", { timeout: 1000 });
    await expect(password).not.toBeEmpty({ timeout: 1000 });
  }).toPass({ timeout: 20_000 });
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("supplier import rejects invalid rows and writes valid rows only after confirmation", async ({ page }) => {
  const taxId = String(randomInt(800_000_000, 900_000_000));
  const supplier = `Browser Test Supplier ${taxId}`;
  await page.goto("/suppliers");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Import from a spreadsheet" });
  const file = dialog.getByLabel("File (CSV or Excel)");
  const check = dialog.getByRole("button", { name: "Check file" });
  const commit = dialog.getByRole("button", { name: "Import", exact: true });
  const load = (id: string) => file.setInputFiles({
    name: "suppliers.csv", mimeType: "text/csv", buffer: Buffer.from(`name,tax_id\n${supplier},${id}\n`),
  });

  await load("invalid");
  await check.click();
  await expect(dialog.getByRole("alert")).toContainText("Fix these rows");
  await expect(commit).toBeDisabled();

  await load(taxId);
  await check.click();
  await expect(dialog.getByText("The file is ready to import.")).toBeVisible();
  await expect(commit).toBeEnabled();
  const before = await page.request.get(`/api/suppliers?q=${taxId}`);
  expect(before.ok()).toBeTruthy();
  expect((await before.json()).items).toEqual([]);

  await commit.click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Imported: 1")).toBeVisible();
  const after = await page.request.get(`/api/suppliers?q=${taxId}`);
  expect(after.ok()).toBeTruthy();
  expect((await after.json()).items).toEqual([expect.objectContaining({ name: supplier, tax_id: taxId })]);
});

test("invoice export downloads a CSV limited to the current search", async ({ page }) => {
  await page.goto("/invoices");
  const search = page.getByPlaceholder(/^Search:/);
  await search.fill("HC-8841");
  await expect(page.getByRole("link", { name: /^HC-8841\b/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /^TV-24518\b/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "CSV", exact: true }).first().click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/^invoices-\d{4}-\d{2}-\d{2}\.csv$/);
  const csv = await readFile(await download.path(), "utf8");
  expect(csv).toMatch(/^\uFEFFinvoice_number,supplier,/);
  expect(csv.trim().split(/\r?\n/).slice(1)).toEqual([expect.stringMatching(/^HC-8841,/)]);
});
