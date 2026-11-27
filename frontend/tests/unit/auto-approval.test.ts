import { describe, expect, it } from "vitest";
import { formFromPolicy, hoursText, percent, policyIssue, sameForm, toPayload, type Policy, type PolicyForm } from "@/lib/auto-approval";

const policy = (over: Partial<Policy> = {}): Policy => ({
  enabled: true, max_amount: "5000.00", supplier_scope: "all", supplier_ids: [], version: 2, updated_at: null, updated_by: null, ...over,
});
const form = (over: Partial<PolicyForm> = {}): PolicyForm => ({ enabled: true, maxAmount: "5000", scope: "all", supplierIds: [], ...over });

describe("auto-approval policy form", () => {
  it("reads the API policy into the form", () => {
    expect(formFromPolicy(policy({ supplier_scope: "selected", supplier_ids: ["b", "a"] })))
      .toEqual({ enabled: true, maxAmount: "5000.00", scope: "selected", supplierIds: ["a", "b"] });
  });

  it("accepts whole and two-decimal amounts only", () => {
    for (const ok of ["0", "5000", "5000.5", "5000.50", " 12 "]) expect(policyIssue(form({ maxAmount: ok }))).toBeNull();
    for (const bad of ["", "abc", "-1", "1.005", "1,000", "1e3", "5000."]) expect(policyIssue(form({ maxAmount: bad }))).toBe("amount");
  });

  it("will not turn on a policy that names no supplier", () => {
    expect(policyIssue(form({ scope: "selected", supplierIds: [] }))).toBe("noSuppliers");
    expect(policyIssue(form({ scope: "selected", supplierIds: ["a"] }))).toBeNull();
    // switched off, an empty selection is harmless and can be saved
    expect(policyIssue(form({ enabled: false, scope: "selected", supplierIds: [] }))).toBeNull();
  });

  it("sends the amount trimmed and the supplier list only when suppliers are selected", () => {
    expect(toPayload(form({ maxAmount: " 750.5 ", supplierIds: ["a"] }))).toEqual({ enabled: true, max_amount: "750.5", supplier_scope: "all", supplier_ids: [] });
    expect(toPayload(form({ scope: "selected", supplierIds: ["a", "b"] }))).toMatchObject({ supplier_scope: "selected", supplier_ids: ["a", "b"] });
  });

  it("treats 5000 and 5000.00 as the same amount, and ignores suppliers when all are allowed", () => {
    expect(sameForm(form({ maxAmount: "5000" }), form({ maxAmount: "5000.00" }))).toBe(true);
    expect(sameForm(form({ maxAmount: "5001" }), form({ maxAmount: "5000.00" }))).toBe(false);
    expect(sameForm(form({ supplierIds: ["a"] }), form({ supplierIds: [] }))).toBe(true);
    expect(sameForm(form({ scope: "selected", supplierIds: ["b", "a"] }), form({ scope: "selected", supplierIds: ["a", "b"] }))).toBe(true);
    expect(sameForm(form({ scope: "selected", supplierIds: ["a"] }), form({ scope: "selected", supplierIds: ["a", "b"] }))).toBe(false);
    expect(sameForm(form({ enabled: false }), form())).toBe(false);
  });
});

describe("touchless KPI formatting", () => {
  it("formats the rate as a percentage, and nothing before any invoice", () => {
    expect(percent(0.5, "en")).toBe("50%");
    expect(percent(0.333, "en")).toBe("33%");
    expect(percent(1, "en")).toBe("100%");
    expect(percent(null, "en")).toBeNull();
    expect(percent(0.5, "he")).toMatch(/50/);
  });
  it("formats hours to one decimal", () => {
    expect(hoursText(0.1, "en")).toBe("0.1");
    expect(hoursText(12.34, "en")).toBe("12.3");
    expect(hoursText(2, "en")).toBe("2");
  });
});
