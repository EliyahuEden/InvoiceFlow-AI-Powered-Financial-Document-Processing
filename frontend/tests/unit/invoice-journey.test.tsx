import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import InboxPage from "@/app/(app)/invoices/page";
import UploadPage from "@/app/(app)/invoices/upload/page";
import InvoiceOverview from "@/app/(app)/invoices/[id]/page";
import { I18nProvider } from "@/lib/i18n";
import { api } from "@/lib/api";
import type { InvoiceDetail } from "@/lib/types";

const state = vi.hoisted(() => ({
  permissions: [] as string[],
  invoice: {} as InvoiceDetail,
  request: "",
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/invoices" }));
vi.mock("@/components/session", () => ({
  useSession: () => ({ me: { user: { id: "reviewer" } }, can: (p: string) => state.permissions.includes(p) }),
}));
vi.mock("@/lib/use-invoice", () => ({ useInvoice: () => ({ data: state.invoice, mutate: vi.fn() }) }));
vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()),
  useApi: (path: string) => {
    state.request = path;
    return { data: { items: [], status_counts: {}, total: 0, page: 1, pages: 1 } };
  },
}));
beforeEach(() => {
  state.permissions = [];
  state.invoice = {
    id: "invoice", status: "reconciled", invoice_number: "INV-42",
    approvals: [{ id: "second", step: 2, required_role: "admin", status: "pending" }],
    discrepancies: [], lines: [], validation_warnings: [], field_sources: {}, missing_fields: [],
  } as unknown as InvoiceDetail;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const show = (page: React.ReactNode) => render(<I18nProvider initial="en">{page}</I18nProvider>);

it("sorts the whole inbox through the API when a sortable column is selected", () => {
  show(<InboxPage />);
  const heading = screen.getByRole("columnheader", { name: "Total" });
  fireEvent.click(within(heading).getByRole("button"));
  expect(new URL(state.request, "http://local").searchParams.get("sort")).toMatch(/^-?total$/);
});

it("withholds file intake on a direct visit without upload permission", () => {
  show(<UploadPage />);
  expect(screen.queryByTestId("file-input")).not.toBeInTheDocument();
});

it("shows the worker's reported percentage and error for an uploaded file", async () => {
  state.permissions = ["invoice:upload"];
  vi.spyOn(api, "post").mockResolvedValue({ invoice_id: "invoice", job_id: "job" });
  show(<UploadPage />);
  await act(async () => fireEvent.change(screen.getByTestId("file-input"), { target: { files: [new File(["pdf"], "doc.pdf")] } }));
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  act(() => { window.dispatchEvent(new CustomEvent("if:event", { detail: {
    event: "job.progress", data: { job_id: "job", progress: 37, message: "Reading page 2" },
  } })); });
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "37");
  act(() => { window.dispatchEvent(new CustomEvent("if:event", { detail: {
    event: "job.failed", data: { job_id: "job", error: "Unable to read page 2" },
  } })); });
  expect(screen.getByText("Unable to read page 2")).toBeVisible();
});

it("requires final-approval permission and a different reviewer for a second payment approval", () => {
  state.permissions = ["approval:decide"];
  const view = show(<InvoiceOverview />);
  expect(screen.queryByRole("button", { name: "Approve for payment" })).not.toBeInTheDocument();
  state.permissions.push("approval:final");
  view.rerender(<I18nProvider initial="en"><InvoiceOverview /></I18nProvider>);
  expect(screen.getByRole("button", { name: "Approve for payment" })).toBeEnabled();
  state.invoice.approvals.unshift({ ...state.invoice.approvals[0], id: "first", step: 1, status: "approved", decided_by: "reviewer" });
  view.rerender(<I18nProvider initial="en"><InvoiceOverview /></I18nProvider>);
  expect(screen.queryByRole("button", { name: "Approve for payment" })).not.toBeInTheDocument();
});

it("pairs corrected supplier data with its original source and retains fractional unit prices", () => {
  state.invoice.supplier_name_raw = "Corrected supplier";
  state.invoice.field_sources = { supplier_name: { text: "Original printed supplier", page: 2, bbox: [.1, .2, .4, .3], verified: true },
    supplier_name_raw: { corrected_by: "reviewer" } };
  state.invoice.lines = [{ id: "line", line_no: 1, sku: null, quantity: "1", description: "Part",
    unit_price: "0.4375", discount: null, line_total: "0.44", source: {} }];
  show(<InvoiceOverview />);
  expect(screen.getByText("0.4375")).toBeVisible();
  expect(screen.getByText("Corrected")).toBeVisible();
  expect(screen.getByText("Original printed supplier")).toBeVisible();
  expect(screen.queryByText("Every row verified against the document")).not.toBeInTheDocument();
});
