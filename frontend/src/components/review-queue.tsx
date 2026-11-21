"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCheck, ChevronRight, ClipboardCheck } from "lucide-react";
import { PriorityBadge, ReasonText, StatusPill } from "./domain";
import { Button, cx, EmptyState, Table, Td, Th } from "./ui";
import { useI18n } from "@/lib/i18n";
import { date, money } from "@/lib/format";
import { reviewedIds } from "@/lib/review";
import type { ReviewQueueItem } from "@/lib/types";

/** A short first-render stagger (capped), so a long queue still appears almost at once. */
const stagger = (index: number): React.CSSProperties => ({ animationDelay: `${Math.min(index, 8) * 24}ms` });

function Rank({ priority }: Pick<ReviewQueueItem, "priority">) {
  const { t } = useI18n();
  return <span className={cx("inline-grid h-8 min-w-8 shrink-0 place-items-center rounded-full px-1.5 text-sm font-semibold num",
    priority.level === "critical" ? "bg-danger-soft text-danger" : priority.level === "high" ? "bg-warn-soft text-warn" : "bg-sunken text-ink-2")}>
    <span className="sr-only">{t.review.rank} </span>{priority.rank}
  </span>;
}

function SessionState({ done, current }: { done: boolean; current: boolean }) {
  const { t } = useI18n();
  return <>{done && <span className="inline-flex items-center gap-1 text-xs text-ok"><CheckCheck className="h-3.5 w-3.5" aria-hidden />{t.review.reviewedThisSession}</span>}
    {current && <span className="text-xs font-medium text-accent">{t.review.current}</span>}</>;
}

export function ReviewQueue({ items, compact = false }: { items: ReviewQueueItem[]; compact?: boolean }) {
  const { t, locale } = useI18n();
  const [reviewed, setReviewed] = useState<string[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    setReviewed(reviewedIds());
    try { setCurrent(sessionStorage.getItem("invoiceflow:current")); } catch { /* Optional session indicator. */ }
  }, [items]);
  if (!items.length) return <EmptyState icon={<ClipboardCheck className="h-8 w-8 text-ok" />} title={t.exceptions.empty} />;

  const rows = items.map((item) => ({
    item, href: `/exceptions/${item.exception_id}`,
    done: reviewed.includes(item.exception_id), current: current === item.exception_id,
    supplier: (locale === "en" && item.supplier_name_en) || item.supplier_name || t.common.unknown,
    amount: money(item.amount_at_risk, item.currency),
    due: item.due_date ? date(item.due_date, locale) : t.review.undated,
    action: ["open", "escalated", "pending_info", "draft"].includes(item.status) ? t.review.investigate : t.review.viewDecision,
  }));

  if (compact) return <ol className="divide-y divide-line">
    {rows.map(({ item, href, done, current: active, supplier, amount }, index) => <li key={item.exception_id} style={stagger(index)} className="animate-rise [animation-fill-mode:both]">
      <Link href={href} aria-current={active || undefined} className="group grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 px-4 py-4 hover:bg-sunken/70 sm:px-5">
        <Rank priority={item.priority} />
        <div className="min-w-0 space-y-1.5">
          <p dir="auto" className="break-words font-semibold leading-snug text-ink">{supplier}</p>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-2"><bdi className={done ? "line-through" : undefined}>{item.invoice_number ?? "—"}</bdi><PriorityBadge level={item.priority.level} /></p>
          {item.priority.reasons[0] && <p className="text-sm text-ink-2"><ReasonText reason={item.priority.reasons[0]} currency={item.currency} /></p>}
          <p className="text-xs text-ink-3">{t.review.atRisk} <bdi className="ms-1 font-semibold text-ink num">{amount}</bdi></p>
          {(done || active) && <div className="flex flex-wrap gap-2"><SessionState done={done} current={active} /></div>}
        </div>
        <ChevronRight className="mt-1 h-4 w-4 text-ink-3 group-hover:text-ink rtl:rotate-180" aria-hidden />
      </Link>
    </li>)}
  </ol>;

  return <>
    <ol data-testid="mobile-review-queue" className="divide-y divide-line lg:hidden">
      {rows.map(({ item, href, done, current: active, supplier, amount, due, action }, index) => <li key={item.exception_id} style={stagger(index)}
        className="animate-rise space-y-3 p-4 [animation-fill-mode:both]" aria-current={active || undefined}>
        <div className="flex items-start gap-3">
          <Rank priority={item.priority} />
          <div className="min-w-0 flex-1"><p dir="auto" className="break-words font-semibold text-ink">{supplier}</p>
            <Link href={href} className={cx("text-sm text-accent hover:underline", done && "line-through")}><bdi>{item.invoice_number ?? "—"}</bdi></Link></div>
          <PriorityBadge level={item.priority.level} />
        </div>
        <ul className="space-y-1 text-sm text-ink-2">{item.priority.reasons.map((reason, index) =>
          <li key={`${reason.code}-${index}`}><ReasonText reason={reason} currency={item.currency} /></li>)}</ul>
        <dl className="grid grid-cols-2 gap-3 rounded-md bg-sunken px-3 py-2 text-sm">
          <div><dt className="text-xs text-ink-3">{t.review.atRisk}</dt><dd className="mt-0.5 break-words font-semibold num"><bdi>{amount}</bdi></dd></div>
          <div><dt className="text-xs text-ink-3">{t.review.due}</dt><dd className="mt-0.5"><bdi>{due}</bdi></dd></div>
        </dl>
        <div className="flex flex-wrap items-center justify-between gap-2"><StatusPill status={item.status} />
          <Button variant="secondary" size="sm" asChild><Link href={href}>{action}<ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden /></Link></Button>
        </div>
        {(done || active) && <div className="flex flex-wrap gap-2"><SessionState done={done} current={active} /></div>}
      </li>)}
    </ol>
    <div className="hidden lg:block"><Table>
      <thead><tr><Th>{t.review.rank}</Th><Th>{t.review.priority}</Th><Th>{t.common.supplier} / {t.recon.invoice}</Th>
        <Th>{t.review.reason}</Th><Th className="text-end">{t.review.atRisk}</Th><Th>{t.review.due}</Th><Th>{t.common.status}</Th><Th>{t.review.nextAction}</Th></tr></thead>
      <tbody>{rows.map(({ item, href, done, current: active, supplier, amount, due, action }, index) => <tr key={item.exception_id} style={stagger(index)}
        className={cx("animate-rise [animation-fill-mode:both]", active ? "bg-accent-soft/50" : "hover:bg-sunken/60")} aria-current={active || undefined}>
        <Td><Rank priority={item.priority} /></Td>
        <Td><PriorityBadge level={item.priority.level} /></Td>
        <Td><div className="min-w-24 space-y-1"><p dir="auto" className="break-words font-semibold leading-snug">{supplier}</p>
          <Link href={href} className={cx("block text-sm text-accent underline-offset-4 hover:underline", done && "line-through")}><bdi>{item.invoice_number ?? "—"}</bdi></Link>
          {(done || active) && <div className="flex flex-wrap gap-1"><SessionState done={done} current={active} /></div>}
        </div></Td>
        <Td><ul className="min-w-28 space-y-1 text-sm leading-snug text-ink-2">{item.priority.reasons.map((reason, index) =>
          <li key={`${reason.code}-${index}`}><ReasonText reason={reason} currency={item.currency} /></li>)}</ul></Td>
        <Td className="whitespace-nowrap text-end font-semibold num"><bdi>{amount}</bdi></Td>
        <Td className={cx("text-sm", item.due_in_days !== null && item.due_in_days < 0 ? "text-warn" : "text-ink-2")}><bdi>{due}</bdi></Td>
        <Td><StatusPill status={item.status} /></Td>
        <Td><Button variant="secondary" size="sm" asChild><Link href={href}>{action}<ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden /></Link></Button></Td>
      </tr>)}</tbody>
    </Table></div>
  </>;
}
