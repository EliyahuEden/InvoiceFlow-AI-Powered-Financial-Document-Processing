import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ReviewPage from "@/app/(app)/invoices/[id]/review/page";
import { I18nProvider } from "@/lib/i18n";
import { api } from "@/lib/api";

const invoice = { id: "inv-1", status: "needs_review", invoice_number: "INV-42", supplier_id: null,
  lines: [], field_sources: {}, missing_fields: [] };
vi.mock("@/lib/use-invoice", () => ({ useInvoice: () => ({ data: invoice, mutate: vi.fn() }) }));
vi.mock("@/components/session", () => ({ useSession: () => ({ can: () => true }) }));
vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()),
  useApi: () => ({ data: { items: [] } }),
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function show() {
  return render(<I18nProvider initial="en"><button data-testid="review-next">Next</button><ReviewPage /></I18nProvider>);
}
describe("extraction corrections protect unsaved work", () => {
  it("guards navigation after editing an extracted field", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { container } = show();
    fireEvent.change(container.querySelector("#f-invoice_number")!, { target: { value: "INV-43" } });
    expect(fireEvent.click(screen.getByRole("button", { name: "Next" }))).toBe(false);
    expect(window.confirm).toHaveBeenCalled();
  });
  it("guards a typed correction reason even when fields are unchanged", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { container } = show();
    fireEvent.change(container.querySelector("#reason")!, { target: { value: "Checking supplier" } });
    expect(fireEvent.click(screen.getByRole("button", { name: "Next" }))).toBe(false);
    expect(window.confirm).toHaveBeenCalled();
  });
  it("clears the guard after a saved reason and protects later edits again", async () => {
    vi.spyOn(api, "patch").mockResolvedValue({});
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { container } = show();
    const reason = container.querySelector("#reason")!;
    fireEvent.change(reason, { target: { value: "Confirmed with supplier" } });
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    await waitFor(() => expect(reason).toHaveValue(""));
    expect(fireEvent.click(screen.getByRole("button", { name: "Next" }))).toBe(true);
    expect(window.confirm).not.toHaveBeenCalled();
    fireEvent.change(reason, { target: { value: "Another unsaved check" } });
    expect(fireEvent.click(screen.getByRole("button", { name: "Next" }))).toBe(false);
  });
});
