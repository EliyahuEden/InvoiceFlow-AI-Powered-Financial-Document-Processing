"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, CalendarClock, CalendarDays, CheckCheck, ChevronRight, CircleAlert, Clock3, Layers, Wallet } from "lucide-react";
import { ReviewQueue } from "@/components/review-queue";
import { ReviewNextButton } from "@/components/review-next";
import { useSession } from "@/components/session";
import { Button, cx, ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { useApi } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ReviewSummary } from "@/lib/types";

export default function OverviewPage() {
  const { t } = useI18n();
  const { can } = useSession();
  const { data, error, mutate } = useApi<ReviewSummary>("/api/review/summary", { refreshInterval: 30_000 });
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;

  const urgency = [
    { label: t.review.critical, href: "/exceptions?level=critical", value: data?.by_level.critical, icon: AlertTriangle, tone: "bg-danger-soft text-danger" },
    { label: t.review.high, href: "/exceptions?level=high", value: data?.by_level.high, icon: CircleAlert, tone: "bg-warn-soft text-warn" },
    { label: t.review.overdue, href: "/exceptions?due=overdue", value: data?.overdue, icon: CalendarClock, tone: "bg-warn-soft text-warn" },
    { label: t.review.dueSoon, href: "/exceptions?due=soon", value: data?.due_soon, icon: CalendarDays, tone: "bg-info-soft text-info" },
  ];
  const workflow = [
    { label: t.review.readyForApproval, href: "/invoices?status=reconciled", value: data?.ready_for_approval, icon: CheckCheck, tone: "text-ok" },
    { label: t.review.awaitingInfo, href: "/exceptions?status=pending_info", value: data?.awaiting_info, icon: Clock3, tone: "text-warn" },
    { label: t.review.escalated, href: "/exceptions?status=escalated", value: data?.escalated, icon: CircleAlert, tone: "text-warn" },
    { label: t.review.processing, href: "/invoices?status=processing", value: data?.processing, icon: Layers, tone: "text-info" },
  ];
  const currencyRows = data ? [
    { currency: data.currency, value_under_review: data.value_under_review, amount_at_risk: data.amount_at_risk },
    ...(data.totals_by_currency ?? []).filter((entry) => entry.currency !== data.currency),
  ] : [];

  return <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(19rem,1fr)]">
    <div className="min-w-0 space-y-5">
      <section className="command-hero min-w-0 p-5 sm:p-7">
        <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{t.review.dashboardTitle}</h1>
        <p className="mt-1.5 text-base text-ink-2">{t.review.subtitle}</p>
        <div className="my-6 flex flex-wrap items-end justify-between gap-4">
          <Link href="/exceptions" className="group inline-flex flex-wrap items-baseline gap-x-3 gap-y-1">
            {data ? <bdi className="text-6xl font-semibold leading-none tracking-tight text-ink num sm:text-7xl">{data.needs_review}</bdi>
              : <Skeleton className="h-14 w-20" />}
            <span className="text-lg font-medium text-ink-2 group-hover:underline">{t.review.needsReview}</span>
          </Link>
          {can("exception:decide") && <ReviewNextButton size="lg" />}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {urgency.map(({ label, href, value, icon: Icon, tone }) => <Link key={href} href={href} className="command-metric min-w-0 p-3 sm:p-4">
            <div className="flex flex-wrap items-center gap-2"><span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-xl", tone)}><Icon className="h-4 w-4" aria-hidden /></span>
              {value === undefined ? <Skeleton className="h-6 w-7" /> : <bdi className="text-xl font-semibold leading-none text-ink num">{value}</bdi>}</div>
            <p className="mt-2 break-words text-sm font-medium text-ink-2">{label}</p>
          </Link>)}
        </div>
      </section>
      <Panel className="command-panel overflow-hidden">
        <PanelHeader title={<span className="inline-flex items-center gap-2"><Wallet className="h-5 w-5 text-info" aria-hidden />{t.review.exposure}</span>}
          sub={currencyRows.length > 1 ? t.review.amountNote : undefined} />
        {data ? <Table><thead><tr><Th>{t.invoice.currency}</Th><Th className="text-end">{t.review.valueUnderReview}</Th><Th className="text-end">{t.review.atRisk}</Th></tr></thead>
          <tbody>{currencyRows.map((entry) => <tr key={entry.currency ?? "unknown"}>
            <Td className="font-medium"><bdi>{entry.currency ?? t.common.unknown}</bdi></Td>
            <Td className="text-end num"><bdi>{money(entry.value_under_review, entry.currency)}</bdi></Td>
            <Td className="text-end font-semibold num"><bdi>{money(entry.amount_at_risk, entry.currency)}</bdi></Td>
          </tr>)}</tbody></Table> : <div className="p-4"><Skeleton className="h-16 w-full" /></div>}
      </Panel>
      <Panel className="command-panel overflow-hidden">
        <PanelHeader title={t.review.health} />
        <ul className="grid grid-cols-1 sm:grid-cols-2">
          {workflow.map(({ label, href, value, icon: Icon, tone }) => <li key={href} className="border-t border-line first:border-t-0 sm:[&:nth-child(2)]:border-t-0">
            <Link href={href} className="flex items-center gap-3 px-4 py-3 hover:bg-sunken">
              <Icon className={cx("h-4 w-4 shrink-0", tone)} aria-hidden /><span className="min-w-0 flex-1 text-sm font-medium">{label}</span>
              {value === undefined ? <Skeleton className="h-5 w-7" /> : <bdi className="font-semibold num">{value}</bdi>}
              <ChevronRight className="h-4 w-4 text-ink-3 rtl:rotate-180" aria-hidden />
            </Link>
          </li>)}
        </ul>
      </Panel>
    </div>
    <aside className="command-aside min-w-0">
      <Panel className="command-panel overflow-hidden">
        <PanelHeader title={t.review.queue} sub={t.review.highestFirst} />
        {data ? <ReviewQueue compact items={data.top} /> : <div className="p-4"><Skeleton className="h-64 w-full" /></div>}
        <div className="border-t border-line p-3"><Button className="w-full" asChild><Link href="/exceptions">{t.review.openQueue}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button></div>
      </Panel>
    </aside>
  </div>;
}
