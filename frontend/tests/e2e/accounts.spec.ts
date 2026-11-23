import { createHmac } from "node:crypto";
import { expect, type APIRequestContext, type Page, test } from "@playwright/test";

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

async function signUpByApi(request: APIRequestContext, email: string): Promise<void> {
  const r = await request.post("/api/auth/signup", {
    headers: { "X-Requested-With": "invoiceflow" },
    data: { company_name: `E2E Co ${Date.now()}`, full_name: "E2E Person", email, password: PASSWORD, locale: "en" },
  });
  expect(r.status(), await r.text()).toBe(201);
}

async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

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
  await page.locator("#company").fill("Galilee Test Bakery Ltd");
  await page.locator("#name").fill("Noa Tester");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Noa Tester")).toBeVisible();
  await expect(page.getByText("Administrator").first()).toBeVisible();
  await expect(page.getByText("No exceptions match.")).toBeVisible();          // a fresh business sees none of the demo data
  const me = await (await page.request.get("/api/auth/me")).json();
  expect(me.organization.name).toBe("Galilee Test Bakery Ltd");
  // a second sign-up with the same email is refused with a clear message
  await signOut(page);
  await page.goto("/signup");
  await page.locator("#company").fill("Another Co");
  await page.locator("#name").fill("Someone Else");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("An account with this email already exists")).toBeVisible();
});

test("forgot password: the emailed link sets a new password and works only once", async ({ page, request }) => {
  const email = unique("reset");
  await signUpByApi(request, email);
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await page.locator("#email").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("reset link is on its way");

  const link = await emailedLink(request, email, "reset-password");
  await page.goto(link);
  await page.locator("#new-password").fill(NEW_PASSWORD);
  await page.locator("#confirm-password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page.getByRole("status")).toBeVisible();

  await signIn(page, email, PASSWORD);                                 // the old password no longer works
  await expect(alertIn(page)).toContainText("incorrect");
  await signIn(page, email, NEW_PASSWORD);
  await expect(page).toHaveURL(/\/$/);

  await signOut(page);
  await page.goto(link);                                                // the same link again
  await page.locator("#new-password").fill(PASSWORD);
  await page.locator("#confirm-password").fill(PASSWORD);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(alertIn(page)).toBeVisible();
});

test("an administrator invites a teammate, who chooses a password from the email and signs in", async ({ page, request }) => {
  const email = unique("invite");
  await signIn(page, "admin@kinneret.example", DEMO_PASSWORD);
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Add user" }).click();
  await page.locator("#tm-name").fill("Invited Teammate");
  await page.locator("#tm-email").fill(email);
  await page.locator("#tm-role").selectOption("finance_reviewer");
  await page.getByRole("button", { name: "Add to team" }).click();
  await expect(page.getByText(`${email} was invited.`)).toBeVisible();

  await signOut(page);
  await page.goto(await emailedLink(request, email, "accept-invite"));
  await expect(page.getByText("Choose your password")).toBeVisible();
  await page.locator("#new-password").fill(PASSWORD);
  await page.locator("#confirm-password").fill(PASSWORD);
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
  await page.locator("#tf-enable").fill(totp(secret));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByText("Save these recovery codes")).toBeVisible();
  const codes = await page.locator("ul.ltr li").allTextContents();
  expect(codes).toHaveLength(10);
  await page.getByRole("button", { name: "I saved them" }).click();

  // sign in again: the password leads to the code step, a wrong code is refused, the next app code works
  await signOut(page);
  await signIn(page, email, PASSWORD);
  await expect(page.getByText("Enter the code from your authenticator app")).toBeVisible();
  await page.locator("#code").fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(alertIn(page)).toContainText("not correct");
  await page.locator("#code").fill(totp(secret, Date.now() + 30_000)); // setup used this window; codes never replay
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/$/);

  // a recovery code also works, once
  await signOut(page);
  await signIn(page, email, PASSWORD);
  await page.getByRole("button", { name: "Use a recovery code instead" }).click();
  await page.locator("#code").fill(codes[0]!);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/settings");
  await expect(page.getByText("9 recovery codes left")).toBeVisible();
});
