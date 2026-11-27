import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AutoApprovalPanel } from "@/components/auto-approval-panel";
import { AutomationKpiCard } from "@/components/automation-kpi";
import { I18nProvider } from "@/lib/i18n";
import type { PolicyView } from "@/lib/auto-approval";

const put = vi.fn(async (_path: string, _body: unknown) => ({}));
const mutate = vi.fn(async () => undefined);
let view: PolicyView;
const suppliers = { total: 2, items: [{ id: "s1", name: "Tavor", name_en: "Tavor Foods" }, { id: "s2", name: "Hermon", name_en: null }] };

vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  api: { put: (p: string, b: unknown) => put(p, b) },
  useApi: (path: string) => ({ data: path.startsWith("/api/suppliers") ? suppliers : view, mutate }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...p }: { href: string; children: React.ReactNode }) => <a href={href} {...p}>{children}</a> }));

const baseView = (policy: Partial<PolicyView["policy"]> = {}): PolicyView => ({
  policy: { enabled: false, max_amount: "0.00", supplier_scope: "selected", supplier_ids: [], version: 0, updated_at: null, updated_by: null, ...policy },
  minutes_per_invoice: 6, window_days: 30,
  fixed_rules: ["three_way_match", "zero_findings", "no_human_edit", "no_payment_hold_or_bank_change"],
});
const show = (admin = true, locale: "en" | "he" = "en") =>
  render(<I18nProvider initial={locale}><AutoApprovalPanel admin={admin} currency="ILS" /></I18nProvider>);
const save = () => screen.getByRole("button", { name: /Save policy|שמירת המדיניות/ });

beforeEach(() => { view = baseView(); });
afterEach(() => { cleanup(); put.mockClear(); mutate.mockClear(); });

describe("auto-approval settings panel", () => {
  it("states the rules that can never be switched off and that payment approval is unchanged", () => {
    show();
    expect(screen.getByText(/Always required, never configurable/)).toBeVisible();
    expect(screen.getByText(/complete three-way match/)).toBeVisible();
    expect(screen.getByText(/Zero findings/)).toBeVisible();
    expect(screen.getByText(/No payment hold and no bank change/)).toBeVisible();
    expect(screen.getByText(/Payment approval is unchanged/)).toBeVisible();
    expect(screen.getByText("Not set yet")).toBeVisible();
  });

  it("starts switched off with nothing to save", () => {
    show();
    expect(screen.getByRole("checkbox", { name: /Turn on auto-approval/ })).not.toBeChecked();
    expect(save()).toBeDisabled();
  });

  it("saves an all-suppliers policy with its ceiling", async () => {
    show();
    fireEvent.click(screen.getByRole("checkbox", { name: /Turn on auto-approval/ }));
    fireEvent.click(screen.getByRole("radio", { name: /All recognised suppliers/ }));
    fireEvent.change(screen.getByLabelText("Largest invoice total"), { target: { value: "7500.50" } });
    fireEvent.click(save());
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/org/auto-approval",
      { enabled: true, max_amount: "7500.50", supplier_scope: "all", supplier_ids: [] }));
    expect(mutate).toHaveBeenCalled();
  });

  it("will not save a selected-suppliers policy until a supplier is chosen", async () => {
    show();
    fireEvent.click(screen.getByRole("checkbox", { name: /Turn on auto-approval/ }));
    fireEvent.change(screen.getByLabelText("Largest invoice total"), { target: { value: "1000" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/Choose at least one supplier/);
    expect(save()).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Tavor Foods" }));  // English name in English
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "Hermon" }));
    fireEvent.click(save());
    await waitFor(() => expect(put).toHaveBeenCalledWith("/api/org/auto-approval",
      { enabled: true, max_amount: "1000", supplier_scope: "selected", supplier_ids: ["s1", "s2"] }));
  });

  it("rejects an amount that is not money before anything is sent", () => {
    show();
    fireEvent.click(screen.getByRole("checkbox", { name: /Turn on auto-approval/ }));
    fireEvent.click(screen.getByRole("radio", { name: /All recognised suppliers/ }));
    fireEvent.change(screen.getByLabelText("Largest invoice total"), { target: { value: "ten thousand" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/Enter an amount such as 5000/);
    expect(screen.getByLabelText("Largest invoice total")).toHaveAttribute("aria-invalid", "true");
    expect(save()).toBeDisabled();
    expect(put).not.toHaveBeenCalled();
  });

  it("shows the saved policy and its version", () => {
    view = baseView({ enabled: true, max_amount: "12000.00", supplier_scope: "selected", supplier_ids: ["s2"], version: 4 });
    show();
    expect(screen.getByText("Policy version 4")).toBeVisible();
    expect(screen.getByLabelText("Largest invoice total")).toHaveValue("12000.00");
    expect(screen.getByRole("checkbox", { name: "Hermon" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Tavor Foods" })).not.toBeChecked();
    expect(save()).toBeDisabled(); // unchanged
  });

  it("is read-only for people who cannot manage the organization", () => {
    view = baseView({ enabled: true, max_amount: "12000.00", supplier_scope: "all", version: 1 });
    show(false);
    expect(screen.getByRole("checkbox", { name: /Turn on auto-approval/ })).toBeDisabled();
    expect(screen.getByLabelText("Largest invoice total")).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Only the suppliers I choose/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Save policy/ })).toBeNull();
  });

  it("renders in Hebrew", () => {
    show(true, "he");
    expect(screen.getByRole("checkbox", { name: /הפעלת אישור אוטומטי/ })).toBeVisible();
    expect(screen.getByText(/תמיד נדרש/)).toBeVisible();
    expect(screen.getByText(/אפס ממצאים/)).toBeVisible();
  });
});

describe("touchless KPI card", () => {
  const kpi = { touchless_rate: 0.5, auto_approved: 3, processed: 6, hours_saved: 0.3, minutes_per_invoice: 6, window_days: 30 };
  const card = (props: React.ComponentProps<typeof AutomationKpiCard>, locale: "en" | "he" = "en") =>
    render(<I18nProvider initial={locale}><AutomationKpiCard {...props} /></I18nProvider>);

  it("shows the rate, the counts, the hours saved and the assumption behind them", () => {
    card({ kpi, enabled: true });
    expect(screen.getByText("50%")).toBeVisible();
    expect(screen.getByText("3 of 6 invoices, last 30 days")).toBeVisible();
    expect(screen.getByText("About 0.3 hours saved")).toBeVisible();
    expect(screen.getByText(/6 minutes of review assumed for each auto-approved invoice/)).toBeVisible();
    expect(screen.getByTestId("automation-kpi")).toHaveAttribute("href", "/settings#autoApproval");
  });

  it("shows a dash and no savings before anything is auto-approved, and says when the policy is off", () => {
    card({ kpi: { ...kpi, touchless_rate: 0, auto_approved: 0, hours_saved: 0 }, enabled: false });
    expect(screen.getByText("0%")).toBeVisible();
    expect(screen.queryByText(/hours saved/)).toBeNull();
    expect(screen.getByText(/Auto-approval is off\./)).toBeVisible();
  });

  it("shows a dash and an empty note with no invoices at all", () => {
    card({ kpi: { ...kpi, touchless_rate: null, auto_approved: 0, processed: 0, hours_saved: 0 }, enabled: true });
    expect(screen.getByText("—")).toBeVisible();
    expect(screen.getByText("No invoices yet")).toBeVisible();
  });

  it("renders in Hebrew", () => {
    card({ kpi, enabled: true }, "he");
    expect(screen.getByText("שיעור טיפול ללא מגע")).toBeVisible();
    expect(screen.getByText(/חיסכון של כ-0\.3 שעות/)).toBeVisible();
  });
});
