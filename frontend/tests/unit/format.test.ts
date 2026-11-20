import { describe, expect, it } from "vitest";
import { money, num } from "@/lib/format";

describe("money formatting (string decimals, no float math)", () => {
  it("groups thousands and pads cents", () => {
    expect(money("7633.42", "ILS")).toBe("₪7,633.42");
    expect(money("1234567.5", "USD")).toBe("$1,234,567.50");
    expect(money("0.1")).toBe("0.10");
  });
  it("keeps precision that floats would lose", () => {
    expect(money("90071992547409.99", "ILS")).toBe("₪90,071,992,547,409.99");
  });
  it("handles negatives and empty values", () => {
    expect(money("-12.5", "EUR")).toBe("−€12.50");
    expect(money(null)).toBe("—");
  });
  it("formats quantities without trailing zeros", () => {
    expect(num("60.000")).toBe("60");
    expect(num("2.500")).toBe("2.5");
    expect(num("1500")).toBe("1,500");
  });
});
