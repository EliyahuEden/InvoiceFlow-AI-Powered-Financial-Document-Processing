"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { StatusPill } from "@/components/domain";
import { PurchaseOrderLines } from "@/components/po-lines";
import { PageHeader } from "@/components/shell";
import { ErrorState, KV, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Detail = { id: string; po_number: string; supplier_id: string; supplier_name: string; supplier_name_en: string | null;
  order_date: string; currency: string; status: string; total: string; notes: string | null;
  lines: { id: string; line_no: number; sku: string | null; description: string; quantity: string; unit_price: string; line_total: string; received: string; invoiced: string }[];
  goods_receipts: { id: string; gr_number: string; received_date: string; received_by: string | null; lines: { po_line_id: string; quantity_received: string }[] }[];
  invoices: { id: string; invoice_number: string | null; status: string; total: string | null }[] };

export default function PODetail() {
  const { t, locale } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: p, error, mutate } = useApi<Detail>(`/api/purchase-orders/${id}`);
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!p) return <Skeleton className="h-96 w-full" />;
  return (
    <div className="space-y-5">
      <PageHeader back={{ href: "/purchase-orders", label: t.pos.title }} title={<span className="ltr font-mono">{p.po_number}</span>}
        sub={<Link href={`/suppliers/${p.supplier_id}`} className="hover:text-accent" dir="auto">{locale === "en" && p.supplier_name_en ? p.supplier_name_en : p.supplier_name}</Link>}
        actions={<StatusPill status={p.status} />} />
      <Panel className="p-4">
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          <KV label={t.common.date}>{date(p.order_date, locale)}</KV>
          <KV label={t.invoice.currency}>{p.currency}</KV>
          <KV label={t.common.total}><span className="ltr font-semibold">{money(p.total, p.currency)}</span></KV>
          <KV label={t.pos.receipts}>{p.goods_receipts.length}</KV>
        </dl>
      </Panel>
      <Panel>
        <PanelHeader title={t.pos.lines} />
        <PurchaseOrderLines lines={p.lines} currency={p.currency} />
      </Panel>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel>
          <PanelHeader title={t.pos.receipts} />
          <ul className="divide-y divide-line">
            {p.goods_receipts.length === 0 && <li className="px-4 py-4 text-sm text-warn">{(t.finding as Record<string, string>).MISSING_GOODS_RECEIPT}</li>}
            {p.goods_receipts.map((g) => (
              <li key={g.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                <span className="ltr font-mono">{g.gr_number}</span>
                <span className="text-ink-2" dir="auto">{g.received_by}</span>
                <span className="text-ink-3">{date(g.received_date, locale)}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel>
          <PanelHeader title={t.pos.linkedInvoices} />
          <ul className="divide-y divide-line">
            {p.invoices.map((i) => (
              <li key={i.id}><Link href={`/invoices/${i.id}`} className="flex items-center justify-between px-4 py-2.5 hover:bg-sunken/70">
                <span className="ltr font-mono text-sm">{i.invoice_number}</span><StatusPill status={i.status} />
                <span className="ltr text-sm font-medium">{money(i.total, p.currency)}</span></Link></li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
