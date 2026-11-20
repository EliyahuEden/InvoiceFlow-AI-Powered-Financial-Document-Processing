import { expect, type Request, test } from "@playwright/test";

test("every screen renders in both themes at desktop, tablet and mobile widths", async ({ page }) => {
  test.setTimeout(900_000);
  const prefetches = new Set<Request>();
  const cancelledPrefetchPaths = new Set<string>();
  const prefetchFailures: string[] = [];
  const routePath = (url: string) => { const parsed = new URL(url); return parsed.origin + parsed.pathname; };
  page.on("request", (request) => { if (new URL(request.url()).searchParams.has("_rsc")) prefetches.add(request); });
  page.on("requestfinished", (request) => prefetches.delete(request));
  page.on("requestfailed", (request) => {
    if (prefetches.has(request)) {
      const failure = request.failure()?.errorText;
      if (failure === "net::ERR_ABORTED") cancelledPrefetchPaths.add(routePath(request.url()));
      else prefetchFailures.push(`${request.url()}: ${failure}`);
    }
    prefetches.delete(request);
  });
  page.on("response", (response) => {
    if (new URL(response.url()).searchParams.has("_rsc") && response.status() >= 400) {
      prefetchFailures.push(`${response.url()}: HTTP ${response.status()}`);
    }
  });
  const settlePrefetches = async () => {
    // Let visible links schedule their prefetches, then finish them before replacing the document.
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestIdleCallback(() => resolve()))));
    await expect.poll(() => prefetches.size, { timeout: 20_000 }).toBe(0);
  };
  await page.context().addCookies([{ name: "if_locale", value: "en", url: test.info().project.use.baseURL! }]);
  await page.goto("/login");
  await page.getByLabel("Work email").fill("admin@kinneret.example");
  await page.getByLabel("Password", { exact: true }).fill(process.env.DEMO_PASSWORD ?? "InvoiceFlow!2026");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);

  const get = async (path: string) => {
    const response = await page.request.get(path);
    expect(response.ok(), path).toBeTruthy();
    return response.json();
  };
  const invoices = await get("/api/invoices?page_size=100");
  const invoice = await get(`/api/invoices/${invoices.items[0].id}`);
  const exceptions = await get("/api/exceptions?page_size=100");
  const pos = await get("/api/purchase-orders?page_size=100");
  const suppliers = await get("/api/suppliers?page_size=100");
  const runs = await get("/api/agent/runs?page_size=100");
  const run = runs.items.find((item: { status: string }) => item.status === "awaiting_approval") ?? runs.items[0];
  const knowledge = await get("/api/knowledge/documents");
  const paths = ["/", "/invoices", "/invoices/upload", "/exceptions", "/investigations", "/suppliers",
    "/purchase-orders", "/knowledge", "/evaluation", "/observability", "/audit", "/settings",
    `/invoices/${invoice.id}`, ...["reconciliation", "review", "investigation", "history"].map((tab) => `/invoices/${invoice.id}/${tab}`),
    `/exceptions/${exceptions.items[0].id}`, `/purchase-orders/${pos.items[0].id}`, `/suppliers/${suppliers.items[0].id}`,
    ...(invoice.document ? [`/documents/${invoice.document.id}`] : []),
    ...(knowledge.items.length ? [`/knowledge/${knowledge.items[0].id}`] : []),
    ...(run ? [`/investigations/${run.id}`] : [])];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await settlePrefetches();
  for (const locale of ["en", "he"]) {
    await page.context().addCookies([{ name: "if_locale", value: locale, url: test.info().project.use.baseURL! }]);
    for (const theme of ["light", "dark"]) {
      await page.evaluate((value) => { localStorage.setItem("if_theme", value); }, theme);
      for (const width of [1440, 1024, 375]) {
        await page.setViewportSize({ width, height: 900 });
        await settlePrefetches();
        for (const path of paths) {
          await test.step(`${locale} ${theme} ${width}px ${path}`, async () => {
            const response = await page.goto(path);
            expect(response?.ok(), path).toBeTruthy();
            await expect(page.locator("h1").first()).toBeVisible();
            await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
            await expect(page.locator("html")).toHaveAttribute("dir", locale === "he" ? "rtl" : "ltr");
            await expect(page.locator("main .skeleton").first()).toHaveCount(0);
            await page.evaluate(() => document.fonts.ready);
            await settlePrefetches();
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
            expect.soft(overflow, `document overflow on ${path} (${locale}, ${theme}, ${width})`).toBeLessThanOrEqual(1);
          });
        }
        console.info(`Rendered ${paths.length} screens: ${locale}, ${theme}, ${width}px`);
      }
    }
  }
  expect(prefetchFailures, "prefetch server or transport failures").toEqual([]);
  const applicationErrors = errors.filter((message) => {
    const cancelled = message.match(/^Failed to fetch RSC payload for (.+?)\. Falling back to browser navigation\./);
    // Hard navigations can cancel Next's speculative requests; require browser cancellation evidence.
    return !cancelled || !cancelledPrefetchPaths.has(routePath(cancelled[1]));
  });
  expect(applicationErrors, "uncaught exceptions or console errors during the screen sweep").toEqual([]);
});
