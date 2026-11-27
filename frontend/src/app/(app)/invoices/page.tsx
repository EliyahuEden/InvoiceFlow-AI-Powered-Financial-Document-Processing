"use client";

import { ArrowDown, ArrowRight, ArrowUp, ArrowUpDown, CheckCircle2, ChevronLeft, FileScan, FileText, Inbox, Loader, Plus, ShieldAlert, TriangleAlert, BadgeCheck } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { StatusPill } from "@/components/domain";
import { EmailSourceBadge } from "@/components/email-inbox";
import { ExportMenu } from "@/components/export-menu";
import { Pager, RowsSkeleton, SearchBox, type Page } from "@/components/list";
import { CountBadge, DetailPanel, DetailSection, FilterBar, FilterSelect, PageHeader, useWideLayout } from "@/components/page-kit";
import { useSession } from "@/components/session";
import { Button, cx, EmptyState, ErrorState, Panel, Skeleton, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { date, dateTime, money, relative } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";
import type { InvoiceDetail } from "@/lib/types";

export type InvoiceRow = {
  id: string; status: string; invoice_number: string | null; supplier_name: string | null; supplier_name_en: string | null;
  supplier_matched: boolean; invoice_date: string | null; currency: string | null; total: string | null;
  po_reference: string | null; language: string | null; extraction_method: string | null; created_at: string;
  filename: string | null; text_method: string | null; open_exceptions: number; warnings: number; security_flag: boolean;
  source?: string; email_sender?: string | null; email_subject?: string | null; // "email" when it arrived at the forwarding address
};

const STATUSES = ["processing", "failed", "needs_review", "exception", "reconciled", "on_hold", "approved", "rejected", "voided", "credit_note"];
// the main path an invoice travels; each stage filters the list to the statuses it covers
const STAGES = [
  { key: "processing,failed", icon: Loader, title: "stageProcessing", sub: "stageProcessingSub" },
  { key: "exception,needs_review", icon: TriangleAlert, title: "stageAttention", sub: "stageAttentionSub" },
  { key: "reconciled", icon: CheckCircle2, title: "stageReady", sub: "stageReadySub" },
  { key: "approved", icon: BadgeCheck, title: "stageApproved", sub: "stageApprovedSub" },
] as const;
const OFF_PATH = ["on_hold", "rejected", "voided", "credit_note"];
const SORTS = ["-created_at", "created_at", "-invoice_date", "invoice_date", "-total", "total", "invoice_number"];

export default function InboxPage() {
  return <Suspense fallback={<Skeleton className="h-80 w-full" />}><InvoiceInbox /></Suspense>;
}

function methodLabel(t: ReturnType<typeof useI18n>["t"], method: string | null): string | null {
  if (!method) return null;
  return method.startsWith("rules+llm") ? t.inbox.methodRulesAi : method === "rule_based" ? t.inbox.methodRules : method;
}

function InvoiceInbox() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const wide = useWideLayout();
  const archived = params.get("archived") === "true";
  const rawStatus = params.get("status") ?? "";
  const status = rawStatus.split(",").every((s) => STATUSES.includes(s)) ? rawStatus : "";
  const supplierId = params.get("supplier_id") ?? "";
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("-created_at");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const setParam = (key: string, value: string) => {
    const updated = new URLSearchParams(params.toString());
    if (value) updated.set(key, value); else updated.delete(key);
    router.replace(updated.size ? `${pathname}?${updated}` : pathname, { scroll: false });
    setPage(1);
  };
  const { data, error, mutate, isLoading } = useApi<Page<InvoiceRow> & { status_counts: Record<string, number> }>(
    `/api/invoices${qs({ status, q, page, page_size: 20, sort, supplier_id: supplierId || undefined, archived: archived ? "true" : undefined })}`,
    { refreshInterval: (d) => (d?.items.some((i) => i.status === "processing") ? 3000 : 0) },
  );
  const { data: suppliers } = useApi<Page<{ id: string; name: string; name_en: string | null }>>("/api/suppliers?page_size=100");
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  const counts = data?.status_counts ?? {};
  const count = (key: string) => key.split(",").reduce((a, s) => a + (counts[s] ?? 0), 0);
  const totalAll = Object.values(counts).reduce((a, b) => a + b, 0);
  const selected = data?.items.find((i) => i.id === selectedId) ?? data?.items[0] ?? null;
  const supplierOf = (r: InvoiceRow) => (locale === "en" && r.supplier_name_en ? r.supplier_name_en : r.supplier_name);
  const sortLabel: Record<string, string> = {
    "-created_at": `${t.inbox.received}, ${t.inbox.sortNewest}`, created_at: `${t.inbox.received}, ${t.inbox.sortOldest}`,
    "-invoice_date": `${t.common.date}, ${t.inbox.sortNewest}`, invoice_date: `${t.common.date}, ${t.inbox.sortOldest}`,
    "-total": `${t.common.total}, ${t.inbox.sortHigh}`, total: `${t.common.total}, ${t.inbox.sortLow}`, invoice_number: t.inbox.number,
  };

  const sortHeading = (key: string, text: string, end = false) => {
    const active = sort.replace(/^-/, "") === key;
    const Icon = active ? (sort.startsWith("-") ? ArrowDown : ArrowUp) : ArrowUpDown;
    return <Th className={end ? "text-end" : ""} aria-sort={active ? (sort.startsWith("-") ? "descending" : "ascending") : undefined}>
      <button type="button" className="inline-flex items-center gap-1 rounded px-0.5 py-1 hover:text-ink"
        onClick={() => { setSort(sort === key ? `-${key}` : key); setPage(1); }}>{text}<Icon aria-hidden className="h-3 w-3" /></button>
    </Th>;
  };

  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={archived ? t.inbox.archivedNote : t.inbox.title} sub={t.inbox.subtitle}
        actions={<>
          <ExportMenu filters={{ status, q, sort, archived: archived ? "true" : undefined }} />
          <Button onClick={() => {
            const updated = new URLSearchParams(params.toString());
            updated.delete("status");
            if (archived) updated.delete("archived"); else updated.set("archived", "true");
            router.replace(updated.size ? `${pathname}?${updated}` : pathname, { scroll: false });
            setPage(1);
          }}>{archived ? t.invoiceLifecycle.activeList : t.invoiceLifecycle.archiveList}</Button>
          {can("invoice:upload") && <Button asChild variant="primary"><Link href="/invoices/upload"><Plus className="h-4 w-4" aria-hidden />{t.inbox.upload}</Link></Button>}
        </>} />

      {/* the lifecycle: where every invoice is right now; a stage filters the list */}
      <section aria-label={t.inbox.stagesTitle} className="command-panel p-2">
        <ol className="grid gap-1 sm:grid-cols-2 xl:grid-cols-4">
          {STAGES.map((s, i) => {
            const active = status === s.key;
            const n = count(s.key);
            const failed = s.key.startsWith("processing") ? counts.failed ?? 0 : 0;
            const tone = s.key.startsWith("exception") && n > 0 ? "bg-warn-soft text-warn" : s.key === "approved" && n > 0 ? "bg-ok-soft text-ok" : s.key === "reconciled" && n > 0 ? "bg-accent-soft text-accent" : "bg-sunken text-ink-3";
            return <li key={s.key} className="relative flex min-w-0">
              <button type="button" aria-pressed={active} onClick={() => setParam("status", active ? "" : s.key)}
                className={cx("flex w-full min-w-0 items-center gap-3 self-stretch rounded-[14px] px-3.5 py-3 text-start transition-colors hover:bg-sunken", active && "bg-accent-soft/60 hover:bg-accent-soft/80")}>
                <span className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", tone)} aria-hidden><s.icon className="h-[18px] w-[18px]" /></span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2"><span className="truncate text-sm font-bold text-ink">{t.inbox[s.title]}</span></span>
                  <span className="line-clamp-2 block text-xs leading-snug text-ink-3">{t.inbox[s.sub]}</span>
                </span>
                <span className="text-end">
                  <bdi className="block text-2xl font-extrabold leading-none text-ink num">{data ? n : "—"}</bdi>
                  {failed > 0 && <span className="mt-1 block whitespace-nowrap text-xs font-semibold text-danger">{t.inbox.failedN.replace("{n}", String(failed))}</span>}
                </span>
              </button>
              {i < STAGES.length - 1 && <ChevronLeft aria-hidden className="absolute -end-2.5 top-1/2 z-[1] hidden h-4 w-4 -translate-y-1/2 text-line-strong ltr:rotate-180 xl:block" />}
            </li>;
          })}
        </ol>
        {OFF_PATH.some((s) => counts[s]) && <p className="flex flex-wrap items-center gap-2 border-t border-line px-3.5 pb-1.5 pt-2.5 text-xs text-ink-3">
          {t.inbox.offPath}:
          {OFF_PATH.filter((s) => counts[s]).map((s) => <button key={s} type="button" aria-pressed={status === s} onClick={() => setParam("status", status === s ? "" : s)}
            className={cx("inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 font-semibold text-ink-2 hover:bg-sunken", status === s && "border-accent/40 bg-accent-soft/60")}>
            {label(t.status, s)} <bdi className="num">{counts[s]}</bdi></button>)}
        </p>}
      </section>

      <div className="grid min-w-0 items-start gap-4 min-[1440px]:grid-cols-[minmax(0,1fr)_21rem] 2xl:grid-cols-[minmax(0,1fr)_24rem]">
        <Panel className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-4">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{t.overview.invoices}{data && <CountBadge>{data.total}</CountBadge>}</h2>
            <FilterSelect label={t.inbox.sortBy} value={sort} onChange={(v) => { setSort(v || "-created_at"); setPage(1); }}>
              {SORTS.map((s) => <option key={s} value={s}>{sortLabel[s]}</option>)}
            </FilterSelect>
          </div>
          <FilterBar className="border-b border-line px-5 pb-4" active={[status, supplierId].filter(Boolean).length}
            onClear={status || supplierId || q ? () => { setQ(""); router.replace(archived ? `${pathname}?archived=true` : pathname, { scroll: false }); setPage(1); } : undefined}
            search={<SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.inbox.number}, ${t.common.supplier}, ${t.inbox.po}`} />}>
            <FilterSelect label={t.common.status} value={status} onChange={(v) => setParam("status", v)}>
              <option value="">{t.inbox.filterAll}{data ? ` (${totalAll})` : ""}</option>
              {STAGES.map((s) => <option key={s.key} value={s.key}>{t.inbox[s.title]}{data ? ` (${count(s.key)})` : ""}</option>)}
              {STATUSES.filter((s) => !STAGES.some((g) => g.key === s)).map((s) => <option key={s} value={s}>{label(t.status, s)}{data ? ` (${counts[s] ?? 0})` : ""}</option>)}
            </FilterSelect>
            <FilterSelect label={t.common.supplier} value={supplierId} onChange={(v) => setParam("supplier_id", v)}>
              <option value="">{t.common.all}</option>
              {suppliers?.items.map((s) => <option key={s.id} value={s.id}>{locale === "en" && s.name_en ? s.name_en : s.name}</option>)}
            </FilterSelect>
          </FilterBar>

          {error ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div> : <>
            {/* phones: one card per invoice */}
            <ul className="divide-y divide-line md:hidden">
              {isLoading && !data ? Array.from({ length: 4 }).map((_, i) => <li key={i} className="p-4"><Skeleton className="h-14 w-full" /></li>)
                : data?.items.map((r) => <li key={r.id}>
                  <Link href={`/invoices/${r.id}`} className="flex items-start gap-3 p-4 transition-colors hover:bg-sunken">
                    <DocIcon row={r} />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-2">
                        <bdi className="truncate font-semibold text-ink">{r.invoice_number ?? r.filename ?? "—"}</bdi>
                        <bdi className="shrink-0 font-bold text-ink num ltr">{money(r.total, r.currency)}</bdi>
                      </span>
                      <span className="mt-0.5 block truncate text-sm text-ink-2"><bdi>{supplierOf(r) ?? "—"}</bdi></span>
                      <span className="mt-2 flex flex-wrap items-center gap-2"><StatusPill status={r.status} />
                        <EmailSourceBadge source={r.source} sender={r.email_sender} subject={r.email_subject} />
                        <span className="text-xs text-ink-3">{date(r.invoice_date, locale)}</span></span>
                    </span>
                  </Link>
                </li>)}
            </ul>
            {/* tablets and up: the table; with room for the preview a row selects, otherwise it opens */}
            <div className="hidden md:block"><Table className="inbox-table queue-table">
              <thead><tr>
                {sortHeading("invoice_number", t.inbox.number)}<Th>{t.common.supplier}</Th>{sortHeading("invoice_date", t.common.date)}
                {sortHeading("total", t.common.total, true)}<Th>{t.common.status}</Th>
              </tr></thead>
              <tbody>
                {isLoading && !data ? <RowsSkeleton cols={5} /> : data?.items.map((r) => {
                  const isSelected = wide && selected?.id === r.id;
                  return <tr key={r.id} data-selected={isSelected || undefined} className={cx("cursor-pointer", isSelected && "queue-row-selected")}
                    onClick={(e) => { if ((e.target as HTMLElement).closest("a,button")) return; if (wide) setSelectedId(r.id); else router.push(`/invoices/${r.id}`); }}>
                    <Td>
                      <div className="flex min-w-0 items-center gap-3">
                        {wide ? <button type="button" aria-pressed={isSelected} className="shrink-0 rounded-xl" onClick={() => setSelectedId(r.id)}>
                          <span className="sr-only">{t.inbox.preview}: {r.invoice_number ?? r.filename}</span><DocIcon row={r} /></button> : <DocIcon row={r} />}
                        <div className="min-w-0">
                          <Link href={`/invoices/${r.id}`} className="block max-w-[13rem] truncate font-semibold text-ink underline-offset-4 hover:text-accent hover:underline"><bdi>{r.invoice_number ?? r.filename ?? "—"}</bdi></Link>
                          <span className="flex items-center gap-x-1.5 whitespace-nowrap text-xs text-ink-3">
                            {r.text_method === "ocr" && <FileScan className="h-3 w-3" aria-hidden />}
                            {r.text_method === "ocr" ? t.invoice.ocr : r.text_method === "native" ? t.invoice.nativeText : r.text_method}
                            {r.language && <><span aria-hidden>·</span><bdi className="uppercase">{r.language}</bdi></>}
                            <EmailSourceBadge source={r.source} sender={r.email_sender} subject={r.email_subject} className="ms-1" />
                          </span>
                        </div>
                      </div>
                    </Td>
                    <Td><div className="min-w-[8rem] max-w-[14rem]">
                      <p className={cx("line-clamp-2 break-words leading-snug", r.supplier_matched ? "text-ink" : "text-ink-3")}><bdi>{supplierOf(r) ?? "—"}</bdi></p>
                      {r.po_reference && <bdi className="block font-mono text-xs text-ink-3">{r.po_reference}</bdi>}
                    </div></Td>
                    <Td className="whitespace-nowrap text-sm" title={t.inbox.receivedAgo.replace("{when}", relative(r.created_at, locale))}>
                      <span className="block text-ink-2">{date(r.invoice_date, locale)}</span></Td>
                    <Td className="text-end"><bdi className="whitespace-nowrap font-semibold text-ink num ltr">{money(r.total, r.currency)}</bdi></Td>
                    <Td>
                      <StatusPill status={r.status} />
                      {r.open_exceptions > 0 && <span className="mt-1 block whitespace-nowrap text-xs text-warn">{t.inbox.openExceptionsN.replace("{n}", String(r.open_exceptions))}</span>}
                    </Td>
                  </tr>;
                })}
              </tbody>
            </Table></div>
          </>}
          {data && data.items.length === 0 && <EmptyState icon={<Inbox className="h-8 w-8" />} title={q || status || supplierId ? t.common.noResults : t.inbox.empty}
            action={!q && !status && !supplierId && can("invoice:upload") ? <Button asChild variant="primary"><Link href="/invoices/upload"><Plus className="h-4 w-4" aria-hidden />{t.inbox.upload}</Link></Button> : undefined} />}
          {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
        </Panel>

        {wide && selected && <aside className="min-w-0 min-[1440px]:sticky min-[1440px]:top-20"><InvoicePreview id={selected.id} row={selected} /></aside>}
      </div>
    </div>
  );
}

function DocIcon({ row }: { row: InvoiceRow }) {
  const { t } = useI18n();
  return <span className={cx("grid h-9 w-9 shrink-0 place-items-center rounded-xl", row.security_flag ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent-ink")}>
    {row.security_flag ? <ShieldAlert className="h-4 w-4" aria-label={t.invoice.security} /> : <FileText className="h-4 w-4" aria-hidden />}
  </span>;
}

/** The selected invoice: its first page, the fields read from it, and where they came from. Read-only. */
function InvoicePreview({ id, row }: { id: string; row: InvoiceRow }) {
  const { t, locale } = useI18n();
  const { data: inv, error } = useApi<InvoiceDetail>(`/api/invoices/${id}`);
  const href = `/invoices/${id}`;
  const doc = inv?.document;
  const supplier = inv ? ((locale === "en" && inv.supplier_name_en) || inv.supplier_name || inv.supplier_name_raw) : null;
  const field = (labelText: string, value: React.ReactNode) => <div className="flex items-baseline justify-between gap-3 py-1.5">
    <dt className="shrink-0 text-sm text-ink-3">{labelText}</dt><dd className="min-w-0 truncate text-end text-sm font-medium text-ink">{value ?? "—"}</dd>
  </div>;
  return <DetailPanel title={<bdi>{row.invoice_number ?? row.filename ?? "—"}</bdi>}
    meta={<div className="flex flex-wrap items-center gap-1.5"><StatusPill status={row.status} />
      {row.open_exceptions > 0 && <span className="text-xs font-semibold text-warn">{t.inbox.openExceptionsN.replace("{n}", String(row.open_exceptions))}</span>}</div>}
    footer={<Button variant="secondary" className="w-full" asChild><Link href={href}>{t.inbox.openInvoice}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button>}>
    {error ? <ErrorState message={t.common.error} /> : !inv ? <div className="space-y-3"><Skeleton className="h-56 w-full" /><Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-2/3" /></div> : <>
      {row.security_flag && <p className="flex gap-2 rounded-xl bg-danger-soft px-3 py-2.5 text-sm text-danger"><ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{t.invoice.security}</p>}
      {doc && (doc.page_count ?? 0) > 0
        ? <Link href={href} className="group block overflow-hidden rounded-xl border border-line bg-sunken">
          {/* eslint-disable-next-line @next/next/no-img-element -- an authenticated API image, not a static asset */}
          <img src={`/api/documents/${doc.id}/pages/1/image?width=640`} alt={`${t.inbox.preview}: ${doc.filename}, ${t.inbox.pages} 1/${doc.page_count}`}
            className="mx-auto h-64 w-full object-contain object-top transition-transform duration-300 group-hover:scale-[1.015]" />
        </Link>
        : <p className="rounded-xl bg-sunken px-3 py-6 text-center text-sm text-ink-3">{t.inbox.noPreview}</p>}
      <DetailSection title={t.invoice.fields}>
        <dl className="divide-y divide-line">
          {field(t.common.supplier, supplier && <bdi>{supplier}</bdi>)}
          {field(t.invoice.invoiceNumber, inv.invoice_number && <bdi className="font-mono text-xs">{inv.invoice_number}</bdi>)}
          {field(t.invoice.invoiceDate, inv.invoice_date && date(inv.invoice_date, locale))}
          {inv.due_date && field(t.invoice.dueDate, date(inv.due_date, locale))}
          {field(t.invoice.total, inv.total && <bdi className="num ltr">{money(inv.total, inv.currency)}</bdi>)}
          {inv.tax_total && field(t.invoice.tax, <bdi className="num ltr">{money(inv.tax_total, inv.currency)}</bdi>)}
          {field(t.invoice.poReference, inv.purchase_order
            ? <Link href={`/purchase-orders/${inv.purchase_order.id}`} className="font-mono text-xs text-accent hover:underline"><bdi>{inv.purchase_order.po_number}</bdi></Link>
            : inv.po_reference && <bdi className="font-mono text-xs">{inv.po_reference}</bdi>)}
          {inv.allocation_number && field(t.invoice.allocationNumber, <bdi className="font-mono text-xs">{inv.allocation_number}</bdi>)}
        </dl>
      </DetailSection>
      <DetailSection title={t.inbox.source}>
        <dl className="divide-y divide-line">
          {doc && field(t.inbox.file, <bdi className="text-xs">{doc.filename}</bdi>)}
          {row.source === "email" && field(t.emailInbox.sentBy, <bdi dir="ltr" className="text-xs">{row.email_sender || "—"}</bdi>)}
          {row.source === "email" && row.email_subject && field(t.emailInbox.subjectLabel, <bdi className="text-xs">{row.email_subject}</bdi>)}
          {field(t.inbox.processingCol, [doc?.text_method === "ocr" ? t.invoice.ocr : doc?.text_method === "native" ? t.invoice.nativeText : doc?.text_method, inv.language?.toUpperCase()].filter(Boolean).join(" · ") || null)}
          {field(t.inbox.extraction, methodLabel(t, inv.extraction_method))}
          {doc?.page_count ? field(t.inbox.pages, <bdi className="num">{doc.page_count}</bdi>) : null}
          {field(t.inbox.received, dateTime(inv.created_at, locale))}
        </dl>
      </DetailSection>
    </>}
  </DetailPanel>;
}
