import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AtRisk, DueCell } from "@/components/review-queue";
import { I18nProvider } from "@/lib/i18n";
import { dictionaries } from "@/lib/i18n/dictionaries";
import { dueRelative } from "@/lib/review";
import type { ReviewQueueItem } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

const item = (over: Partial<ReviewQueueItem>): ReviewQueueItem => ({
  exception_id: "e1", invoice_id: "i1", invoice_number: "TV-1", supplier_id: null, supplier_name: "Tavor", supplier_name_en: null,
  total: "100.00", currency: "ILS", amount_at_risk: "100.00", due_date: null, due_in_days: null, status: "open",
  finding_types: [], proposed_action: null, has_ai_summary: false, escalated_by: null, created_at: "2026-11-01T00:00:00Z",
  priority: { level: "high", reasons: [], rank: 1 }, ...over,
} as ReviewQueueItem);

describe("due dates in words", () => {
  const t = dictionaries.en;
  it("says how late or how soon, and how loudly", () => {
    expect(dueRelative(t, null)).toBeNull();
    expect(dueRelative(t, -3)).toEqual({ text: "3 days overdue", tone: "danger" });
    expect(dueRelative(t, -1)).toEqual({ text: "1 day overdue", tone: "danger" });
    expect(dueRelative(t, 0)).toEqual({ text: "Due today", tone: "warn" });
    expect(dueRelative(t, 1)).toEqual({ text: "Due tomorrow", tone: "warn" });
    expect(dueRelative(t, 3)?.tone).toBe("warn");
    expect(dueRelative(t, 9)).toEqual({ text: "Due in 9 days", tone: "quiet" });
  });
  it("Hebrew has its own wording", () => {
    expect(dueRelative(dictionaries.he, -2)?.text).toBe("באיחור של 2 ימים");
  });
});

describe("queue cells", () => {
  afterEach(cleanup);
  it("says when an invoice states no due date", () => {
    render(<I18nProvider initial="en"><DueCell item={item({})} /></I18nProvider>);
    expect(screen.getByText("Not stated")).toBeTruthy();
  });
  it("shows the due date with how late it is", () => {
    render(<I18nProvider initial="en"><DueCell item={item({ due_date: "2026-11-20", due_in_days: -5 })} /></I18nProvider>);
    expect(screen.getByText("5 days overdue")).toBeTruthy();
  });
  it("never invents a currency the invoice did not state", () => {
    render(<I18nProvider initial="en"><AtRisk item={item({ currency: null, amount_at_risk: "7633.42" })} /></I18nProvider>);
    expect(screen.getByText("7,633.42")).toBeTruthy();
    expect(screen.getByText("Currency not stated")).toBeTruthy();
  });
});
