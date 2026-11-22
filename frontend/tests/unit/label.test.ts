import { describe, expect, it } from "vitest";
import { label } from "@/lib/i18n/label";
import { dictionaries } from "@/lib/i18n/dictionaries";

describe("label: a translated name for a value the backend sends", () => {
  it("returns the translation for a known key", () => {
    expect(label(dictionaries.he.status, "approved")).toBe(dictionaries.he.status.approved);
    expect(label(dictionaries.en.roles, "finance_reviewer")).toBe("Finance reviewer");
  });
  it("never renders blank for a value the dictionary does not know yet", () => {
    expect(label(dictionaries.en.status, "awaiting_bank_transfer")).toBe("awaiting bank transfer");
    expect(label(dictionaries.en.status, "awaiting_bank_transfer", "Other")).toBe("Other");
  });
  it("uses the given fallback when there is no value at all", () => {
    expect(label(dictionaries.en.finding, "", "Price differs from the PO")).toBe("Price differs from the PO");
  });
  it("shows a dash for a missing value", () => {
    expect(label(dictionaries.en.status, null)).toBe("—");
    expect(label(dictionaries.en.status, undefined)).toBe("—");
  });
  it("does not treat inherited object keys as translations", () => {
    expect(label(dictionaries.en.status, "toString")).toBe("toString");
  });
});
