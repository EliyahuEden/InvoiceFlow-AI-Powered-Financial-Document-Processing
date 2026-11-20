"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback } from "react";
import { ReviewQueue } from "@/components/review-queue";
import { ReviewNextButton } from "@/components/review-next";
import { Pager, SearchBox, type Page } from "@/components/list";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, ErrorState, Field, Panel, PanelHeader, Select, Skeleton } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { ReviewQueueItem } from "@/lib/types";

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
  const { data, error, mutate } = useApi<Page<ReviewQueueItem>>(`/api/review/queue${qs(filters)}`);
  const { data: suppliers } = useApi<Page<{ id: string; name: string; name_en: string | null }>>("/api/suppliers?page_size=100");
  const { data: approvals } = useApi<{ pending_approvals: PendingApproval[] }>("/api/exceptions?page_size=1");
  const update = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }, [params, pathname, router]);
  const onSearch = useCallback((value: string) => update("q", value), [update]);
  return <div className="space-y-5">
    <PageHeader title={t.review.queue} sub={t.review.subtitle} actions={can("exception:decide") && <ReviewNextButton />} />
    <Panel>
      <div className="grid grid-cols-1 items-end gap-3 border-b border-line p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <Field label={t.review.priority} htmlFor="priority-filter"><Select id="priority-filter" className="w-full" value={filters.level} onChange={(e) => update("level", e.target.value)}><option value="">{t.common.all}</option>{["critical", "high", "normal"].map((v) => <option key={v} value={v}>{t.review[v as "critical" | "high" | "normal"]}</option>)}</Select></Field>
        <Field label={t.review.filterFinding} htmlFor="finding-filter"><Select id="finding-filter" className="w-full" value={filters.type} onChange={(e) => update("type", e.target.value)}><option value="">{t.common.all}</option>{Object.entries(t.finding).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field>
        <Field label={t.review.filterSupplier} htmlFor="supplier-filter"><Select id="supplier-filter" className="w-full" value={filters.supplier_id} onChange={(e) => update("supplier_id", e.target.value)}><option value="">{t.common.all}</option>{suppliers?.items.map((s) => <option key={s.id} value={s.id}>{locale === "en" && s.name_en ? s.name_en : s.name}</option>)}</Select></Field>
        <Field label={t.review.due} htmlFor="due-filter"><Select id="due-filter" className="w-full" value={filters.due} onChange={(e) => update("due", e.target.value)}><option value="">{t.common.all}</option><option value="overdue">{t.review.overdue}</option><option value="soon">{t.review.dueSoon}</option><option value="later">{t.review.later}</option></Select></Field>
        <Field label={t.common.status} htmlFor="status-filter"><Select id="status-filter" className="w-full" value={filters.status} onChange={(e) => update("status", e.target.value)}><option value="">{t.review.needsReview}</option>{["open", "escalated", "pending_info", "approved", "rejected", "resolved", "draft"].map((v) => <option key={v} value={v}>{(t.status as Record<string, string>)[v] ?? v}</option>)}</Select></Field>
        <Button variant="ghost" onClick={() => router.replace(pathname, { scroll: false })}>{t.review.clearFilters}</Button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-3">
        <SearchBox value={filters.q} onChange={onSearch} placeholder={t.common.search} />
        {data && <span className="text-sm text-ink-2">{t.common.total}: <b className="num">{data.total}</b></span>}
      </div>
      {error ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div> : data ? <ReviewQueue items={data.items} /> : <div className="p-4"><Skeleton className="h-64 w-full" /></div>}
      {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={(page) => update("page", String(page))} />}
    </Panel>
    <Panel>
      <PanelHeader title={t.exceptions.approvals} />
      {approvals?.pending_approvals.length ? <ul className="divide-y divide-line">{approvals.pending_approvals.map((a) => <li key={a.approval_id}>
        <Link href={`/invoices/${a.invoice.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-sunken/70"><span><bdi className="font-medium">{a.invoice.invoice_number}</bdi><span dir="auto" className="ms-3 text-sm text-ink-2">{a.supplier_name}</span><span className="ms-3 text-xs text-ink-3">{t.invoice.step} {a.step} · {(t.roles as Record<string, string>)[a.required_role]}</span></span><bdi className="font-medium num">{money(a.invoice.total, a.invoice.currency)}</bdi></Link>
      </li>)}</ul> : <p className="px-4 py-6 text-sm text-ink-3">{approvals ? t.common.none : t.common.loading}</p>}
    </Panel>
  </div>;
}
