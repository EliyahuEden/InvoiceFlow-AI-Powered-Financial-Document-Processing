import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewQueue } from "@/components/review-queue";
import { I18nProvider } from "@/lib/i18n";
import type { ReviewQueueItem } from "@/lib/types";

// queue rows open cases through TransitionLink, which uses the app router
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

const item = (over: Partial<ReviewQueueItem>): ReviewQueueItem => ({
  exception_id: "e1", invoice_id: "i1", invoice_number: "FX-1", supplier_id: null, supplier_name: "Arava", supplier_name_en: null,
  total: "10000.00", currency: "USD", amount_at_risk: "2000.00", due_date: null, due_in_days: null, status: "open",
  finding_types: ["PRICE_MISMATCH"], proposed_action: null, has_ai_summary: false, escalated_by: null, created_at: "2026-11-01T00:00:00Z",
  priority: { level: "critical", reasons: [], rank: 1 }, ...over,
} as ReviewQueueItem);

describe("money at risk across currencies", () => {
  afterEach(cleanup);
  it("shows the shekel equivalent and the rate date next to a foreign amount", () => {
    render(<I18nProvider initial="en"><ReviewQueue compact items={[item({ amount_at_risk_base: "6660.00", fx_as_of: "2026-11-20" })]} /></I18nProvider>);
    const amount = screen.getByText(/≈/);
    expect(amount.textContent).toMatch(/2,000\.00/);
    expect(amount.textContent).toMatch(/6,660\.00/);
    expect(amount.getAttribute("title")).toMatch(/2026-11-20|20/);
  });
  it("shows shekel amounts as they are", () => {
    render(<I18nProvider initial="en"><ReviewQueue compact items={[item({ currency: "ILS", amount_at_risk: "3000.00", amount_at_risk_base: null })]} /></I18nProvider>);
    expect(screen.queryByText(/≈/)).toBeNull();
  });
});
