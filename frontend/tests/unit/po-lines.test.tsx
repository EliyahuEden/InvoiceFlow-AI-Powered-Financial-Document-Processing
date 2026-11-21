import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { PurchaseOrderLines } from "@/components/po-lines";
import { I18nProvider } from "@/lib/i18n";

describe("purchase order delivery comparison", () => {
  afterEach(cleanup);
  const line = { id: "line", line_no: 1, sku: "TEST", description: "Synthetic goods", quantity: "10", received: "6", invoiced: "8", unit_price: "29.50", line_total: "295.00" };
  it("distinguishes ordered, received, invoiced and open delivery, and values the missing billed goods", () => {
    render(<I18nProvider initial="en"><PurchaseOrderLines lines={[line]} currency="ILS" /></I18nProvider>);
    for (const heading of ["Ordered", "Received", "Invoiced", "Open delivery"]) {
      expect(screen.getByRole("columnheader", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText(/2 not received/)).toBeInTheDocument();
    expect(screen.getByText(/₪59.00/)).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
  it("does not label an uninvoiced partial delivery as a billed shortfall", () => {
    render(<I18nProvider initial="en"><PurchaseOrderLines lines={[{ ...line, invoiced: "0" }]} currency="ILS" /></I18nProvider>);
    expect(screen.queryByText(/not received/)).not.toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
  it("links each line to its recorded receipts and retains fractional unit prices", () => {
    const receipt = { id: "receipt-a", gr_number: "GR-A", received_date: "2026-03-01", received_by: null,
      lines: [{ po_line_id: line.id, quantity_received: "6" }] };
    const other = { ...receipt, id: "receipt-b", gr_number: "GR-B", lines: [{ po_line_id: "other", quantity_received: "4" }] };
    render(<I18nProvider initial="en"><PurchaseOrderLines lines={[{ ...line, unit_price: "0.4375" }]}
      receipts={[receipt, other]} currency="ILS" /></I18nProvider>);
    expect(screen.getByRole("link", { name: "GR-A" })).toHaveAttribute("href", "#receipt-receipt-a");
    expect(screen.queryByRole("link", { name: "GR-B" })).not.toBeInTheDocument();
    expect(screen.getByText("₪0.4375")).toBeVisible();
  });
});
