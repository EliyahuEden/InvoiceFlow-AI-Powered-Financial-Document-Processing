import { createHmac } from "node:crypto";
import { expect, type APIRequestContext, type Locator, type Page, test } from "@playwright/test";
import { LEGAL_VERSION } from "../../src/lib/legal";

// Account flows in the browser: sign-up, password reset by email, team invitation by email, two-factor sign-in.
// Emails are read from the stack's Mailpit inbox, so run this only against the throwaway stack
// (docker-compose.e2e.yml), never one that sends real email. Each test creates its own users.
const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8026";
const DEMO_PASSWORD = process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026"; // demo-only credential from the seed
const PASSWORD = "Correct-Horse-2026!"; // test-only, created by these tests
const NEW_PASSWORD = "Battery-Staple-2026!";

test.describe.configure({ mode: "serial" });
const english = (page: Page) =>
  page.context().addCookies([{ name: "if_locale", value: "en", url: test.info().project.use.baseURL! }]);
/** The page's own alert (Next.js also renders an empty route announcer with role=alert). */
const alertIn = (page: Page) => page.locator('[role="alert"]:not(#__next-route-announcer__)');
/** Signs out by dropping the session cookies, keeping the English interface. */
async function signOut(page: Page): Promise<void> {
  await page.context().clearCookies();
  await english(page);
}
test.beforeEach(async ({ page }) => { await english(page); });

const unique = (tag: string) => `e2e-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e4)}@example.com`;

/** Fill a field and make sure the value stuck: typing before React hydrates the page is otherwise lost. */
async function fill(field: Locator, value: string): Promise<void> {
  await expect(async () => {
    await field.fill(value);
    await expect(field).toHaveValue(value, { timeout: 1000 });
  }).toPass({ timeout: 20_000 });
}

async function signUpByApi(request: APIRequestContext, email: string): Promise<void> {
  const r = await request.post("/api/auth/signup", {
    headers: { "X-Requested-With": "invoiceflow" },
    data: { company_name: `E2E Co ${Date.now()}`, full_name: "E2E Person", email, password: PASSWORD, locale: "en",
      accepted_legal_version: LEGAL_VERSION },
  });
  expect(r.status(), await r.text()).toBe(201);
}

async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await fill(page.locator("#email"), email);
  await fill(page.locator("#password"), password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("an administrator confirms and deletes their workspace from Settings", async ({ page, request }) => {
  const email = unique("erase");
  await signUpByApi(request, email);
  await signIn(page, email, PASSWORD);
  await expect(page).toHaveURL(/\/$/);
  const user = await (await page.request.get("/api/auth/me")).json();
  await page.goto("/settings");
  await page.getByText("Delete workspace permanently", { exact: true }).first().click();
  const confirm = page.getByRole("button", { name: "Delete workspace permanently" });
  await fill(page.getByLabel("Type the workspace identifier"), user.organization.slug);
  await expect(confirm).toBeDisabled();
  await fill(page.locator("#erase-workspace-password"), PASSWORD);
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});

/** The link in the newest email to `to`, waiting for it to arrive. */
async function emailedLink(request: APIRequestContext, to: string, path: "reset-password" | "accept-invite"): Promise<string> {
  const pattern = new RegExp(`https?://[^\\s"<>]+/${path}\\?token=[A-Za-z0-9_\\-]+`);
  for (let i = 0; i < 40; i++) {
    const search = await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
    const messages = (await search.json()).messages ?? [];
    if (messages.length) {
      const message = await (await request.get(`${MAILPIT}/api/v1/message/${messages[0].ID}`)).json();
      const link = String(message.Text ?? "").match(pattern) ?? String(message.HTML ?? "").match(pattern);
      if (link) return new URL(link[0]).pathname + new URL(link[0]).search; // open it on this stack
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no ${path} email reached ${to}`);
}

/** RFC 6238 code, as an authenticator app would show it. */
function totp(secret: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/[\s=]/g, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1]! & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

test("a new business signs up and lands in its own empty workspace", async ({ page }) => {
  const email = unique("signup");
  await page.goto("/signup");
  await fill(page.locator("#company"), "Galilee Test Bakery Ltd");
  await fill(page.locator("#name"), "Noa Tester");
  await fill(page.locator("#email"), email);
  await fill(page.locator("#password"), PASSWORD);
  const create = page.getByRole("button", { name: "Create account" });
  await expect(create).toBeDisabled(); // the terms must be accepted first
  await page.getByRole("checkbox").check();
  await create.click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Noa Tester")).toBeVisible();
  await expect(page.getByText("Administrator").first()).toBeVisible();
  await expect(page.getByText("No exceptions match.")).toBeVisible();          // a fresh business sees none of the demo data
  const me = await (await page.request.get("/api/auth/me")).json();
  expect(me.organization.name).toBe("Galilee Test Bakery Ltd");
  // a second sign-up with the same email is refused with a clear message
  await signOut(page);
  await page.goto("/signup");
  await fill(page.locator("#company"), "Another Co");
  await fill(page.locator("#name"), "Someone Else");
  await fill(page.locator("#email"), email);
  await fill(page.locator("#password"), PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("An account with this email already exists")).toBeVisible();
});

test("forgot password: the emailed link sets a new password and works only once", async ({ page, request }) => {
  const email = unique("reset");
  await signUpByApi(request, email);
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page).toHaveURL(/forgot-password/);
  await fill(page.locator("#email"), email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("reset link is on its way");

  const link = await emailedLink(request, email, "reset-password");
  await page.goto(link);
  await fill(page.locator("#new-password"), NEW_PASSWORD);
  await fill(page.locator("#confirm-password"), NEW_PASSWORD);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page.getByRole("status")).toBeVisible();

  await signIn(page, email, PASSWORD);                                 // the old password no longer works
  await expect(alertIn(page)).toContainText("incorrect");
  await signIn(page, email, NEW_PASSWORD);
  await expect(page).toHaveURL(/\/$/);

  await signOut(page);
  await page.goto(link);                                                // the same link again
  await fill(page.locator("#new-password"), PASSWORD);
  await fill(page.locator("#confirm-password"), PASSWORD);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(alertIn(page)).toBeVisible();
});

test("an administrator invites a teammate, who chooses a password from the email and signs in", async ({ page, request }) => {
  const email = unique("invite");
  await signIn(page, "admin@kinneret.example", DEMO_PASSWORD);
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Add user" }).click();
  await fill(page.locator("#tm-name"), "Invited Teammate");
  await fill(page.locator("#tm-email"), email);
  await page.locator("#tm-role").selectOption("finance_reviewer");
  await page.getByRole("button", { name: "Add to team" }).click();
  await expect(page.getByText(`${email} was invited.`)).toBeVisible();

  await signOut(page);
  await page.goto(await emailedLink(request, email, "accept-invite"));
  await expect(page.getByText("Choose your password")).toBeVisible();
  await fill(page.locator("#new-password"), PASSWORD);
  await fill(page.locator("#confirm-password"), PASSWORD);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page.getByRole("status")).toBeVisible();

  await signIn(page, email, PASSWORD);
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/settings");
  await expect(page.getByText("Finance reviewer").first()).toBeVisible();
});

test("two-factor sign-in: set up with the app, then the password alone is not enough", async ({ page, request }) => {
  const email = unique("2fa");
  await signUpByApi(request, email);
  await signIn(page, email, PASSWORD);
  await expect(page).toHaveURL(/\/$/);

  await page.goto("/settings");
  await page.getByRole("button", { name: "Set up", exact: true }).click();
  await expect(page.getByRole("img", { name: "QR code for your authenticator app" })).toBeVisible();
  const secret = (await page.locator("code.ltr").textContent()) ?? "";
  await fill(page.locator("#tf-enable"), totp(secret));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByText("Save these recovery codes")).toBeVisible();
  const codes = await page.locator("ul.ltr li").allTextContents();
  expect(codes).toHaveLength(10);
  await page.getByRole("button", { name: "I saved them" }).click();

  // sign in again: the password leads to the code step, a wrong code is refused, the next app code works
  await signOut(page);
  await signIn(page, email, PASSWORD);
  await expect(page.getByText("Enter the code from your authenticator app")).toBeVisible();
  await fill(page.locator("#code"), "000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(alertIn(page)).toContainText("not correct");
  await fill(page.locator("#code"), totp(secret, Date.now() + 30_000)); // setup used this window; codes never replay
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/$/);

  // a recovery code also works, once
  await signOut(page);
  await signIn(page, email, PASSWORD);
  await page.getByRole("button", { name: "Use a recovery code instead" }).click();
  await fill(page.locator("#code"), codes[0]!);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/settings");
  await expect(page.getByText("9 recovery codes left")).toBeVisible();
});

test("an administrator resets two-factor for a teammate who lost their phone", async ({ page, request, playwright, baseURL }) => {
  const admin = unique("admin");
  const mate = unique("mate");
  await signUpByApi(request, admin);
  await signIn(page, admin, PASSWORD);
  await expect(page).toHaveURL(/\/$/);
  // the admin adds a teammate with an initial password (no invitation email)
  const add = await page.request.post("/api/org/members", {
    headers: { "X-Requested-With": "invoiceflow" },
    data: { email: mate, full_name: "Lost Phone", role: "finance_reviewer", password: PASSWORD },
  });
  expect(add.status(), await add.text()).toBe(201);

  // the teammate turns two-factor on, in their own browser context
  const theirs = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { "X-Requested-With": "invoiceflow" } });
  expect((await theirs.post("/api/auth/login", { data: { email: mate, password: PASSWORD } })).ok()).toBe(true);
  const { secret } = await (await theirs.post("/api/auth/2fa/setup")).json();
  expect((await theirs.post("/api/auth/2fa/enable", { data: { code: totp(secret) } })).ok()).toBe(true);

  await page.goto("/settings");
  const row = page.getByRole("row", { name: /Lost Phone/ });
  await expect(row.getByText("On", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "Reset two-factor · Lost Phone" }).click();
  await fill(page.getByLabel("Your password"), "wrong-password-here");
  await page.getByRole("button", { name: "Reset two-factor", exact: true }).click();
  await expect(page.getByText("The current password is not correct.")).toBeVisible();
  await fill(page.getByLabel("Your password"), PASSWORD);
  await page.getByRole("button", { name: "Reset two-factor", exact: true }).click();
  await expect(page.getByText("Two-factor reset for Lost Phone")).toBeVisible();
  await expect(row.getByText("Off", { exact: true })).toBeVisible();

  // their old session is gone, the password alone signs them in again, and they were told by email
  expect((await theirs.get("/api/auth/me")).status()).toBe(401);
  const again = await (await theirs.post("/api/auth/login", { data: { email: mate, password: PASSWORD } })).json();
  expect(again.access_token).toBeTruthy();
  const found = await (await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${mate}"`)}`)).json();
  expect(found.messages?.[0]?.Subject).toContain("two-factor");
  await theirs.dispose();
});

test("a team member must enroll before opening a workspace that requires two-factor sign-in", async ({ page, request }) => {
  const admin = unique("policy-admin");
  const mate = unique("policy-member");
  await signUpByApi(request, admin);
  await signIn(page, admin, PASSWORD);
  await expect(page).toHaveURL(/\/$/);
  const headers = { "X-Requested-With": "invoiceflow" };
  const member = await page.request.post("/api/org/members", { headers, data: {
    email: mate, full_name: "Enrollment Required", role: "finance_reviewer", password: PASSWORD,
  } });
  expect(member.status()).toBe(201);
  const setup = await page.request.post("/api/auth/2fa/setup", { headers });
  expect(setup.ok()).toBe(true);
  const enabled = await page.request.post("/api/auth/2fa/enable", { headers, data: { code: totp((await setup.json()).secret) } });
  expect(enabled.ok()).toBe(true);
  await page.goto("/settings");
  await page.getByRole("checkbox", { name: "Require two-factor sign-in for everyone" }).check();
  const saved = page.waitForResponse((response) => response.url().endsWith("/api/org/settings") && response.request().method() === "PATCH");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  expect((await saved).ok()).toBe(true);

  await signOut(page);
  await signIn(page, mate, PASSWORD);
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { name: "Set up two-factor sign-in" })).toBeVisible();
  expect((await page.request.get("/api/invoices")).status()).toBe(403);
  await page.getByRole("button", { name: "Set up", exact: true }).click();
  const secret = await page.locator("code.ltr").textContent();
  await fill(page.locator("#tf-enable"), totp(secret ?? ""));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByText("Save these recovery codes")).toBeVisible();
  await page.getByRole("button", { name: "I saved them" }).click();
  await expect(page.getByRole("heading", { name: "Organization settings" })).toBeVisible();
  expect((await page.request.get("/api/invoices")).ok()).toBe(true);
});
