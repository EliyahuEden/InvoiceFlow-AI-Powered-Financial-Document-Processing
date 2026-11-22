"use client";

import Link from "next/link";
import { AlertTriangle, ArrowDownWideNarrow, CalendarClock, CheckCheck, ChevronRight, Layers, SlidersHorizontal, Wallet } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { ReviewQueue } from "@/components/review-queue";
import { ReviewNextButton } from "@/components/review-next";
import { Pager, SearchBox, type Page } from "@/components/list";
import { useSession } from "@/components/session";
import { Button, cx, ErrorState, Field, Panel, PanelHeader, Select, Skeleton } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ReviewQueueItem, ReviewSummary } from "@/lib/types";
import { label } from "@/lib/i18n/label";

type PendingApproval = { approval_id: string; step: number; required_role: string; invoice: { id: string; invoice_number: string; total: string; currency: string }; supplier_name: string };

export default function ExceptionsPage() {
  return <Suspense fallback={<Skeleton className="h-80 w-full" />}><QueuePage /></Suspense>;
}

function QueuePage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filters = { level: params.get("level") ?? "", type: params.get("type") ?? "", supplier_id: params.get("supplier_id") ?? "", due: params.get("due") ?? "", status: params.get("status") ?? "", q: params.get("q") ?? "", page: Math.max(1, Number(params.get("page")) || 1), page_size: 20 };
  const activeFilterCount = [filters.level, filters.type, filters.supplier_id, filters.due, filters.status].filter(Boolean).length;
  const [showFilters, setShowFilters] = useState(false);
  const { data, error, mutate } = useApi<Page<ReviewQueueItem>>(`/api/review/queue${qs(filters)}`, { refreshInterval: 30_000 });
  const { data: summary, error: summaryError, mutate: retrySummary } = useApi<ReviewSummary>("/api/review/summary", { refreshInterval: 30_000 });
  const { data: suppliers } = useApi<Page<{ id: string; name: string; name_en: string | null }>>("/api/suppliers?page_size=100");
  const { data: approvals, error: approvalError, mutate: retryApprovals } = useApi<{ pending_approvals: PendingApproval[] }>("/api/exceptions?page_size=1", { refreshInterval: 30_000 });
  const update = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }, [params, pathname, router]);
  const onSearch = useCallback((value: string) => update("q", value), [update]);
  const metrics = [
    { label: t.review.needsReview, value: summary?.needs_review, icon: Layers, tone: "bg-sunken text-ink-3" },
    { label: t.review.critical, value: summary?.by_level.critical, icon: AlertTriangle, tone: "bg-danger-soft text-danger" },
    { label: t.review.valueUnderReview, value: summary && money(summary.value_under_review, summary.currency), icon: Wallet, tone: "bg-sunken text-ink-3" },
  ];
  // value_under_review is the base-currency figure; other currencies are never converted or added in
  const otherCurrencies = summary ? (summary.totals_by_currency ?? []).filter((c) => c.currency !== summary.currency).length : 0;
  const health = [
    { label: t.review.overdue, value: summary?.overdue, href: "/exceptions?due=overdue", icon: AlertTriangle, tone: "bg-danger-soft text-danger" },
    { label: t.review.dueSoon, value: summary?.due_soon, href: "/exceptions?due=soon", icon: CalendarClock, tone: "bg-warn-soft text-warn" },
    { label: t.review.readyForApproval, value: summary?.ready_for_approval, href: "/invoices?status=reconciled", icon: CheckCheck, tone: "bg-sunken text-ink-3" },
  ];

  return <div className="min-w-0 space-y-5">
    <header className="command-hero grid min-w-0 items-center gap-5 p-5 sm:p-6 xl:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.65fr)]">
      <div><h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{t.review.queue}</h1><p className="mt-1.5 text-base text-ink-2">{t.review.subtitle}</p></div>
      <dl className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.5fr)]">
        {metrics.map(({ label, value, icon: Icon, tone }, index) => <div key={label} className={cx("command-metric grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2.5 px-3 py-2.5 sm:py-4", index === 2 && "col-span-2 sm:col-span-1")}>
          <span className={cx("row-span-2 grid h-8 w-8 shrink-0 place-items-center rounded-xl sm:h-10 sm:w-10", tone)} aria-hidden><Icon className="h-4 w-4 sm:h-5 sm:w-5" /></span>
          {/* the number reads first visually, but dt stays before dd so the pair is announced correctly */}
          <dt className="col-start-2 row-start-2 min-w-0 text-sm leading-snug text-ink-2">{label}{index === 2 && summary && <> · <bdi>{summary.currency}</bdi>
              {otherCurrencies > 0 && <> · {t.review.plusCurrencies.replace("{n}", String(otherCurrencies))}</>}</>}</dt>
            <dd className="col-start-2 row-start-1 min-w-0 break-words text-lg font-semibold leading-tight text-ink num sm:text-xl">{value === undefined ? "—" : <bdi>{value}</bdi>}</dd>
        </div>)}
      </dl>
    </header>
    <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(14rem,19%)]">
      <Panel className="command-panel min-w-0 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4">
          <div className="flex flex-wrap items-center gap-3">
            {can("exception:decide") && <ReviewNextButton />}
            <span className="inline-flex items-center gap-1.5 text-sm text-ink-2"><ArrowDownWideNarrow className="h-4 w-4" aria-hidden />{t.review.highestFirst}</span>
          </div>
          {data && <span className="text-sm text-ink-2">{t.common.total} <bdi className="ms-1 font-semibold text-ink num">{data.total}</bdi></span>}
        </div>
        <div className="space-y-3 border-b border-line p-4">
          <div className="flex flex-wrap items-center gap-2"><div className="min-w-0 flex-1"><SearchBox value={filters.q} onChange={onSearch} placeholder={t.common.search} /></div>
            <Button className="md:hidden" aria-expanded={showFilters} aria-controls="queue-filters" onClick={() => setShowFilters(!showFilters)}>
              <SlidersHorizontal className="h-4 w-4" aria-hidden />{t.review.filters}{activeFilterCount > 0 && <bdi>{activeFilterCount}</bdi>}
            </Button>
            {(activeFilterCount > 0 || filters.q) && <Button size="sm" variant="ghost" onClick={() => router.replace(pathname, { scroll: false })}>{t.review.clearFilters}</Button>}
          </div>
          <div id="queue-filters" className={cx("grid-cols-2 items-end gap-2 md:grid md:grid-cols-5", showFilters ? "grid" : "hidden")}>
            <Field label={t.review.priority} htmlFor="priority-filter"><Select id="priority-filter" className="w-full" value={filters.level} onChange={(e) => update("level", e.target.value)}><option value="">{t.common.all}</option>{["critical", "high", "normal"].map((v) => <option key={v} value={v}>{t.review[v as "critical" | "high" | "normal"]}</option>)}</Select></Field>
            <Field label={t.review.filterFinding} htmlFor="finding-filter"><Select id="finding-filter" className="w-full" value={filters.type} onChange={(e) => update("type", e.target.value)}><option value="">{t.common.all}</option>{Object.entries(t.finding).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
            <Field label={t.review.filterSupplier} htmlFor="supplier-filter"><Select id="supplier-filter" className="w-full" value={filters.supplier_id} onChange={(e) => update("supplier_id", e.target.value)}><option value="">{t.common.all}</option>{suppliers?.items.map((s) => <option key={s.id} value={s.id}>{locale === "en" && s.name_en ? s.name_en : s.name}</option>)}</Select></Field>
            <Field label={t.review.due} htmlFor="due-filter"><Select id="due-filter" className="w-full" value={filters.due} onChange={(e) => update("due", e.target.value)}><option value="">{t.common.all}</option><option value="overdue">{t.review.overdue}</option><option value="soon">{t.review.dueSoon}</option><option value="later">{t.review.later}</option></Select></Field>
            <Field label={t.common.status} htmlFor="status-filter"><Select id="status-filter" className="w-full" value={filters.status} onChange={(e) => update("status", e.target.value)}><option value="">{t.review.needsReview}</option>{["open", "escalated", "pending_info", "approved", "rejected", "resolved", "draft"].map((v) => <option key={v} value={v}>{label(t.status, v)}</option>)}</Select></Field>
          </div>
        </div>
        {error ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div> : data ? <ReviewQueue items={data.items} /> : <div className="p-4"><Skeleton className="h-64 w-full" /></div>}
        {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={(page) => update("page", String(page))} />}
      </Panel>
      <aside className="command-aside min-w-0 space-y-4">
        <Panel className="command-panel overflow-hidden">
          <PanelHeader title={t.review.health} />
          {summaryError ? <div className="p-3"><ErrorState message={t.common.error} onRetry={() => retrySummary()} retryLabel={t.common.retry} /></div>
            : <ul className="divide-y divide-line">{health.map(({ label, href, value, icon: Icon, tone }) => <li key={href}>
              <Link href={href} className="flex items-center gap-2 px-3 py-3.5 hover:bg-sunken">
                <span className={cx("grid h-8 w-8 shrink-0 place-items-center rounded-xl", tone)}><Icon className="h-4 w-4" aria-hidden /></span>
                <span className="min-w-0 flex-1 text-sm leading-snug"><bdi className="me-1 font-semibold text-ink num">{value ?? "—"}</bdi>{label}</span><ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-3 rtl:rotate-180" aria-hidden />
              </Link>
            </li>)}</ul>}
        </Panel>
        <Panel className="command-panel overflow-hidden">
          <PanelHeader title={t.exceptions.approvals} />
          {approvalError ? <div className="p-3"><ErrorState message={t.common.error} onRetry={() => retryApprovals()} retryLabel={t.common.retry} /></div>
            : approvals?.pending_approvals.length ? <ul className="divide-y divide-line">{approvals.pending_approvals.map((a) => <li key={a.approval_id}>
              <Link href={`/invoices/${a.invoice.id}`} className="block space-y-1 px-4 py-3 hover:bg-sunken">
                <p className="break-words font-medium" dir="auto">{a.supplier_name}</p>
                <p className="flex flex-wrap items-center gap-x-2 text-sm"><bdi className="text-accent">{a.invoice.invoice_number}</bdi><bdi className="font-semibold num">{money(a.invoice.total, a.invoice.currency)}</bdi></p>
                <p className="text-xs text-ink-3">{t.invoice.step} {a.step} · {label(t.roles, a.required_role)}</p>
              </Link>
            </li>)}</ul> : <p className="px-4 py-5 text-sm text-ink-3">{approvals ? t.common.none : t.common.loading}</p>}
        </Panel>
      </aside>
    </div>
  </div>;
}
