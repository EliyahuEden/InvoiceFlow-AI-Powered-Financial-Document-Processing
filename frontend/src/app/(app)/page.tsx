"use client";

import Link from "next/link";
import { ArrowRight, CheckCheck, ChevronRight, CircleAlert, Clock3, Layers } from "lucide-react";
import { ReviewQueue } from "@/components/review-queue";
import { ExportMenu } from "@/components/export-menu";
import { PaymentReminders } from "@/components/invoice-payment";
import { ReviewNextButton } from "@/components/review-next";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, cx, ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { useApi } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ReviewSummary } from "@/lib/types";

/** One cell of the figures strip: a label, the figure, and what it breaks down into. */
function Figure({ href, label, value, children, tone }: {
  href: string; label: string; value: React.ReactNode; children?: React.ReactNode; tone?: "danger" | "warn";
}) {
  return (
    <Link href={href} className="group relative min-w-0 px-4 py-3.5 transition-colors hover:bg-ink/[.03] sm:px-5">
      <p className="flex items-center gap-1.5 text-sm text-ink-3">
        {tone && <span className={cx("h-1.5 w-1.5 rounded-full", tone === "danger" ? "bg-danger" : "bg-warn")} aria-hidden />}
        {label}
      </p>
      <div className="mt-1.5 text-figure font-semibold text-ink num">{value}</div>
      {children && <div className="mt-1 text-sm text-ink-3">{children}</div>}
    </Link>
  );
}

export default function OverviewPage() {
  const { t } = useI18n();
  const { can } = useSession();
  const { data, error, mutate } = useApi<ReviewSummary>("/api/review/summary", { refreshInterval: 30_000 });
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;

  const workflow = [
    { label: t.review.readyForApproval, href: "/invoices?status=reconciled", value: data?.ready_for_approval, icon: CheckCheck, tone: "text-ok" },
    { label: t.review.awaitingInfo, href: "/exceptions?status=pending_info", value: data?.awaiting_info, icon: Clock3, tone: "text-warn" },
    { label: t.review.escalated, href: "/exceptions?status=escalated", value: data?.escalated, icon: CircleAlert, tone: "text-warn" },
    { label: t.review.processing, href: "/invoices?status=processing", value: data?.processing, icon: Layers, tone: "text-ink-3" },
  ];
  const currencyRows = data ? [
    { currency: data.currency, value_under_review: data.value_under_review, amount_at_risk: data.amount_at_risk },
    ...(data.totals_by_currency ?? []).filter((entry) => entry.currency !== data.currency),
  ] : [];
  const n = (v: number | undefined) => (v === undefined ? <Skeleton className="h-7 w-10" /> : <bdi>{v}</bdi>);

  return <div className="min-w-0 space-y-4">
    <PageHeader title={t.review.dashboardTitle} sub={t.review.subtitle}
      actions={<>{can("invoice:read") && <ExportMenu report="insights" />}{can("exception:decide") && <ReviewNextButton />}</>} />

    <Panel className="grid grid-cols-2 divide-line lg:grid-cols-4 lg:divide-x rtl:lg:divide-x-reverse [&>*]:border-line max-lg:[&>*:nth-child(-n+2)]:border-b max-lg:[&>*:nth-child(odd)]:border-e">
      <Figure href="/exceptions" label={t.review.needsReview} value={n(data?.needs_review)}>
        {data && <><span className="text-danger">{data.by_level.critical} {t.review.critical}</span> · <span className="text-warn">{data.by_level.high} {t.review.high}</span></>}
      </Figure>
      <Figure href="/exceptions" label={t.review.atRisk} tone="danger"
        value={data ? <bdi className="ltr">{money(data.amount_at_risk, data.currency)}</bdi> : <Skeleton className="h-7 w-28" />}>
        {data && <>{t.review.valueUnderReview} <bdi className="ltr">{money(data.value_under_review, data.currency)}</bdi></>}
      </Figure>
      <Figure href="/exceptions?due=overdue" label={t.review.overdue} tone={data && data.overdue > 0 ? "warn" : undefined} value={n(data?.overdue)}>
        {data && <>{data.due_soon} {t.review.dueSoon}</>}
      </Figure>
      <Figure href="/invoices?status=reconciled" label={t.review.readyForApproval} value={n(data?.ready_for_approval)}>
        {data && <>{data.awaiting_info} {t.review.awaitingInfo}</>}
      </Figure>
    </Panel>

    <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <Panel className="min-w-0">
        <PanelHeader title={t.review.queue} sub={t.review.highestFirst}
          actions={<Button size="sm" variant="ghost" asChild><Link href="/exceptions">{t.review.openQueue}<ArrowRight className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden /></Link></Button>} />
        {data ? <ReviewQueue compact items={data.top} /> : <div className="p-4"><Skeleton className="h-64 w-full" /></div>}
      </Panel>

      <aside className="command-aside min-w-0 space-y-4">
        <PaymentReminders />
        <Panel>
          <PanelHeader title={t.review.exposure} sub={currencyRows.length > 1 ? t.review.amountNote : undefined} />
          {data ? <Table><thead><tr><Th>{t.invoice.currency}</Th><Th className="text-end">{t.review.valueUnderReview}</Th><Th className="text-end">{t.review.atRisk}</Th></tr></thead>
            <tbody>{currencyRows.map((entry) => <tr key={entry.currency ?? "unknown"}>
              <Td className="font-medium"><bdi>{entry.currency ?? t.common.unknown}</bdi></Td>
              <Td className="text-end text-ink-2 num"><bdi className="ltr">{money(entry.value_under_review, entry.currency)}</bdi></Td>
              <Td className="text-end font-medium num"><bdi className="ltr">{money(entry.amount_at_risk, entry.currency)}</bdi></Td>
            </tr>)}</tbody></Table> : <div className="p-4"><Skeleton className="h-16 w-full" /></div>}
        </Panel>
        <Panel>
          <PanelHeader title={t.review.health} />
          <ul>
            {workflow.map(({ label, href, value, icon: Icon, tone }) => <li key={href} className="border-t border-line first:border-t-0">
              <Link href={href} className="flex h-10 items-center gap-2.5 px-4 transition-colors hover:bg-ink/[.03]">
                <Icon className={cx("h-4 w-4 shrink-0", tone)} aria-hidden /><span className="min-w-0 flex-1 text-base text-ink-2">{label}</span>
                {value === undefined ? <Skeleton className="h-5 w-7" /> : <bdi className="font-medium text-ink num">{value}</bdi>}
                <ChevronRight className="h-3.5 w-3.5 text-ink-3 rtl:rotate-180" aria-hidden />
              </Link>
            </li>)}
          </ul>
        </Panel>
      </aside>
    </div>
  </div>;
}
