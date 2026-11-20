import { describe, expect, it } from "vitest";
import { dictionaries } from "@/lib/i18n/dictionaries";

function keys(o: unknown, prefix = ""): string[] {
  if (typeof o !== "object" || o === null || Array.isArray(o)) return [prefix];
  return Object.entries(o).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
}

describe("i18n dictionaries", () => {
  it("Hebrew and English define exactly the same keys", () => {
    expect(keys(dictionaries.he).sort()).toEqual(keys(dictionaries.en).sort());
  });
  it("Hebrew strings are actually Hebrew for core navigation", () => {
    expect(dictionaries.he.nav.inbox).toMatch(/[֐-׿]/);
    expect(dictionaries.he.ai.advisory).toMatch(/[֐-׿]/);
  });
  it("every finding type has a label in both languages", () => {
    expect(Object.keys(dictionaries.he.finding)).toEqual(Object.keys(dictionaries.en.finding));
  });
});
