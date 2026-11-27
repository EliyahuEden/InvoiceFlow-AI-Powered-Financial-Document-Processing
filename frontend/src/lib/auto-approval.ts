/** Auto-approval policy: the shapes the API uses, and the checks the settings form makes before it saves. The
 *  backend validates again and is the authority; these checks only keep an obviously wrong form from being sent. */

export type Policy = {
  enabled: boolean; max_amount: string; supplier_scope: "all" | "selected"; supplier_ids: string[];
  version: number; updated_at: string | null; updated_by: string | null;
};
export type PolicyView = { policy: Policy; minutes_per_invoice: number; window_days: number; fixed_rules: string[] };
export type PolicyForm = { enabled: boolean; maxAmount: string; scope: "all" | "selected"; supplierIds: string[] };
export type AutomationKpi = {
  touchless_rate: number | null; auto_approved: number; processed: number; hours_saved: number;
  minutes_per_invoice: number; window_days: number;
};

export function formFromPolicy(p: Policy): PolicyForm {
  return { enabled: p.enabled, maxAmount: p.max_amount, scope: p.supplier_scope, supplierIds: [...p.supplier_ids].sort() };
}

/** A whole or two-decimal, non-negative amount (what the API accepts). */
export const AMOUNT = /^\d{1,10}(\.\d{1,2})?$/;

export type PolicyIssue = "amount" | "noSuppliers";

/** Why this form cannot be saved yet, or null. */
export function policyIssue(f: PolicyForm): PolicyIssue | null {
  if (!AMOUNT.test(f.maxAmount.trim())) return "amount";
  if (f.enabled && f.scope === "selected" && f.supplierIds.length === 0) return "noSuppliers";
  return null;
}

export function toPayload(f: PolicyForm) {
  return { enabled: f.enabled, max_amount: f.maxAmount.trim(), supplier_scope: f.scope,
    supplier_ids: f.scope === "selected" ? f.supplierIds : [] };
}

export function sameForm(a: PolicyForm, b: PolicyForm): boolean {
  return a.enabled === b.enabled && Number(a.maxAmount) === Number(b.maxAmount) && a.scope === b.scope
    && (a.scope === "all" || [...a.supplierIds].sort().join() === [...b.supplierIds].sort().join());
}

/** 0.5 -> "50%", 0.333 -> "33%"; null (nothing processed yet) -> null. */
export function percent(rate: number | null, locale: string): string | null {
  return rate === null ? null : new Intl.NumberFormat(locale === "he" ? "he-IL" : "en-GB", { style: "percent", maximumFractionDigits: 0 }).format(rate);
}

export function hoursText(hours: number, locale: string): string {
  return new Intl.NumberFormat(locale === "he" ? "he-IL" : "en-GB", { maximumFractionDigits: 1 }).format(hours);
}
