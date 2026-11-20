"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { PriorityBadge, ReasonText, StatusPill } from "./domain";
import { EmptyState, Table, Td, Th } from "./ui";
import { useI18n } from "@/lib/i18n";
import { date, money } from "@/lib/format";
import { reviewedIds } from "@/lib/review";
import type { ReviewQueueItem } from "@/lib/types";

export function ReviewQueue({ items }: { items: ReviewQueueItem[] }) {
  const { t, locale } = useI18n();
  const [reviewed, setReviewed] = useState<string[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    setReviewed(reviewedIds());
    try { setCurrent(sessionStorage.getItem("invoiceflow:current")); } catch { /* Optional session indicator. */ }
  }, [items]);
  if (!items.length) return <EmptyState icon={<ClipboardCheck className="h-8 w-8 text-ok" />} title={t.exceptions.empty} />;
  return <>
  <ul data-testid="mobile-review-queue" className="divide-y divide-line md:hidden">
    {items.map((item) => <li key={item.exception_id} className="space-y-3 p-4" aria-current={current === item.exception_id ? "true" : undefined}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={`/exceptions/${item.exception_id}`} className={`font-semibold text-accent ${reviewed.includes(item.exception_id) ? "line-through" : ""}`}><bdi>{item.invoice_number ?? "—"}</bdi></Link>
        <PriorityBadge level={item.priority.level} />
      </div>
      <p className="truncate text-sm text-ink-2" dir="auto">{locale === "en" && item.supplier_name_en ? item.supplier_name_en : item.supplier_name ?? t.common.unknown}</p>
      <ul className="space-y-1 text-sm text-ink-2">{item.priority.reasons.slice(0, 2).map((reason, index) =>
        <li key={`${reason.code}-${index}`}><ReasonText reason={reason} currency={item.currency} /></li>)}</ul>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-xs text-ink-3">{t.review.atRisk}</dt><dd className="mt-1 font-semibold num"><bdi>{Number(item.amount_at_risk) ? money(item.amount_at_risk, item.currency) : "—"}</bdi></dd></div>
        <div><dt className="text-xs text-ink-3">{t.review.due}</dt><dd className="mt-1">{item.due_date ? date(item.due_date, locale) : t.review.undated}</dd></div>
      </dl>
      <div className="flex flex-wrap items-center justify-between gap-2"><StatusPill status={item.status} />
        <Link href={`/exceptions/${item.exception_id}`} className="inline-flex min-h-10 items-center font-medium text-accent underline underline-offset-4">{["open", "escalated", "pending_info", "draft"].includes(item.status) ? t.review.investigate : t.review.viewDecision}</Link>
      </div>
      {reviewed.includes(item.exception_id) && <p className="text-xs text-ok">{t.review.reviewedThisSession}</p>}
      {current === item.exception_id && <p className="text-xs text-ink-2">{t.review.current}</p>}
    </li>)}
  </ul>
  <div className="hidden md:block"><Table>
    <thead><tr><Th>{t.review.rank}</Th><Th>{t.review.priority}</Th><Th>{t.recon.invoice}</Th><Th>{t.common.supplier}</Th><Th>{t.review.reason}</Th><Th className="text-end">{t.review.atRisk}</Th><Th>{t.review.due}</Th><Th>{t.common.status}</Th><Th>{t.review.nextAction}</Th></tr></thead>
    <tbody>{items.map((item) => {
      const done = reviewed.includes(item.exception_id);
      const href = `/exceptions/${item.exception_id}`;
      return <tr key={item.exception_id} className={current === item.exception_id ? "bg-accent-soft/50" : "hover:bg-sunken/60"} aria-current={current === item.exception_id ? "true" : undefined}>
        <Td className="text-ink-3 num">{item.priority.rank}</Td>
        <Td><PriorityBadge level={item.priority.level} /></Td>
        <Td><Link href={href} className={`font-medium text-ink underline-offset-4 hover:underline ${done ? "line-through" : ""}`}><bdi>{item.invoice_number ?? "—"}</bdi></Link>
          {done && <span className="mt-1 block text-xs text-ok">{t.review.reviewedThisSession}</span>}
          {current === item.exception_id && <span className="mt-1 block text-xs text-ink-2">{t.review.current}</span>}
        </Td>
        <Td className="max-w-48"><span dir="auto" className="block truncate">{locale === "en" && item.supplier_name_en ? item.supplier_name_en : item.supplier_name ?? t.common.unknown}</span></Td>
        <Td className="min-w-48 max-w-72"><ul className="space-y-1 text-sm text-ink-2">{item.priority.reasons.slice(0, 2).map((reason, i) => <li key={`${reason.code}-${i}`}><ReasonText reason={reason} currency={item.currency} /></li>)}</ul></Td>
        <Td className={`whitespace-nowrap text-end font-medium num ${item.priority.level === "critical" ? "text-danger" : "text-ink"}`}><bdi>{Number(item.amount_at_risk) ? money(item.amount_at_risk, item.currency) : "—"}</bdi></Td>
        <Td className="whitespace-nowrap text-sm"><span className={item.due_in_days !== null && item.due_in_days < 0 ? "text-warn" : "text-ink-2"}>{item.due_date ? date(item.due_date, locale) : t.review.undated}</span></Td>
        <Td><StatusPill status={item.status} /></Td>
        <Td><Link href={href} className="inline-flex min-h-9 items-center font-medium text-accent underline-offset-4 hover:underline">{["open", "escalated", "pending_info", "draft"].includes(item.status) ? t.review.investigate : t.review.viewDecision}</Link></Td>
      </tr>;
    })}</tbody>
  </Table></div></>;
}
