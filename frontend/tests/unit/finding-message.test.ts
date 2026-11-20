import { describe, expect, it } from "vitest";
import { dictionaries } from "@/lib/i18n/dictionaries";
import { findingMessage } from "@/lib/findings";

const price = {
  type: "PRICE_MISMATCH",
  message: "Line 1: unit price 124.00 vs 118.00 on PO-1 (+5.08%), tolerance 1.0% / 0.05.",
  message_key: "PRICE_MISMATCH",
  params: { line: 1, invoice_price: "124.00", po_price: "118.00", po: "PO-1", pct: "+5.08", tolerance_pct: "1.0", tolerance_abs: "0.05" },
};

describe("findingMessage (deterministic engine messages, localized by key)", () => {
  it("renders the Hebrew template with the engine's parameters", () => {
    const s = findingMessage(dictionaries.he, price);
    expect(s).toMatch(/[֐-׿]/);
    expect(s).toContain("124.00");
    expect(s).toContain("118.00");
    expect(s).toContain("PO-1");
    expect(s).not.toContain("{");
  });

  it("renders the English template too", () => {
    expect(findingMessage(dictionaries.en, price)).toBe(price.message);
  });

  it("reads key and params from a stored discrepancy's evidence", () => {
    const d = { type: "PO_CLOSED", message: "PO-7 is closed.", evidence: { message_key: "PO_CLOSED", params: { po: "PO-7", status: "closed" } } };
    const s = findingMessage(dictionaries.he, d);
    expect(s).toContain("PO-7");
    expect(s).toContain(dictionaries.he.status.closed); // status values are localized too
  });

  it("localizes missing values instead of printing null", () => {
    const d = { type: "UNRECOGNIZED_SUPPLIER", message: "x", message_key: "UNRECOGNIZED_SUPPLIER", params: { name: null, tax_id: null } };
    const s = findingMessage(dictionaries.en, d);
    expect(s).not.toContain("null");
    expect(s).toContain(dictionaries.en.common.notPrinted);
  });

  it("falls back to the stored English message for results without params", () => {
    expect(findingMessage(dictionaries.he, { type: "PRICE_MISMATCH", message: "legacy text" })).toBe("legacy text");
  });

  it("falls back when a parameter is missing rather than showing a placeholder", () => {
    const d = { ...price, params: { line: 1 } };
    expect(findingMessage(dictionaries.he, d)).toBe(price.message);
  });
});
