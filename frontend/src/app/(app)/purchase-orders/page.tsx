"use client";

import { ArrowRight, CheckCircle2, ClipboardList, FileText, Layers, PackageCheck, ShoppingCart, Timer } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { StatusPill } from "@/components/domain";
import { ImportDialog } from "@/components/import-dialog";
import { Pager, RowsSkeleton, SearchBox, type Page } from "@/components/list";
import { CountBadge, DetailPanel, DetailSection, FilterBar, PageHeader, Segments, useWideLayout } from "@/components/page-kit";
import { useSession } from "@/components/session";
import { Button, cx, EmptyState, ErrorState, Panel, Skeleton, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

type PO = { id: string; po_number: string; supplier_name: string; supplier_name_en: string | null; order_date: string; currency: string;
  status: string; line_count: number; total: string;
  lines_received: number; lines_partial: number; lines_over_received: number; received_value: string };
type PODetail = PO & { notes: string | null;
  lines: { id: string; line_no: number; sku: string | null; description: string; unit: string | null; quantity: string; unit_price: string;
    line_total: string; received: string; invoiced: string }[];
  goods_receipts: { id: string; gr_number: string; received_date: string; received_by: string | null; lines: { po_line_id: string; quantity_received: string }[] }[];
  invoices: { id: string; invoice_number: string | null; status: string; total: string | null; currency: string | null }[] };

const SEGMENTS = ["", "open", "partially_received", "received", "closed", "cancelled"] as const;
type Segment = (typeof SEGMENTS)[number];
const SEG_ICON = { "": Layers, open: ClipboardList, partially_received: Timer, received: CheckCircle2, closed: PackageCheck, cancelled: ClipboardList } as const;
const SEG_TONE = { "": "neutral", open: "accent", partially_received: "warn", received: "ok", closed: "neutral", cancelled: "neutral" } as const;

/** Received progress, from the goods receipts: whole lines received, at order prices. Never inferred from the status. */
function Progress({ po, compact = false }: { po: PO; compact?: boolean }) {
  const { t } = useI18n();
  const total = Number(po.total) || 0;
  const share = total > 0 ? Math.min(1, Number(po.received_value) / total) : 0;
  const complete = po.line_count > 0 && po.lines_received === po.line_count;
  const started = po.lines_received + po.lines_partial > 0;
  return <div className={cx("min-w-0", compact ? "w-full" : "w-[9.5rem]")}>
    <p className="text-sm text-ink"><bdi className="num">{t.pos.linesReceived.replace("{full}", String(po.lines_received)).replace("{n}", String(po.line_count))}</bdi></p>
    <div aria-hidden className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sunken">
      <div className={cx("h-full rounded-full", complete ? "bg-ok" : started ? "bg-warn" : "bg-transparent")} style={{ width: `${Math.round(share * 100)}%` }} />
    </div>
    {po.lines_partial > 0 && <p className="mt-1 text-xs font-semibold text-warn">{t.pos.linesPartial.replace("{n}", String(po.lines_partial))}</p>}
    {po.lines_over_received > 0 && <p className="mt-1 text-xs font-semibold text-danger">{t.pos.overReceived.replace("{n}", String(po.lines_over_received))}</p>}
  </div>;
}

export default function POsPage() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const { can } = useSession();
  const wide = useWideLayout();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<Segment>("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading, error, mutate } = useApi<Page<PO> & { status_counts?: Record<string, number> }>(`/api/purchase-orders${qs({ q, status, page, page_size: 25 })}`);
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  const counts = data?.status_counts ?? {};
  const all = Object.values(counts).reduce((a, b) => a + b, 0);
  const selected = data?.items.find((p) => p.id === selectedId) ?? data?.items[0] ?? null;
  const supplierOf = (p: PO) => (locale === "en" && p.supplier_name_en ? p.supplier_name_en : p.supplier_name);

  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={t.pos.title} sub={t.pos.subtitle} actions={can("masterdata:write") && <ImportDialog kinds={["purchase-orders", "goods-receipts"]} onDone={() => mutate()} />} />
      <Segments label={t.common.status} value={status} onChange={(v) => { setStatus(v); setPage(1); }}
        options={SEGMENTS.filter((s) => s === "" || ["open", "partially_received", "received"].includes(s) || counts[s] || status === s).map((s) => ({
          value: s, label: s ? label(t.status, s) : t.common.all, count: data ? (s ? counts[s] ?? 0 : all) : undefined, icon: SEG_ICON[s], tone: SEG_TONE[s] }))} />

      <div className="grid min-w-0 items-start gap-4 min-[1440px]:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_27rem]">
        <Panel className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-4">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{status ? label(t.status, status) : t.common.all}{data && <CountBadge>{data.total}</CountBadge>}</h2>
          </div>
          <FilterBar className="border-b border-line px-5 pb-4" search={<SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.pos.searchPh}`} />}
            onClear={q || status ? () => { setQ(""); setStatus(""); setPage(1); } : undefined} />
          {error && <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div>}

          {/* phones: one card per order */}
          <ul className="divide-y divide-line md:hidden">
            {isLoading && !data ? [0, 1, 2].map((i) => <li key={i} className="p-4"><Skeleton className="h-16 w-full" /></li>)
              : data?.items.map((p) => <li key={p.id}><Link href={`/purchase-orders/${p.id}`} className="block space-y-2.5 p-4 transition-colors hover:bg-sunken">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0"><bdi className="font-mono text-sm font-bold text-ink">{p.po_number}</bdi>
                    <p className="truncate text-sm text-ink-2"><bdi>{supplierOf(p)}</bdi></p></div>
                  <bdi className="shrink-0 font-bold text-ink num ltr">{money(p.total, p.currency)}</bdi>
                </div>
                <div className="flex items-end justify-between gap-3"><Progress po={p} compact /><StatusPill status={p.status} /></div>
              </Link></li>)}
          </ul>

          <div className="hidden md:block"><Table className="queue-table">
            <thead><tr><Th>{t.pos.number}</Th><Th>{t.common.supplier}</Th><Th className="text-end">{t.common.total}</Th>
              <Th>{t.pos.orderedReceived}</Th><Th>{t.common.status}</Th></tr></thead>
            <tbody>
              {isLoading && !data ? <RowsSkeleton cols={6} /> : data?.items.map((p) => {
                const isSelected = wide && selected?.id === p.id;
                return <tr key={p.id} data-selected={isSelected || undefined} className={cx("cursor-pointer", isSelected && "queue-row-selected")}
                  onClick={(e) => { if ((e.target as HTMLElement).closest("a,button")) return; if (wide) setSelectedId(p.id); else router.push(`/purchase-orders/${p.id}`); }}>
                  <Td>{wide ? <button type="button" aria-pressed={isSelected} onClick={() => setSelectedId(p.id)} className="whitespace-nowrap text-start font-mono text-sm font-bold text-accent hover:underline"><bdi>{p.po_number}</bdi></button>
                    : <Link href={`/purchase-orders/${p.id}`} className="whitespace-nowrap font-mono text-sm font-bold text-accent hover:underline"><bdi>{p.po_number}</bdi></Link>}
                    <span className="block whitespace-nowrap text-xs text-ink-3">{date(p.order_date, locale)} · {p.line_count === 1 ? t.pos.lines1 : t.pos.linesN.replace("{n}", String(p.line_count))}</span></Td>
                  <Td><p className="line-clamp-2 min-w-[7rem] max-w-[12rem] break-words leading-snug"><bdi>{supplierOf(p)}</bdi></p></Td>
                  <Td className="text-end"><bdi className="whitespace-nowrap font-semibold num ltr">{money(p.total, p.currency)}</bdi></Td>
                  <Td><Progress po={p} /></Td>
                  <Td><StatusPill status={p.status} /></Td>
                </tr>;
              })}
            </tbody>
          </Table></div>
          {data && data.items.length === 0 && <EmptyState icon={<ShoppingCart className="h-8 w-8" />} title={q || status ? t.common.noResults : t.pos.empty} />}
          {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
        </Panel>
        {wide && selected && <aside className="min-w-0 min-[1440px]:sticky min-[1440px]:top-20"><POPanel po={selected} /></aside>}
      </div>
    </div>
  );
}

/** The selected order: each line ordered against received and invoiced, the receipts, and the invoices that bill it. */
function POPanel({ po }: { po: PO }) {
  const { t, locale } = useI18n();
  const { data: d, error } = useApi<PODetail>(`/api/purchase-orders/${po.id}`);
  const supplier = locale === "en" && po.supplier_name_en ? po.supplier_name_en : po.supplier_name;
  return <DetailPanel title={<bdi className="font-mono">{po.po_number}</bdi>}
    meta={<div className="space-y-1.5"><p className="text-sm text-ink-2"><bdi>{supplier}</bdi></p><StatusPill status={po.status} /></div>}
    footer={<Button variant="secondary" className="w-full" asChild><Link href={`/purchase-orders/${po.id}`}>{t.pos.openPo}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button>}>
    <dl className="grid grid-cols-2 gap-3 rounded-xl bg-sunken px-3.5 py-3">
      <div><dt className="text-xs text-ink-3">{t.common.date}</dt><dd className="mt-0.5 text-sm font-semibold text-ink">{date(po.order_date, locale)}</dd></div>
      <div><dt className="text-xs text-ink-3">{t.pos.orderedValue}</dt><dd className="mt-0.5 text-sm font-semibold text-ink"><bdi className="num ltr">{money(po.total, po.currency)}</bdi></dd></div>
      <div className="col-span-2"><dt className="text-xs text-ink-3">{t.pos.receivedValue} <span className="text-ink-3">· {t.pos.atOrderPrices}</span></dt>
        <dd className="mt-1"><Progress po={po} compact /><bdi className="mt-1 block text-sm font-semibold text-ink num ltr">{money(po.received_value, po.currency)}</bdi></dd></div>
    </dl>
    {error ? <ErrorState message={t.common.error} /> : !d ? <div className="space-y-2"><Skeleton className="h-24 w-full" /><Skeleton className="h-12 w-full" /></div> : <>
      <DetailSection title={<>{t.pos.lineItems} <span className="font-normal text-ink-3">· {d.lines.length}</span></>}>
        <div className="overflow-hidden rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-sunken text-xs text-ink-3"><tr>
              <th className="px-3 py-2 text-start font-semibold">{t.pos.lines}</th><th className="px-2 py-2 text-end font-semibold">{t.pos.ordered}</th>
              <th className="px-2 py-2 text-end font-semibold">{t.pos.receivedCol}</th><th className="px-3 py-2 text-end font-semibold">{t.pos.invoiced}</th>
            </tr></thead>
            <tbody className="divide-y divide-line">{d.lines.map((ln) => {
              const ordered = Number(ln.quantity); const received = Number(ln.received);
              const tone = received > ordered ? "text-danger" : received < ordered ? (received > 0 ? "text-warn" : "text-ink-3") : "text-ok";
              return <tr key={ln.id}>
                <td className="px-3 py-2"><p className="line-clamp-2 leading-snug text-ink"><bdi>{ln.description}</bdi></p>
                  {ln.sku && <bdi className="font-mono text-xs text-ink-3">{ln.sku}</bdi>}</td>
                <td className="whitespace-nowrap px-2 py-2 text-end num">{ln.quantity}{ln.unit && <span className="text-xs text-ink-3"> {ln.unit}</span>}</td>
                <td className={cx("whitespace-nowrap px-2 py-2 text-end font-semibold num", tone)}>{ln.received}</td>
                <td className="whitespace-nowrap px-3 py-2 text-end text-ink-2 num">{ln.invoiced}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
      </DetailSection>
      <DetailSection title={<>{t.pos.receipts} <span className="font-normal text-ink-3">· {d.goods_receipts.length}</span></>}>
        {d.goods_receipts.length === 0 ? <p className="text-sm text-ink-3">{t.pos.noReceipts}</p>
          : <ul className="divide-y divide-line rounded-xl border border-line">{d.goods_receipts.map((g) => <li key={g.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
            <span className="flex min-w-0 items-center gap-2"><PackageCheck className="h-4 w-4 shrink-0 text-ok" aria-hidden /><bdi className="font-mono text-xs font-semibold text-ink">{g.gr_number}</bdi></span>
            <span className="truncate text-xs text-ink-3">{date(g.received_date, locale)}{g.received_by && <> · <bdi>{g.received_by}</bdi></>}</span>
          </li>)}</ul>}
      </DetailSection>
      <DetailSection title={<>{t.pos.linkedInvoices} <span className="font-normal text-ink-3">· {d.invoices.length}</span></>}>
        {d.invoices.length === 0 ? <p className="text-sm text-ink-3">{t.pos.noInvoices}</p>
          : <ul className="divide-y divide-line rounded-xl border border-line">{d.invoices.map((i) => <li key={i.id}>
            <Link href={`/invoices/${i.id}`} className="flex items-center justify-between gap-2 px-3 py-2 text-sm transition-colors hover:bg-sunken">
              <span className="flex min-w-0 items-center gap-2"><FileText className="h-4 w-4 shrink-0 text-ink-3" aria-hidden /><bdi className="font-mono text-xs font-semibold text-accent">{i.invoice_number ?? "—"}</bdi></span>
              <span className="flex items-center gap-2"><bdi className="text-xs font-semibold num ltr">{money(i.total, i.currency)}</bdi><StatusPill status={i.status} /></span>
            </Link></li>)}</ul>}
      </DetailSection>
    </>}
  </DetailPanel>;
}
