import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/shell";
import { I18nProvider } from "@/lib/i18n";
import { at } from "../support/at";

const state = vi.hoisted(() => ({ role: "read_only" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/invoices", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/events", () => ({ useLiveEvents: () => undefined }));
vi.mock("@/lib/api", () => ({ api: { post: vi.fn(), get: vi.fn() }, useApi: () => ({}) }));
vi.mock("@/components/session", () => ({
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
  useSession: () => ({
    me: { user: { id: "reviewer", full_name: "Demo Reviewer" }, organization: { id: "demo", name: "Demo Org" },
      role: state.role, permissions: state.role === "read_only" ? [] : ["exception:decide"], ai_mode: "offline" },
    can: (permission: string) => state.role !== "read_only" || !["invoice:upload", "audit:read"].includes(permission),
  }),
}));
afterEach(() => { cleanup(); state.role = "read_only"; });

describe("command center navigation", () => {
  it("opens every permitted destination in a labelled drawer and supports Escape", () => {
    render(<I18nProvider initial="en"><AppShell><h1>Invoices</h1></AppShell></I18nProvider>);
    fireEvent.click(at(screen.getAllByRole("button", { name: "All destinations" }), 0));
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByRole("link", { name: "Agreements & knowledge" })).toBeVisible();
    expect(within(drawer).getByRole("link", { name: "Organization settings" })).toBeVisible();
    expect(within(drawer).queryByRole("link", { name: "Upload" })).not.toBeInTheDocument();
    fireEvent.keyDown(drawer, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("retains upload and audit navigation for a permitted reviewer", () => {
    state.role = "finance_reviewer";
    render(<I18nProvider initial="en"><AppShell><h1>Invoices</h1></AppShell></I18nProvider>);
    fireEvent.click(at(screen.getAllByRole("button", { name: "All destinations" }), 0));
    expect(within(screen.getByRole("dialog")).getByRole("link", { name: "Upload" })).toBeVisible();
    expect(within(screen.getByRole("dialog")).getByRole("link", { name: "Audit trail" })).toBeVisible();
  });
});
