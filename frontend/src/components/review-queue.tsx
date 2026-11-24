"use client";

import Link from "next/link";
import { TransitionLink } from "./transition-link";
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
  return <span className={cx("inline-grid h-6 min-w-6 shrink-0 place-items-center rounded-md border px-1 text-xs font-medium num",
    priority.level === "critical" ? "border-danger/25 bg-danger-soft text-danger" : priority.level === "high" ? "border-warn/25 bg-warn-soft text-warn" : "border-line bg-ink/[.04] text-ink-2")}>
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
    amount: item.amount_at_risk_base
      ? `${money(item.amount_at_risk, item.currency)} (≈ ${money(item.amount_at_risk_base, "ILS")})`
      : money(item.amount_at_risk, item.currency),
    amountTitle: item.amount_at_risk_base
      ? t.review.fxNote.replace("{date}", item.fx_as_of ? date(item.fx_as_of, locale) : "—") : undefined,
    due: item.due_date ? date(item.due_date, locale) : t.review.undated,
    action: ["open", "escalated", "pending_info", "draft"].includes(item.status) ? t.review.investigate : t.review.viewDecision,
  }));

  if (compact) return <ol className="divide-y divide-line">
    {rows.map(({ item, href, done, current: active, supplier, amount, amountTitle, due }, index) => <li key={item.exception_id} style={stagger(index)} className="animate-rise [animation-fill-mode:both]">
      <TransitionLink href={href} aria-current={active || undefined}
        className={cx("group grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-0.5 px-4 py-2.5 transition-colors hover:bg-ink/[.03] sm:grid-cols-[auto_minmax(0,1.1fr)_minmax(0,1.4fr)_auto_auto]",
          active && "bg-accent-soft/40")}>
        <Rank priority={item.priority} />
        <div className="min-w-0">
          <p className="flex min-w-0 items-center gap-2"><PriorityBadge level={item.priority.level} />
            <span dir="auto" className="truncate text-base font-medium text-ink">{supplier}</span></p>
          <p className="flex flex-wrap items-center gap-x-1.5 text-sm text-ink-3"><bdi data-vt-source className={cx("inline-block whitespace-nowrap font-mono text-xs", done && "line-through")}>{item.invoice_number ?? "—"}</bdi>
            <span aria-hidden>·</span><bdi className="whitespace-nowrap">{due}</bdi><SessionState done={done} current={active} /></p>
        </div>
        <p className="col-start-2 truncate text-sm text-ink-2 sm:col-start-auto">{item.priority.reasons[0] ? <ReasonText reason={item.priority.reasons[0]} currency={item.currency} /> : null}</p>
        <bdi className="col-start-2 justify-self-start whitespace-nowrap text-base font-medium text-ink num ltr sm:col-start-auto sm:justify-self-end" title={amountTitle}>{amount}</bdi>
        <ChevronRight className="hidden h-3.5 w-3.5 text-ink-3 group-hover:text-ink rtl:rotate-180 sm:block" aria-hidden />
      </TransitionLink>
    </li>)}
  </ol>;

  return <>
    <ol data-testid="mobile-review-queue" className="divide-y divide-line lg:hidden">
      {rows.map(({ item, href, done, current: active, supplier, amount, amountTitle, due, action }, index) => <li key={item.exception_id} style={stagger(index)}
        className="animate-rise space-y-3 p-4 [animation-fill-mode:both]" aria-current={active || undefined}>
        <div className="flex items-start gap-3">
          <Rank priority={item.priority} />
          <div className="min-w-0 flex-1"><p dir="auto" className="break-words font-medium text-ink">{supplier}</p>
            <TransitionLink href={href} className={cx("text-sm text-accent hover:underline", done && "line-through")}><bdi>{item.invoice_number ?? "—"}</bdi></TransitionLink></div>
          <PriorityBadge level={item.priority.level} />
        </div>
        <ul className="space-y-1 text-sm text-ink-2">{item.priority.reasons.map((reason, index) =>
          <li key={`${reason.code}-${index}`}><ReasonText reason={reason} currency={item.currency} /></li>)}</ul>
        <dl className="grid grid-cols-2 gap-3 rounded-md border border-line bg-ink/[.03] px-3 py-2 text-sm">
          <div><dt className="text-xs text-ink-3">{t.review.atRisk}</dt><dd className="mt-0.5 break-words font-semibold num"><bdi title={amountTitle}>{amount}</bdi></dd></div>
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
      <tbody>{rows.map(({ item, href, done, current: active, supplier, amount, amountTitle, due, action }, index) => <tr key={item.exception_id} style={stagger(index)}
        className={cx("animate-rise [animation-fill-mode:both]", active && "bg-accent-soft/40")} aria-current={active || undefined}>
        <Td><Rank priority={item.priority} /></Td>
        <Td><PriorityBadge level={item.priority.level} /></Td>
        <Td><div className="min-w-24 space-y-0.5"><p dir="auto" className="break-words font-medium leading-snug">{supplier}</p>
          <TransitionLink href={href} className={cx("block w-fit font-mono text-xs text-accent underline-offset-4 hover:underline", done && "line-through")}><bdi>{item.invoice_number ?? "—"}</bdi></TransitionLink>
          {(done || active) && <div className="flex flex-wrap gap-1"><SessionState done={done} current={active} /></div>}
        </div></Td>
        <Td><ul className="min-w-28 space-y-1 text-sm leading-snug text-ink-2">{item.priority.reasons.map((reason, index) =>
          <li key={`${reason.code}-${index}`}><ReasonText reason={reason} currency={item.currency} /></li>)}</ul></Td>
        <Td className="whitespace-nowrap text-end font-medium num"><bdi className="ltr" title={amountTitle}>{amount}</bdi></Td>
        <Td className={cx("text-sm", item.due_in_days !== null && item.due_in_days < 0 ? "text-warn" : "text-ink-2")}><bdi>{due}</bdi></Td>
        <Td><StatusPill status={item.status} /></Td>
        <Td><Button variant="secondary" size="sm" asChild><Link href={href}>{action}<ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden /></Link></Button></Td>
      </tr>)}</tbody>
    </Table></div>
  </>;
}
