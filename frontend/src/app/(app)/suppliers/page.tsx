"use client";

import { ArrowRight, BookOpenText, Building2, FileText, Plus, ShoppingCart } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { StatusPill } from "@/components/domain";
import { ImportDialog } from "@/components/import-dialog";
import { Pager, RowsSkeleton, SearchBox, type Page } from "@/components/list";
import { CountBadge, DetailPanel, DetailSection, FilterBar, FilterSelect, PageHeader, useWideLayout } from "@/components/page-kit";
import { useSession } from "@/components/session";
import { Button, cx, EmptyState, ErrorState, Field, Input, Panel, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

type Supplier = { id: string; name: string; name_en: string | null; tax_id: string | null; payment_terms: string | null; status: string;
  default_currency: string; invoice_count: number; open_po_count: number; aliases: string[];
  email: string | null; phone: string | null; address: string | null };
type SupplierDetail = Supplier & {
  purchase_orders: { id: string; po_number: string; order_date: string; currency: string; status: string; total: string }[];
  invoices: { id: string; invoice_number: string | null; status: string; total: string | null; currency: string | null; invoice_date: string | null }[] };
type KnowledgeDoc = { id: string; title: string; doc_type: string; supplier_id: string | null; effective_date: string | null; status: string };

function NewSupplier({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ name: "", name_en: "", tax_id: "", payment_terms: "", default_currency: "ILS" });
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/api/suppliers", { ...f, name_en: f.name_en || null, tax_id: f.tax_id || null, payment_terms: f.payment_terms || null });
      toast.success(t.suppliers.new);
      onDone();
    } catch (err) { toast.error(err instanceof ApiError ? String(err.message) : t.common.error); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3 border-b border-line bg-sunken/50 p-4 sm:grid-cols-2 lg:grid-cols-5">
      <Field label={t.common.supplier} htmlFor="supplier-name"><Input id="supplier-name" required dir="auto" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label={t.suppliers.englishName} htmlFor="supplier-name-en"><Input id="supplier-name-en" dir="ltr" value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} /></Field>
      <Field label={t.suppliers.taxId} htmlFor="supplier-tax-id"><Input id="supplier-tax-id" dir="ltr" pattern="\d{8,10}" value={f.tax_id} onChange={(e) => setF({ ...f, tax_id: e.target.value })} /></Field>
      <Field label={t.suppliers.terms} htmlFor="supplier-terms"><Input id="supplier-terms" dir="auto" value={f.payment_terms} onChange={(e) => setF({ ...f, payment_terms: e.target.value })} /></Field>
      <div className="flex items-end"><Button type="submit" variant="primary" loading={busy} className="w-full">{t.common.save}</Button></div>
    </form>
  );
}

/** Two letters from the supplier's own name, as an identifying mark (no logos: none are recorded). */
function Initials({ name, className }: { name: string; className?: string }) {
  const words = name.replace(/["'״׳]/g, "").split(/\s+/).filter(Boolean);
  // a camel-case brand reads by its capitals (BlueWave → BW), everything else by its first two words
  const caps = words[0]?.match(/[A-Z]/g);
  const letters = caps && caps.length >= 2 ? caps.slice(0, 2).join("") : words.slice(0, 2).map((w) => w[0]).join("");
  return <span aria-hidden className={cx("grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-sm font-bold text-accent-ink", className)}>{letters}</span>;
}

export default function SuppliersPage() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const { can } = useSession();
  const wide = useWideLayout();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading, error, mutate } = useApi<Page<Supplier>>(`/api/suppliers${qs({ q, status, page, page_size: 25 })}`);
  // every supplier active: a column repeating "Active" adds nothing; blocked or inactive ones bring it back
  const anyInactive = !!data?.items.some((s) => s.status !== "active");
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  const selected = data?.items.find((s) => s.id === selectedId) ?? data?.items[0] ?? null;
  const names = (s: Supplier) => {
    const primary = locale === "en" && s.name_en ? s.name_en : s.name;
    const secondary = s.name_en ? (locale === "en" ? s.name : s.name_en) : null;
    return { primary, secondary: secondary && secondary !== primary ? secondary : null };
  };

  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={t.suppliers.title} sub={t.suppliers.subtitle} actions={can("masterdata:write") && (<>
        <ImportDialog kinds={["suppliers"]} onDone={() => mutate()} />
        <Button variant="primary" aria-expanded={adding} onClick={() => setAdding((a) => !a)}><Plus className="h-4 w-4" aria-hidden />{t.suppliers.new}</Button></>)} />

      <div className="grid min-w-0 items-start gap-4 min-[1440px]:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_27rem]">
        <Panel className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-4">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{t.suppliers.title}{data && <CountBadge>{data.total}</CountBadge>}</h2>
          </div>
          {adding && <NewSupplier onDone={() => { setAdding(false); mutate(); }} />}
          <FilterBar className="border-b border-line px-5 pb-4" active={status ? 1 : 0}
            onClear={q || status ? () => { setQ(""); setStatus(""); setPage(1); } : undefined}
            search={<SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.suppliers.searchPh}`} />}>
            <FilterSelect label={t.common.status} value={status} onChange={(v) => { setStatus(v); setPage(1); }}>
              <option value="">{t.common.all}</option>{["active", "blocked", "inactive"].map((s) => <option key={s} value={s}>{label(t.status, s)}</option>)}
            </FilterSelect>
          </FilterBar>
          {error && <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div>}

          {/* phones: one card per supplier */}
          <ul className="divide-y divide-line md:hidden">
            {isLoading && !data ? [0, 1, 2].map((i) => <li key={i} className="p-4"><Skeleton className="h-14 w-full" /></li>)
              : data?.items.map((s) => { const n = names(s); return <li key={s.id}>
                <Link href={`/suppliers/${s.id}`} className="flex items-start gap-3 p-4 transition-colors hover:bg-sunken">
                  <Initials name={n.primary} />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold text-ink"><bdi>{n.primary}</bdi></span>
                    {n.secondary && <span className="block text-xs text-ink-3"><bdi>{n.secondary}</bdi></span>}
                    <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
                      {s.tax_id && <bdi className="font-mono">{s.tax_id}</bdi>}
                      <span>{t.suppliers.openPos}: <bdi className="font-semibold text-ink-2 num">{s.open_po_count}</bdi></span>
                      <span>{t.suppliers.invoices}: <bdi className="font-semibold text-ink-2 num">{s.invoice_count}</bdi></span>
                    </span>
                  </span>
                  {s.status !== "active" && <StatusPill status={s.status} />}
                </Link></li>; })}
          </ul>

          <div className="hidden md:block"><Table className="queue-table">
            <thead><tr><Th>{t.common.supplier}</Th><Th>{t.suppliers.taxId}</Th><Th>{t.suppliers.terms}</Th><Th className="text-end">{t.suppliers.openPos}</Th>
              <Th className="text-end">{t.suppliers.invoices}</Th>{anyInactive && <Th>{t.common.status}</Th>}</tr></thead>
            <tbody>
              {isLoading && !data ? <RowsSkeleton cols={6} /> : data?.items.map((s) => {
                const n = names(s);
                const isSelected = wide && selected?.id === s.id;
                return <tr key={s.id} data-selected={isSelected || undefined} className={cx("cursor-pointer", isSelected && "queue-row-selected")}
                  onClick={(e) => { if ((e.target as HTMLElement).closest("a,button")) return; if (wide) setSelectedId(s.id); else router.push(`/suppliers/${s.id}`); }}>
                  <Td><div className="flex min-w-[12rem] items-center gap-3">
                    <Initials name={n.primary} />
                    <div className="min-w-0">
                      {wide ? <button type="button" aria-pressed={isSelected} onClick={() => setSelectedId(s.id)} className="text-start font-semibold text-ink hover:text-accent"><bdi>{n.primary}</bdi></button>
                        : <Link href={`/suppliers/${s.id}`} className="font-semibold text-ink hover:text-accent"><bdi>{n.primary}</bdi></Link>}
                      {n.secondary && <p className="text-xs text-ink-3"><bdi>{n.secondary}</bdi></p>}
                    </div>
                  </div></Td>
                  <Td><bdi className="whitespace-nowrap font-mono text-sm text-ink-2">{s.tax_id ?? "—"}</bdi></Td>
                  <Td className="whitespace-nowrap text-sm text-ink-2"><bdi>{s.payment_terms ?? "—"}</bdi></Td>
                  <Td className="text-end num">{s.open_po_count}</Td>
                  <Td className="text-end num">{s.invoice_count}</Td>
                  {anyInactive && <Td>{s.status !== "active" && <StatusPill status={s.status} />}</Td>}
                </tr>;
              })}
            </tbody>
          </Table></div>
          {data && data.items.length === 0 && <EmptyState icon={<Building2 className="h-8 w-8" />} title={q || status ? t.common.noResults : t.suppliers.empty} />}
          {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
        </Panel>
        {wide && selected && <aside className="min-w-0 min-[1440px]:sticky min-[1440px]:top-20"><SupplierPanel supplier={selected} primary={names(selected).primary} secondary={names(selected).secondary} /></aside>}
      </div>
    </div>
  );
}

/** Supplier 360: the recorded company details (missing ones say so), and its recent invoices, orders and agreements. */
function SupplierPanel({ supplier: s, primary, secondary }: { supplier: Supplier; primary: string; secondary: string | null }) {
  const { t, locale } = useI18n();
  const { data: d, error } = useApi<SupplierDetail>(`/api/suppliers/${s.id}`);
  const { data: kb } = useApi<{ items: KnowledgeDoc[] }>("/api/knowledge/documents");
  const agreements = (kb?.items ?? []).filter((k) => k.supplier_id === s.id);
  const row = (labelText: string, value: React.ReactNode) => <div className="flex items-baseline justify-between gap-3 py-1.5">
    <dt className="shrink-0 text-sm text-ink-3">{labelText}</dt>
    <dd className={cx("min-w-0 break-words text-end text-sm", value ? "font-medium text-ink" : "text-ink-3")}>{value || t.suppliers.notRecorded}</dd>
  </div>;
  const empty = <p className="text-sm text-ink-3">{t.suppliers.noneYet}</p>;
  return <DetailPanel title={<span className="flex items-center gap-3"><Initials name={primary} className="h-10 w-10" /><bdi>{primary}</bdi></span>}
    meta={<div className="space-y-1.5">{secondary && <p className="text-sm text-ink-2"><bdi>{secondary}</bdi></p>}<StatusPill status={s.status} /></div>}
    footer={<Button variant="secondary" className="w-full" asChild><Link href={`/suppliers/${s.id}`}>{t.suppliers.openSupplier}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button>}>
    <DetailSection title={t.suppliers.contact}>
      <dl className="divide-y divide-line">
        {row(t.suppliers.taxId, s.tax_id && <bdi className="font-mono">{s.tax_id}</bdi>)}
        {row(t.suppliers.terms, s.payment_terms && <bdi>{s.payment_terms}</bdi>)}
        {row(t.suppliers.currency, s.default_currency)}
        {row(t.suppliers.email, s.email && <bdi dir="ltr">{s.email}</bdi>)}
        {row(t.suppliers.phone, s.phone && <bdi dir="ltr">{s.phone}</bdi>)}
        {row(t.suppliers.address, s.address && <bdi>{s.address}</bdi>)}
        {s.aliases.length > 0 && row(t.suppliers.aliases, <bdi>{s.aliases.join(" · ")}</bdi>)}
      </dl>
    </DetailSection>
    {error ? <ErrorState message={t.common.error} /> : !d ? <div className="space-y-2"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div> : <>
      <DetailSection title={<>{t.suppliers.recentInvoices} <span className="font-normal text-ink-3">· {s.invoice_count}</span></>}>
        {d.invoices.length === 0 ? empty : <ul className="divide-y divide-line rounded-xl border border-line">{d.invoices.slice(0, 5).map((i) => <li key={i.id}>
          <Link href={`/invoices/${i.id}`} className="flex items-center justify-between gap-2 px-3 py-2 text-sm transition-colors hover:bg-sunken">
            <span className="flex min-w-0 items-center gap-2"><FileText className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
              <span className="min-w-0"><bdi className="block font-mono text-xs font-semibold text-accent">{i.invoice_number ?? "—"}</bdi>
                <span className="block text-xs text-ink-3">{date(i.invoice_date, locale)}</span></span></span>
            <span className="flex items-center gap-2"><bdi className="text-xs font-semibold num ltr">{money(i.total, i.currency)}</bdi><StatusPill status={i.status} /></span>
          </Link></li>)}</ul>}
      </DetailSection>
      <DetailSection title={<>{t.suppliers.purchaseOrders} <span className="font-normal text-ink-3">· {d.purchase_orders.length}</span></>}>
        {d.purchase_orders.length === 0 ? empty : <ul className="divide-y divide-line rounded-xl border border-line">{d.purchase_orders.slice(0, 5).map((po) => <li key={po.id}>
          <Link href={`/purchase-orders/${po.id}`} className="flex items-center justify-between gap-2 px-3 py-2 text-sm transition-colors hover:bg-sunken">
            <span className="flex min-w-0 items-center gap-2"><ShoppingCart className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
              <span className="min-w-0"><bdi className="block font-mono text-xs font-semibold text-accent">{po.po_number}</bdi>
                <span className="block text-xs text-ink-3">{date(po.order_date, locale)}</span></span></span>
            <span className="flex items-center gap-2"><bdi className="text-xs font-semibold num ltr">{money(po.total, po.currency)}</bdi><StatusPill status={po.status} /></span>
          </Link></li>)}</ul>}
      </DetailSection>
      {kb && <DetailSection title={<>{t.suppliers.agreements} <span className="font-normal text-ink-3">· {agreements.length}</span></>}>
        {agreements.length === 0 ? empty : <ul className="divide-y divide-line rounded-xl border border-line">{agreements.map((k) => <li key={k.id}>
          <Link href={`/knowledge/${k.id}`} className="flex items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-sunken">
            <BookOpenText className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />
            <span className="min-w-0 flex-1"><bdi className="line-clamp-2 font-medium text-ink">{k.title}</bdi>
              <span className="block text-xs text-ink-3">{label(t.knowledge.type, k.doc_type)}{k.effective_date && <> · {date(k.effective_date, locale)}</>}</span></span>
          </Link></li>)}</ul>}
      </DetailSection>}
    </>}
  </DetailPanel>;
}
