"use client";

import Link from "next/link";
import { TransitionLink } from "./transition-link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCheck, ChevronRight, ClipboardCheck, FileText } from "lucide-react";
import { PriorityBadge, ReasonText, StatusPill } from "./domain";
import { Button, cx, EmptyState, Table, Td, Th } from "./ui";
import { useI18n } from "@/lib/i18n";
import { date, money } from "@/lib/format";
import { dueRelative, reviewedIds } from "@/lib/review";
import type { ReviewQueueItem } from "@/lib/types";

/** A short first-render stagger (capped), so a long queue still appears almost at once. */
const stagger = (index: number): React.CSSProperties => ({ animationDelay: `${Math.min(index, 8) * 24}ms` });
const ACTIONABLE = ["open", "escalated", "pending_info", "draft"];

function Rank({ priority }: Pick<ReviewQueueItem, "priority">) {
  const { t } = useI18n();
  return <span className={cx("inline-grid h-7 min-w-7 shrink-0 place-items-center rounded-full border px-1 text-sm font-bold num",
    priority.level === "critical" ? "border-danger/25 bg-danger-soft text-danger" : priority.level === "high" ? "border-warn/25 bg-warn-soft text-warn" : "border-line bg-sunken text-ink-2")}>
    <span className="sr-only">{t.review.rank} </span>{priority.rank}
  </span>;
}

function SessionState({ done, current }: { done: boolean; current: boolean }) {
  const { t } = useI18n();
  return <>{done && <span className="inline-flex items-center gap-1 text-xs text-ok"><CheckCheck className="h-3.5 w-3.5" aria-hidden />{t.review.reviewedThisSession}</span>}
    {current && <span className="text-xs font-medium text-accent">{t.review.current}</span>}</>;
}

/** The amount at risk in its own currency; a foreign amount adds its shekel estimate, a missing currency says so. */
export function AtRisk({ item, align = "end" }: { item: ReviewQueueItem; align?: "start" | "end" }) {
  const { t, locale } = useI18n();
  const title = item.amount_at_risk_base ? t.review.fxNote.replace("{date}", item.fx_as_of ? date(item.fx_as_of, locale) : "—") : undefined;
  return <div className={cx("min-w-0", align === "end" ? "text-end" : "text-start")}>
    <bdi className="block whitespace-nowrap font-bold text-ink num ltr" title={title}>
      {money(item.amount_at_risk, item.currency)}{item.amount_at_risk_base && <span className="sr-only"> (≈ {money(item.amount_at_risk_base, "ILS")})</span>}
    </bdi>
    {item.amount_at_risk_base
      ? <span aria-hidden className="block whitespace-nowrap text-xs text-ink-3 num" title={title}>≈ <bdi className="ltr">{money(item.amount_at_risk_base, "ILS")}</bdi></span>
      : !item.currency && <span className="block whitespace-nowrap text-xs text-ink-3">{t.review.currencyUnknown}</span>}
  </div>;
}

/** The due date and, beside it, how soon that is. */
export function DueCell({ item }: { item: ReviewQueueItem }) {
  const { t, locale } = useI18n();
  const rel = dueRelative(t, item.due_in_days);
  if (!item.due_date) return <span className="whitespace-nowrap text-sm text-ink-3">{t.review.undated}</span>;
  return <div className="min-w-0 text-sm">
    <bdi className="block whitespace-nowrap text-ink">{date(item.due_date, locale)}</bdi>
    {rel && <span className={cx("block whitespace-nowrap text-xs font-semibold", rel.tone === "danger" ? "text-danger" : rel.tone === "warn" ? "text-warn" : "text-ink-3")}>{rel.text}</span>}
  </div>;
}

export function ReviewQueue({ items, compact = false, selectedId, onSelect }: {
  items: ReviewQueueItem[]; compact?: boolean; selectedId?: string | null; onSelect?: (item: ReviewQueueItem) => void;
}) {
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
    action: ACTIONABLE.includes(item.status) ? t.review.investigate : t.review.viewDecision,
  }));

  if (compact) return <ol className="divide-y divide-line">
    {rows.map(({ item, href, done, current: active, supplier }, index) => <li key={item.exception_id} style={stagger(index)} className="animate-rise [animation-fill-mode:both]">
      <TransitionLink href={href} aria-current={active || undefined}
        className={cx("group grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-0.5 px-4 py-2.5 transition-colors hover:bg-ink/[.03] sm:grid-cols-[auto_minmax(0,1.1fr)_minmax(0,1.4fr)_auto_auto]",
          active && "bg-accent-soft/40")}>
        <Rank priority={item.priority} />
        <div className="min-w-0">
          <p className="flex min-w-0 items-center gap-2"><PriorityBadge level={item.priority.level} />
            <span dir="auto" className="truncate text-base font-medium text-ink">{supplier}</span></p>
          <p className="flex flex-wrap items-center gap-x-1.5 text-sm text-ink-3"><bdi data-vt-source className={cx("inline-block whitespace-nowrap font-mono text-xs", done && "line-through")}>{item.invoice_number ?? "—"}</bdi>
            <span aria-hidden>·</span><bdi className="whitespace-nowrap">{item.due_date ? date(item.due_date, locale) : t.review.undated}</bdi><SessionState done={done} current={active} /></p>
        </div>
        <p className="col-start-2 truncate text-sm text-ink-2 sm:col-start-auto">{item.priority.reasons[0] ? <ReasonText reason={item.priority.reasons[0]} currency={item.currency} /> : null}</p>
        <div className="col-start-2 justify-self-start sm:col-start-auto sm:justify-self-end"><CompactAmount item={item} /></div>
        <ChevronRight className="hidden h-3.5 w-3.5 text-ink-3 group-hover:text-ink rtl:rotate-180 sm:block" aria-hidden />
      </TransitionLink>
    </li>)}
  </ol>;

  return <>
    {/* phones and tablets: one card per case, every reason and the next action in reach */}
    <ol data-testid="mobile-review-queue" className="divide-y divide-line lg:hidden">
      {rows.map(({ item, href, done, current: active, supplier, action }) => <li key={item.exception_id}
        className="space-y-3 p-4" aria-current={active || undefined}>
        <div className="flex items-start gap-3">
          <Rank priority={item.priority} />
          <div className="min-w-0 flex-1"><p className="break-words font-semibold text-ink"><bdi>{supplier}</bdi></p>
            <TransitionLink href={href} className={cx("inline-flex items-center gap-1 font-mono text-sm text-accent hover:underline", done && "line-through")}>
              <FileText className="h-3.5 w-3.5" aria-hidden /><bdi>{item.invoice_number ?? "—"}</bdi></TransitionLink></div>
          <PriorityBadge level={item.priority.level} />
        </div>
        <ul className="space-y-1 text-sm leading-snug text-ink-2">{item.priority.reasons.map((reason, index) =>
          <li key={`${reason.code}-${index}`}><ReasonText reason={reason} currency={item.currency} /></li>)}</ul>
        <dl className="grid grid-cols-2 gap-3 rounded-xl bg-sunken px-3 py-2.5 text-sm">
          <div><dt className="text-xs text-ink-3">{t.review.atRisk}</dt><dd className="mt-0.5"><AtRisk item={item} align="start" /></dd></div>
          <div><dt className="text-xs text-ink-3">{t.review.due}</dt><dd className="mt-0.5"><DueCell item={item} /></dd></div>
        </dl>
        <div className="flex flex-wrap items-center justify-between gap-2">{item.status !== "open" ? <StatusPill status={item.status} /> : <span />}
          <Button variant="secondary" size="sm" asChild><Link href={href}>{action}<ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden /></Link></Button>
        </div>
        {(done || active) && <div className="flex flex-wrap gap-2"><SessionState done={done} current={active} /></div>}
      </li>)}
    </ol>

    {/* desktop: a selectable table. Selecting a row shows why it is in the queue; the action opens the case */}
    <div className="hidden lg:block"><Table className="queue-table">
      <thead><tr>
        <Th className="w-[1%] ps-5">{t.review.rank}</Th><Th>{t.common.supplier} / {t.recon.invoice}</Th>
        <Th>{t.review.reason}</Th><Th className="text-end">{t.review.atRisk}</Th><Th>{t.review.due}</Th>
        <Th className="w-[1%] pe-5"><span className="sr-only">{t.review.nextAction}</span></Th>
      </tr></thead>
      <tbody>{rows.map(({ item, href, done, current: active, supplier, action }) => {
        const selected = selectedId === item.exception_id;
        const [first, ...more] = item.priority.reasons;
        return <tr key={item.exception_id} aria-current={active || undefined} data-selected={selected || undefined}
          onClick={(e) => { if (onSelect && !(e.target as HTMLElement).closest("a,button")) onSelect(item); }}
          className={cx(onSelect && "cursor-pointer", selected && "queue-row-selected")}>
          <Td className="ps-5">
            <div className="flex items-center gap-2.5">
              {onSelect ? <button type="button" onClick={() => onSelect(item)} aria-pressed={selected} className="rounded-full focus-visible:outline-offset-2">
                <span className="sr-only">{t.review.showWhy}: {item.invoice_number ?? supplier}, </span><Rank priority={item.priority} /></button> : <Rank priority={item.priority} />}
              <div className="space-y-1"><PriorityBadge level={item.priority.level} />{item.status !== "open" && <div><StatusPill status={item.status} /></div>}</div>
            </div>
          </Td>
          <Td><div className="min-w-[9rem] max-w-[13rem] space-y-0.5"><p className="break-words font-semibold leading-snug text-ink"><bdi>{supplier}</bdi></p>
            <TransitionLink href={href} className={cx("inline-flex w-fit items-center gap-1 font-mono text-xs text-accent underline-offset-4 hover:underline", done && "line-through")}>
              <FileText className="h-3 w-3 text-ink-3" aria-hidden /><bdi>{item.invoice_number ?? "—"}</bdi></TransitionLink>
            {(done || active) && <div className="flex flex-wrap gap-1"><SessionState done={done} current={active} /></div>}
          </div></Td>
          <Td><div className="min-w-[9.5rem] max-w-[24rem] text-sm leading-snug text-ink-2">
            {first ? <p className="line-clamp-2"><ReasonText reason={first} currency={item.currency} /></p> : <span className="text-ink-3">—</span>}
            {more.length > 0 && <p className="mt-0.5 text-xs font-semibold text-ink-3">{t.review.moreReasons.replace("{n}", String(more.length))}</p>}
          </div></Td>
          <Td><AtRisk item={item} /></Td>
          <Td><DueCell item={item} /></Td>
          <Td className="pe-5"><Button variant="secondary" size="sm" asChild><Link href={href}>{action}</Link></Button></Td>
        </tr>;
      })}</tbody>
    </Table></div>
  </>;
}

/** The compact list keeps the foreign amount and its shekel estimate on one line. */
function CompactAmount({ item }: { item: ReviewQueueItem }) {
  const { t, locale } = useI18n();
  const amount = item.amount_at_risk_base
    ? `${money(item.amount_at_risk, item.currency)} (≈ ${money(item.amount_at_risk_base, "ILS")})`
    : money(item.amount_at_risk, item.currency);
  const title = item.amount_at_risk_base ? t.review.fxNote.replace("{date}", item.fx_as_of ? date(item.fx_as_of, locale) : "—") : undefined;
  return <bdi className="whitespace-nowrap text-base font-medium text-ink num ltr" title={title}>{amount}</bdi>;
}
