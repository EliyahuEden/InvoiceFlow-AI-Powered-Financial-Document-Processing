import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/shell";
import { I18nProvider } from "@/lib/i18n";
import { at } from "../support/at";

const push = vi.fn();
const get = vi.fn(async (path: string) => {
  if (path.startsWith("/api/invoices")) return { items: [{ id: "inv-1", invoice_number: "BW-2026-0412", supplier_name: "BlueWave IT", status: "exception" }] };
  if (path.startsWith("/api/suppliers")) return { items: [{ id: "sup-1", name: "BlueWave IT Solutions Ltd" }] };
  if (path.startsWith("/api/purchase-orders")) return { items: [] };
  return {};
});
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ push }) }));
vi.mock("@/lib/events", () => ({ useLiveEvents: () => undefined }));
vi.mock("@/lib/api", () => ({ api: { post: vi.fn(), get: (p: string) => get(p) }, useApi: () => ({}) }));
vi.mock("@/components/session", () => ({
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
  useSession: () => ({
    me: { user: { id: "u", full_name: "Demo Reviewer" }, organization: { id: "o", name: "Demo Org" }, role: "finance_reviewer",
      permissions: ["exception:decide"], ai_mode: "offline" },
    can: () => true,
  }),
}));
afterEach(() => { cleanup(); push.mockClear(); get.mockClear(); });

const shell = () => render(<I18nProvider initial="en"><AppShell><h1>Page</h1></AppShell></I18nProvider>);

describe("command palette", () => {
  it("opens with Ctrl+K and lists destinations", async () => {
    shell();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: "Command palette" });
    expect(within(dialog).getByText("Suppliers")).toBeVisible();
    expect(within(dialog).getByText("Review next priority")).toBeVisible();
  });

  it("opens from the top-bar search button", async () => {
    shell();
    fireEvent.click(at(screen.getAllByRole("button", { name: /Search or jump to/ }), 0));
    expect(await screen.findByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
  });

  it("searches invoices and suppliers through the real list APIs and navigates", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    shell();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.change(await screen.findByRole("combobox"), { target: { value: "BlueWave" } });
    await act(async () => { vi.advanceTimersByTime(400); });
    await waitFor(() => expect(screen.getByText("BW-2026-0412")).toBeVisible());
    expect(get).toHaveBeenCalledWith(expect.stringContaining("/api/invoices?q=BlueWave"));
    fireEvent.click(screen.getByText("BW-2026-0412"));
    expect(push).toHaveBeenCalledWith("/invoices/inv-1");
    vi.useRealTimers();
  });
});

describe("keyboard shortcuts", () => {
  it("? opens the shortcuts overlay, but not while typing", async () => {
    shell();
    fireEvent.keyDown(window, { key: "?" });
    expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  });

  it("g then q goes to the priority queue", async () => {
    shell();
    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "q" });
    expect(push).toHaveBeenCalledWith("/exceptions");
  });
});
