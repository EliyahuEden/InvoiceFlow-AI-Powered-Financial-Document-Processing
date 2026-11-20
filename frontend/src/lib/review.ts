import type { Dictionary } from "./i18n/dictionaries";
import type { PriorityReason } from "./types";
import { money } from "./format";

export function priorityReasonText(t: Dictionary, reason: PriorityReason, currency?: string | null): string {
  const template = (t.review.reasons as Record<string, string>)[reason.code] ?? t.review.reasons.review_needed;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = reason.params?.[key];
    if (key === "finding") return (t.finding as Record<string, string>)[String(value)] ?? t.review.reasons.review_needed;
    if (key === "amount") return money(String(value ?? "0"), currency);
    return String(value ?? "—");
  });
}

export const REVIEWED_KEY = "invoiceflow:reviewed";
export function reviewedIds(): string[] {
  try {
    const stored: unknown = JSON.parse(sessionStorage.getItem(REVIEWED_KEY) ?? "[]");
    return Array.isArray(stored) ? stored.filter((id): id is string => typeof id === "string") : [];
  } catch { return []; }
}
export function markReviewed(id: string): void {
  try { sessionStorage.setItem(REVIEWED_KEY, JSON.stringify([...new Set([...reviewedIds(), id])])); }
  catch { /* Session progress is optional when browser storage is unavailable. */ }
}
