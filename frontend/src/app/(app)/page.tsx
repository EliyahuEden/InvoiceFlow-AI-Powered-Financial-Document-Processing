"use client";

import Link from "next/link";
import { ArrowUpRight, Clock3 } from "lucide-react";
import { PageHeader } from "@/components/shell";
import { ReviewQueue } from "@/components/review-queue";
import { ReviewNextButton } from "@/components/review-next";
import { useSession } from "@/components/session";
import { ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ReviewSummary } from "@/lib/types";

export default function OverviewPage() {
  const { t } = useI18n();
  const { can } = useSession();
  const { data, error, mutate } = useApi<ReviewSummary>("/api/review/summary", { refreshInterval: 30_000 });
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  return <div className="space-y-6">
    <PageHeader title={t.overview.title} sub={t.review.subtitle} actions={can("exception:decide") && <ReviewNextButton />} />
    <div className="grid grid-cols-2 divide-y divide-line border-y border-line bg-surface sm:divide-y-0 xl:grid-cols-4">
      <Counter href="/exceptions" label={t.review.needsReview} value={data?.needs_review}>
        <span className="text-danger">{data?.by_level.critical ?? 0} {t.review.critical}</span><span> · </span><span className="text-warn">{data?.by_level.high ?? 0} {t.review.high}</span>
      </Counter>
      <Counter href="/exceptions" label={t.review.atRisk} value={data && money(data.amount_at_risk, data.currency)}>
        {t.review.valueUnderReview}: <bdi>{data ? money(data.value_under_review, data.currency) : "—"}</bdi>
      </Counter>
      <Counter href="/invoices?status=reconciled" label={t.review.readyForApproval} value={data?.ready_for_approval}>{t.ai.deterministic}</Counter>
      <Counter href="/exceptions?status=pending_info" label={t.review.awaitingInfo} value={data?.awaiting_info}>{t.review.escalated}: {data?.escalated ?? 0}</Counter>
    </div>
    {data?.totals_by_currency?.some((v) => v.currency !== data.currency) && <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-2" role="note">
      <span>{t.review.amountNote}</span>{data.totals_by_currency.filter((v) => v.currency !== data.currency).map((v) => <span key={v.currency ?? "unknown"}>{v.currency ?? t.common.unknown}: <bdi>{money(v.amount_at_risk, v.currency)}</bdi> {t.review.atRisk} · <bdi>{money(v.value_under_review, v.currency)}</bdi> {t.review.valueUnderReview}</span>)}
    </div>}
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink-2">
      <span className="inline-flex items-center gap-2"><Clock3 className="h-4 w-4" aria-hidden />{t.review.overdue}: <b className="num text-warn">{data?.overdue ?? "—"}</b></span>
      <span>{t.review.dueSoon}: <b className="num text-ink">{data?.due_soon ?? "—"}</b></span>
      {!!data?.processing && <span>{t.review.processing}: <b className="num">{data.processing}</b></span>}
    </div>
    <Panel>
      <PanelHeader title={t.review.queue} sub={t.review.reason} actions={<Link href="/exceptions" className="inline-flex items-center gap-1 text-sm font-medium text-accent">{t.review.openQueue}<ArrowUpRight className="h-4 w-4 rtl:-rotate-90" aria-hidden /></Link>} />
      {data ? <ReviewQueue items={data.top} /> : <div className="p-4"><Skeleton className="h-64 w-full" /></div>}
    </Panel>
  </div>;
}

function Counter({ href, label, value, children }: { href: string; label: string; value?: React.ReactNode; children: React.ReactNode }) {
  return <Link href={href} className="min-w-0 border-e border-line px-3 py-3 transition-colors hover:bg-sunken/70 sm:px-5 sm:py-5 last:border-e-0">
    <p className="text-sm font-medium text-ink-2">{label}</p>
    {value === undefined ? <Skeleton className="my-3 h-9 w-24" /> : <p className="my-2 truncate text-xl font-semibold tracking-tight text-ink num sm:text-3xl"><bdi>{value}</bdi></p>}
    <p className="text-xs leading-relaxed text-ink-2">{children}</p>
  </Link>;
}
