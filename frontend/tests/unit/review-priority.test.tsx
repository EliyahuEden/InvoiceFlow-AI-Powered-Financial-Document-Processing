import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriorityBadge } from "@/components/domain";
import { I18nProvider } from "@/lib/i18n";
import { dictionaries } from "@/lib/i18n/dictionaries";
import { priorityReasonText, markReviewed, reviewedIds } from "@/lib/review";

const reasons = ["blocking", "amount_at_risk", "unconfirmed_delivery", "suspicious_content", "overdue", "due_soon", "escalated", "review_needed"];
describe("review priority presentation", () => {
  it("explains every backend reason in both languages without raw placeholders", () => {
    for (const locale of ["he", "en"] as const) for (const code of reasons) {
      const text = priorityReasonText(dictionaries[locale], { code, params: { finding: "DUPLICATE_INVOICE", amount: "123.00", days: 2 } }, "ILS");
      expect(text).not.toMatch(/[{}]|DUPLICATE_INVOICE/);
      expect(text).not.toBe(code);
      expect(text.length).toBeGreaterThan(3);
    }
  });
  it("labels priority and reserves red for critical", () => {
    render(<I18nProvider initial="en"><PriorityBadge level="critical" /><PriorityBadge level="high" /><PriorityBadge level="normal" /></I18nProvider>);
    expect(screen.getByText("Critical")).toHaveClass("text-danger");
    expect(screen.getByText("High")).toHaveClass("text-warn");
    expect(screen.getByText("Normal")).toHaveClass("text-info");
  });
  it("remembers a reviewed item once within this session", () => {
    sessionStorage.clear();
    markReviewed("case-1"); markReviewed("case-1"); markReviewed("case-2");
    expect(reviewedIds()).toEqual(["case-1", "case-2"]);
  });
});
