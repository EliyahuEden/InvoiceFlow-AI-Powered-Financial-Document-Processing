import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiKeysPanel, WebhooksPanel } from "@/components/integrations-panel";
import { dictionaries } from "@/lib/i18n/dictionaries";
import { I18nProvider } from "@/lib/i18n";

const post = vi.fn();
const patch = vi.fn();
const del = vi.fn();
const mutate = vi.fn();
const responses: Record<string, unknown> = {};

vi.mock("@/lib/api", () => ({
  api: { post: (...a: unknown[]) => post(...a), patch: (...a: unknown[]) => patch(...a), del: (...a: unknown[]) => del(...a) },
  ApiError: class ApiError extends Error { constructor(public status: number, public detail: unknown) { super(String(detail)); } },
  useApi: (path: string) => ({ data: responses[path], error: undefined, mutate, isValidating: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const ago = (ms: number) => new Date(Date.now() - ms).toISOString();
const KEYS = { items: [
  { id: "k1", name: "ERP sync", scope: "read_write", prefix: "ifk_AbCd1234", created_at: ago(864e5 * 3), last_used_at: ago(120e3), revoked_at: null },
  { id: "k2", name: "Old report", scope: "read", prefix: "ifk_ZzZz9999", created_at: ago(864e5 * 30), last_used_at: null, revoked_at: ago(864e5) },
] };
const HOOKS = { event_types: ["invoice.approved", "payment.approved", "exception.opened"], items: [
  { id: "w1", url: "https://erp.example.com/hooks/invoiceflow", description: "ERP", events: ["invoice.approved", "exception.opened"], active: true,
    secret_hint: "x7Qa", created_at: ago(864e5) },
  { id: "w2", url: "https://paused.example.com/in", description: null, events: ["payment.approved"], active: false, secret_hint: "mm01", created_at: ago(864e5) },
] };
const LOG = { items: [
  { id: "d1", event_type: "invoice.approved", is_test: false, status: "succeeded", attempts: 1, last_status_code: 200, last_error: null,
    created_at: ago(60e3), next_attempt_at: null, delivered_at: ago(59e3), attempt_log: [] },
  { id: "d2", event_type: "exception.opened", is_test: false, status: "retrying", attempts: 2, last_status_code: 503,
    last_error: "The receiver answered with HTTP 503", created_at: ago(300e3), next_attempt_at: new Date(Date.now() + 600e3).toISOString(), delivered_at: null, attempt_log: [] },
  { id: "d3", event_type: "webhook.test", is_test: true, status: "failed", attempts: 6, last_status_code: null,
    last_error: "The URL points to a private or internal address", created_at: ago(864e5), next_attempt_at: null, delivered_at: null, attempt_log: [] },
] };

beforeEach(() => {
  Object.assign(responses, { "/api/org/api-keys": KEYS, "/api/org/webhooks": HOOKS, "/api/org/webhooks/w1/deliveries?page_size=20": LOG });
  post.mockResolvedValue({ secret: "ifk_SECRET_SHOWN_ONCE" });
  patch.mockResolvedValue({}); del.mockResolvedValue({});
  Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });
});
afterEach(() => { cleanup(); post.mockReset(); patch.mockReset(); del.mockReset(); mutate.mockClear(); });

const show = (ui: React.ReactElement, locale: "en" | "he" = "en") => render(<I18nProvider initial={locale}>{ui}</I18nProvider>);

describe("API keys", () => {
  it("lists keys with their access, last use and revoked state, never a secret", () => {
    show(<ApiKeysPanel />);
    const active = screen.getByText("ERP sync").closest("tr")!;
    expect(within(active).getByText("Read and upload")).toBeVisible();
    expect(within(active).getByText(/ifk_AbCd1234/)).toBeVisible();
    expect(within(active).getByRole("button", { name: /Revoke · ERP sync/ })).toBeVisible();
    const old = screen.getByText("Old report").closest("tr")!;
    expect(within(old).getByText("Revoked")).toBeVisible();
    expect(within(old).getByText("Never used")).toBeVisible();
    expect(within(old).queryByRole("button")).toBeNull();
  });

  it("creates a key, shows the secret once, and hides it when it is stored", async () => {
    show(<ApiKeysPanel />);
    fireEvent.click(screen.getByRole("button", { name: /New key/ }));
    const create = screen.getByRole("button", { name: "Create key" });
    expect(create).toBeDisabled(); // a name is required
    fireEvent.change(screen.getByLabelText("Key name"), { target: { value: "  Warehouse scanner " } });
    fireEvent.click(screen.getByRole("radio", { name: /Read and upload/ }));
    fireEvent.click(create);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/org/api-keys", { name: "Warehouse scanner", scope: "read_write" }));
    const secret = await screen.findByTestId("one-time-secret");
    expect(secret).toHaveTextContent("ifk_SECRET_SHOWN_ONCE");
    expect(mutate).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("ifk_SECRET_SHOWN_ONCE"));
    fireEvent.click(screen.getByRole("button", { name: "I have stored it" }));
    expect(screen.queryByTestId("one-time-secret")).toBeNull();
  });

  it("defaults a new key to read-only", async () => {
    show(<ApiKeysPanel />);
    fireEvent.click(screen.getByRole("button", { name: /New key/ }));
    fireEvent.change(screen.getByLabelText("Key name"), { target: { value: "Reports" } });
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/org/api-keys", { name: "Reports", scope: "read" }));
  });

  it("asks before revoking, then revokes", async () => {
    show(<ApiKeysPanel />);
    fireEvent.click(screen.getByRole("button", { name: /Revoke · ERP sync/ }));
    expect(del).not.toHaveBeenCalled();
    expect(screen.getByText(/stop working immediately/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Revoke key" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/api/org/api-keys/k1"));
  });

  it("is translated to Hebrew", () => {
    show(<ApiKeysPanel />, "he");
    expect(screen.getByText("מפתחות API")).toBeVisible();
    expect(screen.getByText("קריאה והעלאה")).toBeVisible();
    expect(screen.getByText("טרם נעשה בו שימוש")).toBeVisible();
  });
});

describe("webhooks", () => {
  it("lists endpoints with their events, secret hint and off state", () => {
    show(<WebhooksPanel />);
    const first = screen.getByText("https://erp.example.com/hooks/invoiceflow").closest("li")!;
    expect(within(first).getByText(/Invoice approved · Exception opened/)).toBeVisible();
    expect(within(first).getByText("x7Qa")).toBeVisible();
    const second = screen.getByText("https://paused.example.com/in").closest("li")!;
    expect(within(second).getByText("Off")).toBeVisible();
    expect(within(second).getByRole("button", { name: "Switch on" })).toBeVisible();
  });

  it("needs a URL and at least one event, then registers and shows the signing secret once", async () => {
    show(<WebhooksPanel />);
    fireEvent.click(screen.getByRole("button", { name: /New webhook/ }));
    const add = screen.getByRole("button", { name: "Add webhook" });
    fireEvent.change(screen.getByLabelText("Endpoint URL"), { target: { value: " https://hooks.example.org/in " } });
    expect(add).toBeDisabled();
    expect(screen.getByText("Choose at least one event")).toBeVisible();
    fireEvent.click(screen.getByRole("checkbox", { name: /Exception opened/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Payment approval given/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Payment approval given/ })); // toggled off again
    expect(add).toBeEnabled();
    fireEvent.click(add);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/org/webhooks", { url: "https://hooks.example.org/in", events: ["exception.opened"], description: null }));
    expect(await screen.findByTestId("one-time-secret")).toHaveTextContent("ifk_SECRET_SHOWN_ONCE");
    fireEvent.click(screen.getByRole("button", { name: "I have stored it" }));
    expect(screen.queryByTestId("one-time-secret")).toBeNull();
  });

  it("sends a test delivery and opens the delivery log", async () => {
    show(<WebhooksPanel />);
    const row = screen.getByText("https://erp.example.com/hooks/invoiceflow").closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Send test" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/org/webhooks/w1/test"));
    expect(await screen.findByText("Delivery log")).toBeVisible();
  });

  it("shows each delivery's result, attempts, error and next attempt", () => {
    show(<WebhooksPanel />);
    const row = screen.getByText("https://erp.example.com/hooks/invoiceflow").closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Deliveries" }));
    const log = screen.getByText("Delivery log").closest("div")!.parentElement!;
    const delivered = within(log).getByText("Delivered").closest("tr")!;
    expect(within(delivered).getByText("HTTP 200")).toBeVisible();
    const retrying = within(log).getByText("Retrying").closest("tr")!;
    expect(within(retrying).getByText("HTTP 503")).toBeVisible();
    expect(within(retrying).getByText("The receiver answered with HTTP 503")).toBeVisible();
    expect(within(retrying).getByText(/Next attempt/)).toBeVisible();
    expect(within(retrying).getByText("2")).toBeVisible();
    const failed = within(log).getByText("Failed").closest("tr")!;
    expect(within(failed).getByText("The URL points to a private or internal address")).toBeVisible();
    expect(within(failed).getByText("Test delivery")).toBeVisible();
    fireEvent.click(within(row).getByRole("button", { name: "Hide deliveries" }));
    expect(screen.queryByText("Delivery log")).toBeNull();
  });

  it("switches an endpoint off and on", async () => {
    show(<WebhooksPanel />);
    fireEvent.click(within(screen.getByText("https://erp.example.com/hooks/invoiceflow").closest("li")!).getByRole("button", { name: "Switch off" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("/api/org/webhooks/w1", { active: false }));
    fireEvent.click(within(screen.getByText("https://paused.example.com/in").closest("li")!).getByRole("button", { name: "Switch on" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("/api/org/webhooks/w2", { active: true }));
  });

  it("asks before rotating the secret and shows the new one once", async () => {
    show(<WebhooksPanel />);
    const row = screen.getByText("https://erp.example.com/hooks/invoiceflow").closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Rotate secret" }));
    expect(post).not.toHaveBeenCalled();
    const confirm = within(row).getByRole("alert");
    fireEvent.click(within(confirm).getByRole("button", { name: "Rotate secret" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/org/webhooks/w1/rotate-secret"));
    expect(await screen.findByText("Signing secret replaced")).toBeVisible();
  });

  it("asks before deleting a webhook", async () => {
    show(<WebhooksPanel />);
    const row = screen.getByText("https://erp.example.com/hooks/invoiceflow").closest("li")!;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    expect(del).not.toHaveBeenCalled();
    fireEvent.click(within(within(row).getByRole("alert")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/api/org/webhooks/w1"));
  });

  it("is translated to Hebrew", () => {
    show(<WebhooksPanel />, "he");
    expect(screen.getAllByRole("button", { name: "שליחת בדיקה" })).toHaveLength(2);
    expect(screen.getAllByText(/חשבונית אושרה/).length).toBeGreaterThan(0);
  });
});

describe("integration strings", () => {
  it("Hebrew and English define the same keys, including the event names", () => {
    const en = dictionaries.en.integrations, he = dictionaries.he.integrations;
    expect(Object.keys(he).sort()).toEqual(Object.keys(en).sort());
    expect(Object.keys(he.eventNames).sort()).toEqual(Object.keys(en.eventNames).sort());
    expect(Object.keys(en.eventNames)).toEqual(expect.arrayContaining(["invoice.approved", "payment.approved", "exception.opened"]));
    expect(he.apiKeysTitle).toMatch(/[֐-׿]/);
    expect(dictionaries.he.settings.navIntegrations).toBeTruthy();
  });
});
