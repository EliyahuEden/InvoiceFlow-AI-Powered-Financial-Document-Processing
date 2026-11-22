import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionsPanel } from "@/components/sessions-panel";
import { I18nProvider } from "@/lib/i18n";

const del = vi.fn(async (_path: string) => ({ ok: true }));
const mutate = vi.fn();
const items = [
  { id: "s1", current: true, created_at: "2026-11-21T08:00:00Z", last_used_at: "2026-11-21T12:00:00Z",
    expires_at: "2026-11-21T20:00:00Z", ip: "10.0.0.5",
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36" },
  { id: "s2", current: false, created_at: "2026-11-20T08:00:00Z", last_used_at: "2026-11-20T09:00:00Z",
    expires_at: "2026-11-21T17:00:00Z", ip: "172.16.0.9",
    user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5; rv:132.0) Gecko/20100101 Firefox/132.0" },
];
vi.mock("@/lib/api", () => ({
  api: { del: (p: string) => del(p) },
  useApi: () => ({ data: { items }, mutate }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
afterEach(() => { cleanup(); del.mockClear(); mutate.mockClear(); });

const show = (locale: "en" | "he" = "en") => render(<I18nProvider initial={locale}><SessionsPanel /></I18nProvider>);

describe("signed-in sessions", () => {
  it("lists sessions by browser and system, marking this device", () => {
    show();
    const current = screen.getByText("Chrome on Windows").closest("li")!;
    expect(within(current).getByText("This device")).toBeVisible();
    expect(within(current).queryByRole("button")).toBeNull();
    expect(screen.getByText("Firefox on macOS")).toBeVisible();
    expect(screen.getByText(/172\.16\.0\.9/)).toBeVisible();
  });

  it("signs out another session and refreshes the list", async () => {
    show();
    const other = screen.getByText("Firefox on macOS").closest("li")!;
    fireEvent.click(within(other).getByRole("button", { name: /Sign out/ }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/api/auth/sessions/s2"));
    expect(mutate).toHaveBeenCalled();
  });

  it("is translated to Hebrew", () => {
    show("he");
    expect(screen.getByText("מכשירים מחוברים")).toBeVisible();
    expect(screen.getByText("המכשיר הזה")).toBeVisible();
  });
});
