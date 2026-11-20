import { expect, type Page, test } from "@playwright/test";

// Run against a disposable offline seed: decisions deliberately change demo records.
test.describe.configure({ mode: "serial" });

async function login(page: Page, email = "finance@kinneret.example") {
  await page.context().addCookies([{ name: "if_locale", value: "en", url: test.info().project.use.baseURL! }]);
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
}

async function nextItem(page: Page) {
  const response = await page.request.get("/api/review/next");
  expect(response.ok()).toBeTruthy();
  return (await response.json()).item as { exception_id: string; invoice_id: string } | null;
}

test("dashboard → backend's next priority → evidence → decision → next item", async ({ page }) => {
  await login(page);
  const first = await nextItem(page);
  expect(first).not.toBeNull();
  await page.getByTestId("review-next").first().click();
  await expect(page).toHaveURL(new RegExp(`/exceptions/${first!.exception_id}$`));
  await expect(page.getByTestId("discrepancy-table")).toBeVisible();
  await expect(page.locator('img[alt*="document"], img[alt*="pdf"]').first()).toBeVisible();
  await page.getByLabel("Reviewer note").fill("E2E: reviewed source evidence; record resolution and advance.");
  const decision = page.waitForResponse((response) => response.url().endsWith(`/api/exceptions/${first!.exception_id}/decision`)
    && response.request().method() === "POST");
  await page.getByRole("button", { name: "Approve resolution", exact: true }).click();
  expect((await decision).ok()).toBeTruthy();
  await expect(page).not.toHaveURL(new RegExp(`/exceptions/${first!.exception_id}$`));
  const next = await nextItem(page);
  if (next) await expect(page).toHaveURL(new RegExp(`/exceptions/${next.exception_id}$`));
  else await expect(page.getByTestId("queue-clear")).toBeVisible();
  const decided = await page.request.get(`/api/exceptions/${first!.exception_id}`);
  expect((await decided.json()).decision_note).toContain("E2E: reviewed source evidence");
});

test("dirty reviewer work survives a cancelled navigation", async ({ page }) => {
  await login(page);
  const item = await nextItem(page);
  expect(item).not.toBeNull();
  await page.goto(`/exceptions/${item!.exception_id}`);
  const note = page.getByLabel("Reviewer note");
  await note.fill("E2E unsaved draft — keep this note");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: /Exceptions/ }).first().click();
  await expect(page).toHaveURL(new RegExp(`/exceptions/${item!.exception_id}$`));
  await expect(note).toHaveValue("E2E unsaved draft — keep this note");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("link", { name: /Exceptions/ }).first().click();
  await expect(page).toHaveURL(/\/exceptions$/);
});

test("a concurrent decision preserves the draft and advances", async ({ page }) => {
  await login(page);
  const item = await nextItem(page);
  expect(item).not.toBeNull();
  await page.goto(`/exceptions/${item!.exception_id}`);
  await page.getByLabel("Reviewer note").fill("E2E conflict note retained for follow-up");
  // A real second actor's decision creates the conflict, without mocking the endpoint.
  const response = await page.request.post(`/api/exceptions/${item!.exception_id}/decision`, {
    headers: { "X-Requested-With": "invoiceflow" },
    data: { decision: "approve", note: "E2E concurrent reviewer" },
  });
  expect(response.ok()).toBeTruthy();
  await page.getByRole("button", { name: "Approve resolution", exact: true }).click();
  await expect(page).not.toHaveURL(new RegExp(`/exceptions/${item!.exception_id}$`));
  const drafts = await page.evaluate(() => Object.values(sessionStorage));
  expect(drafts.some((draft) => draft.includes("E2E conflict note retained"))).toBeTruthy();
});

test("edited extraction fields block the shell's next-priority navigation", async ({ page }) => {
  await login(page);
  const item = await nextItem(page);
  expect(item).not.toBeNull();
  await page.goto(`/invoices/${item!.invoice_id}/review`);
  const field = page.locator('main input').first();
  await expect(field).toBeVisible();
  await field.fill("E2E unsaved correction");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByTestId("review-next").first().click();
  await expect(page).toHaveURL(new RegExp(`/invoices/${item!.invoice_id}/review$`));
  await expect(field).toHaveValue("E2E unsaved correction");
});

test("the final decision shows queue clear when next returns no item", async ({ page }) => {
  await login(page);
  const item = await nextItem(page);
  expect(item).not.toBeNull();
  await page.goto(`/exceptions/${item!.exception_id}`);
  await page.getByLabel("Reviewer note").fill("E2E final item");
  // Keep the fixture's remaining invoices for other scenarios; exercise the empty response at the boundary.
  await page.route("**/api/review/next?after=*", (route) => route.fulfill({ json: { item: null, position: 0, total: 0 } }));
  await page.getByRole("button", { name: "Approve resolution", exact: true }).click();
  await expect(page.getByTestId("queue-clear")).toBeVisible();
});

test("read-only review stays read-only", async ({ page }) => {
  await login(page, "viewer@kinneret.example");
  await expect(page.getByTestId("review-next")).toHaveCount(0);
  expect(await nextItem(page)).toBeNull();
  await page.goto("/exceptions");
  await expect(page.getByRole("table").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve resolution", exact: true })).toHaveCount(0);
});

test("mobile review exposes demo mode, priority evidence and the next action", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await login(page);
  await expect(page.getByText("Offline demo", { exact: true })).toBeVisible({ timeout: 2000 });
  await page.goto("/exceptions");
  const rows = page.getByTestId("mobile-review-queue");
  await expect(rows).toBeVisible();
  const first = rows.getByRole("listitem").first();
  await expect(first.getByRole("link", { name: "Investigate", exact: true })).toBeVisible();
  await expect(first.getByText("Money at risk", { exact: true })).toBeVisible();
  await expect(first.getByText("Due date", { exact: true })).toBeVisible();
  expect(await rows.evaluate((element) => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
});
