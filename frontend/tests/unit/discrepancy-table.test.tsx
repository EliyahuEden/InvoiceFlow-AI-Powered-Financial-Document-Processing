import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DiscrepancyTable } from "@/components/discrepancy-table";
import { I18nProvider } from "@/lib/i18n";
import type { InvoiceDetail } from "@/lib/types";

afterEach(cleanup);
it("opens the document evidence for a discrepant invoice line", () => {
  const select = vi.fn();
  const invoice = {
    currency: "ILS", purchase_order: null,
    lines: [{ id: "line-1", description: "Desk chairs", source: { page: 2, bbox: [0, 0, 1, 1] } }],
    discrepancies: [{ id: "finding-1", type: "PRICE_MISMATCH", status: "open", severity: "critical",
      invoice_line_id: "line-1", expected: "100", actual: "120", difference: "20", message: "Price differs", evidence: {} }],
  } as InvoiceDetail;
  render(<I18nProvider initial="en"><DiscrepancyTable invoice={invoice} onSelectLine={select} /></I18nProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Desk chairs" }));
  expect(select).toHaveBeenCalledWith("line-1");
  expect(screen.getByText("₪100.00")).toBeVisible();
});

it("preserves fractional unit-price evidence instead of truncating it to cents", () => {
  const invoice = {
    currency: "ILS", purchase_order: null, lines: [],
    discrepancies: [{ id: "fractional", type: "PRICE_MISMATCH", status: "open", severity: "warning",
      expected: "0.0400", actual: "0.0999", difference: "0.0599", message: "Unit price differs", evidence: {} }],
  } as unknown as InvoiceDetail;
  render(<I18nProvider initial="en"><DiscrepancyTable invoice={invoice} /></I18nProvider>);
  expect(screen.getByText("₪0.0999")).toBeVisible();
  expect(screen.getByText("₪0.0599")).toBeVisible();
  expect(screen.getByText("₪0.04")).toBeVisible();
});
