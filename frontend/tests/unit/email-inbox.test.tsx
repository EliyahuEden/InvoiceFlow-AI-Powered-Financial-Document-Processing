import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmailInboxPanel, EmailSourceBadge, type InboxInfo } from "@/components/email-inbox";
import { I18nProvider } from "@/lib/i18n";

const ADDRESS = "invoices+0123456789abcdef0123@inbox.example.com";
const post = vi.fn(async (_path: string) => ({}));
const mutate = vi.fn(async () => undefined);
let info: InboxInfo | undefined;
let failure: unknown;

vi.mock("@/lib/api", () => ({
  api: { post: (p: string) => post(p) },
  ApiError: class ApiError extends Error {},
  useApi: () => ({ data: info, error: failure, mutate }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const base: InboxInfo = {
  enabled: true, address: ADDRESS, methods: { imap: true, webhook: false }, max_attachment_mb: 20,
  recent: [
    { id: "m1", created_at: "2026-11-20T09:15:00Z", sender: "billing@supplier.example", subject: "October invoice", status: "accepted",
      source: "imap", attachments: 1, accepted: 1, problems: [] },
    { id: "m2", created_at: "2026-11-20T10:00:00Z", sender: "ops@other.example", subject: "Scans", status: "partial",
      source: "webhook", attachments: 3, accepted: 1,
      problems: [{ filename: "broken.pdf", status: "rejected", reason: "The PDF is damaged or not a valid PDF." },
        { filename: "notes.docx", status: "skipped", reason: "Only PDF and image attachments are read." }] },
  ],
};

beforeEach(() => { info = base; failure = undefined; });
afterEach(() => { cleanup(); post.mockClear(); mutate.mockClear(); toast.success.mockClear(); toast.error.mockClear(); });

const show = (ui: React.ReactNode, locale: "en" | "he" = "en") => render(<I18nProvider initial={locale}>{ui}</I18nProvider>);

describe("email source badge", () => {
  it("marks an emailed invoice and says who sent it", () => {
    show(<EmailSourceBadge source="email" sender="billing@supplier.example" subject="October invoice" />);
    const badge = screen.getByTestId("email-source-badge");
    expect(badge).toHaveTextContent("Email");
    expect(badge).toHaveAttribute("title", "Received by email from billing@supplier.example · October invoice");
  });

  it("shows nothing for an uploaded invoice", () => {
    show(<EmailSourceBadge source="upload" />);
    show(<EmailSourceBadge />);
    expect(screen.queryByTestId("email-source-badge")).toBeNull();
  });

  it("is translated to Hebrew", () => {
    show(<EmailSourceBadge source="email" sender="a@b.example" />, "he");
    expect(screen.getByTestId("email-source-badge")).toHaveTextContent("דוא״ל");
    expect(screen.getByTestId("email-source-badge")).toHaveAttribute("title", expect.stringContaining("התקבלה בדוא״ל מאת a@b.example"));
  });
});

describe("email inbox settings", () => {
  it("shows the organization's address, left-to-right, and the file size limit", () => {
    show(<EmailInboxPanel />);
    const address = screen.getByTestId("inbox-address");
    expect(address).toHaveTextContent(ADDRESS);
    expect(address).toHaveAttribute("dir", "ltr");
    expect(screen.getByText(/up to 20 MB each/)).toBeVisible();
  });

  it("copies the address", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    show(<EmailInboxPanel />);
    fireEvent.click(screen.getByRole("button", { name: /Copy/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(ADDRESS));
    expect(toast.success).toHaveBeenCalledWith("Address copied");
  });

  it("asks before replacing the address, and replaces it only on confirmation", async () => {
    show(<EmailInboxPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Create a new address" }));
    expect(post).not.toHaveBeenCalled();
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText(/stops working immediately/)).toBeVisible();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Create a new address" }));
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Yes, create a new address" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/org/inbox/regenerate"));
    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith("A new address was created");
  });

  it("lists recent messages with the files that were not taken and why", () => {
    show(<EmailInboxPanel />);
    const rows = screen.getAllByRole("row");
    const first = rows.find((r) => within(r).queryByText("October invoice"))!;
    expect(within(first).getByText("Received")).toBeVisible();
    expect(within(first).getByText("1 of 1 files taken")).toBeVisible();
    const second = rows.find((r) => within(r).queryByText("Scans"))!;
    expect(within(second).getByText("Partly received")).toBeVisible();
    expect(within(second).getByText(/broken\.pdf/)).toBeVisible();
    expect(within(second).getByText(/The PDF is damaged/)).toBeVisible();
    expect(within(second).getByText(/notes\.docx/)).toBeVisible();
  });

  it("says so when no message has arrived", () => {
    info = { ...base, recent: [] };
    show(<EmailInboxPanel />);
    expect(screen.getByText("No messages have arrived yet.")).toBeVisible();
  });

  it("explains that intake is not set up instead of showing an address", () => {
    info = { ...base, enabled: false, address: null };
    show(<EmailInboxPanel />);
    expect(screen.getByText("Email intake is not set up")).toBeVisible();
    expect(screen.queryByTestId("inbox-address")).toBeNull();
    expect(screen.queryByRole("button", { name: "Create a new address" })).toBeNull();
  });

  it("is translated to Hebrew", () => {
    show(<EmailInboxPanel />, "he");
    expect(screen.getByText("קבלת חשבוניות בדוא״ל")).toBeVisible();
    expect(screen.getByRole("button", { name: "יצירת כתובת חדשה" })).toBeVisible();
    expect(screen.getByText("התקבלה חלקית")).toBeVisible();
  });

  it("offers a retry when the settings cannot be loaded", () => {
    info = undefined;
    failure = new Error("boom");
    show(<EmailInboxPanel />);
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }));
    expect(mutate).toHaveBeenCalled();
  });
});
