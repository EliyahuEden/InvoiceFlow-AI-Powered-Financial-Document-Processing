"use client";

import Link from "next/link";
import { AlertTriangle, ArrowDownWideNarrow, ArrowRight, FileText, Layers, Wallet } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { AtRisk, DueCell, ReviewQueue } from "@/components/review-queue";
import { ReviewNextButton } from "@/components/review-next";
import { Pager, SearchBox, type Page } from "@/components/list";
import { CountBadge, DetailPanel, DetailSection, FilterBar, FilterSelect, PageHeader, StatTile } from "@/components/page-kit";
import { ActionLabel, FindingTag, PriorityBadge, ReasonText, StatusPill } from "@/components/domain";
import { TransitionLink } from "@/components/transition-link";
import { useSession } from "@/components/session";
import { Button, cx, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
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
  const { data, error, mutate } = useApi<Page<ReviewQueueItem>>(`/api/review/queue${qs(filters)}`, { refreshInterval: 30_000 });
  const { data: summary } = useApi<ReviewSummary>("/api/review/summary", { refreshInterval: 30_000 });
  const { data: suppliers } = useApi<Page<{ id: string; name: string; name_en: string | null }>>("/api/suppliers?page_size=100");
  const { data: approvals, error: approvalError, mutate: retryApprovals } = useApi<{ pending_approvals: PendingApproval[] }>("/api/exceptions?page_size=1", { refreshInterval: 30_000 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // the selection follows the list: a filtered-out case falls back to the top of what is shown
  const selected = data?.items.find((i) => i.exception_id === selectedId) ?? data?.items[0] ?? null;

  const update = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }, [params, pathname, router]);
  const onSearch = useCallback((value: string) => update("q", value), [update]);

  // value_under_review is the base-currency figure; the other currencies are listed as they are, never converted or added
  const otherCurrencies = summary ? (summary.totals_by_currency ?? []).filter((c) => c.currency && c.currency !== summary.currency) : [];
  const n = (v: number | undefined) => (v === undefined ? <Skeleton className="h-7 w-10" /> : <bdi>{v}</bdi>);

  return <div className="min-w-0 space-y-5">
    <PageHeader title={t.review.queue} sub={t.review.subtitle}
      actions={can("exception:decide") && <ReviewNextButton size="lg" />}
      stats={<>
        <StatTile icon={Layers} label={t.review.needsReview} value={n(summary?.needs_review)}
          note={summary && (summary.overdue > 0 || summary.due_soon > 0) && <>{[
            summary.overdue > 0 && <span key="o"><bdi className="num">{summary.overdue}</bdi> {t.review.overdue.toLocaleLowerCase()}</span>,
            summary.due_soon > 0 && <span key="s"><bdi className="num">{summary.due_soon}</bdi> {t.review.dueSoon.toLocaleLowerCase()}</span>,
          ].filter(Boolean).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, " · ", el] : [el]), [])}</>} />
        <StatTile icon={AlertTriangle} tone="danger" active={!!summary?.by_level.critical} label={t.review.critical} value={n(summary?.by_level.critical)}
          href="/exceptions?level=critical" note={summary && summary.by_level.high > 0 && <><bdi className="num">{summary.by_level.high}</bdi> {t.review.high.toLocaleLowerCase()}</>} />
        <StatTile icon={Wallet} className="col-span-2 md:col-span-1" label={t.review.valueUnderReview}
          value={summary ? <bdi className="ltr">{money(summary.value_under_review, summary.currency)}</bdi> : <Skeleton className="h-7 w-28" />}
          note={otherCurrencies.length > 0 && <>{t.review.alsoUnderReview}: {otherCurrencies.map((c, i) =>
            <span key={c.currency}>{i > 0 && " · "}<bdi className="whitespace-nowrap num ltr">{money(c.value_under_review, c.currency)}</bdi></span>)}</>} />
      </>} />

    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-2 min-[1440px]:grid-cols-[minmax(0,1fr)_18rem] 2xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Panel className="min-w-0 lg:col-span-2 min-[1440px]:col-span-1">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-4">
          <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{t.review.needsReview}{data && <CountBadge>{data.total}</CountBadge>}</h2>
          <span className="inline-flex items-center gap-1.5 text-sm text-ink-3"><ArrowDownWideNarrow className="h-4 w-4" aria-hidden />{t.review.highestFirst}</span>
        </div>
        <FilterBar className="border-b border-line px-5 pb-4" active={activeFilterCount}
          onClear={activeFilterCount > 0 || filters.q ? () => router.replace(pathname, { scroll: false }) : undefined}
          search={<SearchBox value={filters.q} onChange={onSearch} placeholder={t.common.search} />}>
          <FilterSelect label={t.review.priority} value={filters.level} onChange={(v) => update("level", v)}>
            <option value="">{t.common.all}</option>{(["critical", "high", "normal"] as const).map((v) => <option key={v} value={v}>{t.review[v]}</option>)}
          </FilterSelect>
          <FilterSelect label={t.review.filterFinding} value={filters.type} onChange={(v) => update("type", v)}>
            <option value="">{t.common.all}</option>{Object.entries(t.finding).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </FilterSelect>
          <FilterSelect label={t.review.filterSupplier} value={filters.supplier_id} onChange={(v) => update("supplier_id", v)}>
            <option value="">{t.common.all}</option>{suppliers?.items.map((s) => <option key={s.id} value={s.id}>{locale === "en" && s.name_en ? s.name_en : s.name}</option>)}
          </FilterSelect>
          <FilterSelect label={t.review.due} value={filters.due} onChange={(v) => update("due", v)}>
            <option value="">{t.common.all}</option><option value="overdue">{t.review.overdue}</option><option value="soon">{t.review.dueSoon}</option><option value="later">{t.review.later}</option>
          </FilterSelect>
          <FilterSelect label={t.common.status} value={filters.status} onChange={(v) => update("status", v)}>
            <option value="">{t.review.needsReview}</option>{["open", "escalated", "pending_info", "approved", "rejected", "resolved", "draft"].map((v) => <option key={v} value={v}>{label(t.status, v)}</option>)}
          </FilterSelect>
        </FilterBar>
        {error ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div>
          : data ? <ReviewQueue items={data.items} selectedId={selected?.exception_id} onSelect={(item) => setSelectedId(item.exception_id)} />
          : <div className="space-y-3 p-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>}
        {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={(page) => update("page", String(page))} />}
      </Panel>

      {selected && <aside className="hidden min-w-0 lg:block min-[1440px]:sticky min-[1440px]:top-20 min-[1440px]:col-start-2 min-[1440px]:row-span-2 min-[1440px]:row-start-1">
        <WhyPanel item={selected} first={selected.priority.rank === 1} />
      </aside>}

      <Panel className="min-w-0 min-[1440px]:col-start-1">
        <PanelHeader title={<span className="inline-flex items-center gap-2">{t.exceptions.approvals}{approvals && <CountBadge>{approvals.pending_approvals.length}</CountBadge>}</span>} />
        {approvalError ? <div className="p-3"><ErrorState message={t.common.error} onRetry={() => retryApprovals()} retryLabel={t.common.retry} /></div>
          : approvals?.pending_approvals.length ? <ul className="divide-y divide-line">{approvals.pending_approvals.map((a) => <li key={a.approval_id}>
            <Link href={`/invoices/${a.invoice.id}`} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-0.5 px-5 py-3 transition-colors hover:bg-sunken">
              <span className="min-w-0 break-words font-semibold text-ink"><bdi>{a.supplier_name}</bdi></span>
              <bdi className="whitespace-nowrap font-semibold text-ink num ltr">{money(a.invoice.total, a.invoice.currency)}</bdi>
              <span className="col-span-2 flex flex-wrap items-center gap-x-2 text-xs text-ink-3">
                <bdi className="whitespace-nowrap font-mono text-accent">{a.invoice.invoice_number}</bdi><span aria-hidden>·</span>
                <span>{t.invoice.step} {a.step} · {label(t.roles, a.required_role)}</span>
              </span>
            </Link>
          </li>)}</ul> : <p className="px-5 py-5 text-sm text-ink-3">{approvals ? t.common.none : t.common.loading}</p>}
      </Panel>
    </div>
  </div>;
}

/** Why the selected case is in the queue: the priority reasons and findings the rules recorded, and the rules' next step. */
function WhyPanel({ item, first }: { item: ReviewQueueItem; first: boolean }) {
  const { t, locale } = useI18n();
  const supplier = (locale === "en" && item.supplier_name_en) || item.supplier_name || t.common.unknown;
  const href = `/exceptions/${item.exception_id}`;
  const detail = item.finding_types[0] ? label(t.review.actionDetail, item.finding_types[0], "") : "";
  return <DetailPanel title={first ? t.review.whyFirst : t.review.whySelected}
    meta={<div className="flex flex-wrap items-center gap-1.5"><PriorityBadge level={item.priority.level} />{item.status !== "open" && <StatusPill status={item.status} />}</div>}
    footer={<Button variant="secondary" className="w-full" asChild><TransitionLink href={href}>{ACTIONABLE.includes(item.status) ? t.review.openCase : t.review.viewDecision}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></TransitionLink></Button>}>
    <div className="min-w-0">
      <p className="break-words text-md font-bold leading-snug text-ink"><bdi>{supplier}</bdi></p>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-sm text-ink-3">
        <span className="inline-flex items-center gap-1 font-mono text-xs"><FileText className="h-3 w-3" aria-hidden /><bdi>{item.invoice_number ?? "—"}</bdi></span>
        {item.total && <><span aria-hidden>·</span><bdi className="num ltr">{money(item.total, item.currency)}</bdi></>}
      </p>
    </div>
    <dl className="grid grid-cols-2 gap-3 rounded-xl bg-sunken px-3.5 py-3">
      <div className="min-w-0"><dt className="text-xs text-ink-3">{t.review.atRisk}</dt><dd className="mt-0.5"><AtRisk item={item} align="start" /></dd></div>
      <div className="min-w-0"><dt className="text-xs text-ink-3">{t.review.due}</dt><dd className="mt-0.5"><DueCell item={item} /></dd></div>
    </dl>
    {item.priority.reasons.length > 0 && <DetailSection title={t.review.rulesFound}>
      <ul className="space-y-1.5 text-sm leading-snug text-ink-2">{item.priority.reasons.map((reason, i) =>
        <li key={`${reason.code}-${i}`} className="flex gap-2"><span className={cx("mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full", i === 0 ? "bg-danger" : "bg-line-strong")} aria-hidden />
          <ReasonText reason={reason} currency={item.currency} /></li>)}</ul>
    </DetailSection>}
    {item.finding_types.length > 0 && <DetailSection title={t.review.findingTypes}>
      <div className="flex flex-wrap gap-1.5">{item.finding_types.map((type) => <FindingTag key={type} type={type} />)}</div>
    </DetailSection>}
    {item.proposed_action && <DetailSection title={t.review.suggestedStep}>
      <div className="rounded-xl border border-line px-3.5 py-3 text-sm">
        <p className="font-semibold text-ink"><ActionLabel action={item.proposed_action} /></p>
        {detail && <p className="mt-1 leading-snug text-ink-2">{detail}</p>}
      </div>
    </DetailSection>}
    {item.escalated_by && <p className="text-sm text-ink-3">{t.review.escalatedBy}: <bdi className="text-ink-2">{item.escalated_by}</bdi></p>}
  </DetailPanel>;
}

const ACTIONABLE = ["open", "escalated", "pending_info", "draft"];
