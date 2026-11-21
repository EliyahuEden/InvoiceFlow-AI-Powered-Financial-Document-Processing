"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { StatusPill } from "@/components/domain";
import { PageHeader } from "@/components/shell";
import { KV, ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { useApi } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Detail = { id: string; name: string; name_en: string | null; tax_id: string | null; email: string | null; phone: string | null;
  address: string | null; payment_terms: string | null; default_currency: string; status: string; aliases: string[];
  purchase_orders: { id: string; po_number: string; order_date: string; status: string; total: string; currency: string; line_count: number }[];
  invoices: { id: string; invoice_number: string | null; status: string; total: string | null; currency: string | null; invoice_date: string | null }[] };

export default function SupplierDetail() {
  const { t, locale } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: s, error, mutate } = useApi<Detail>(`/api/suppliers/${id}`);
  if (error) return <ErrorState message={t.common.error} retryLabel={t.common.retry} onRetry={() => mutate()} />;
  if (!s) return <Skeleton className="h-96 w-full" />;
  return (
    <div className="space-y-5">
      <PageHeader back={{ href: "/suppliers", label: t.suppliers.title }} title={<bdi>{locale === "en" && s.name_en ? s.name_en : s.name}</bdi>} sub={s.name_en && <bdi>{locale === "en" ? s.name : s.name_en}</bdi>}
        actions={<StatusPill status={s.status} />} />
      <Panel className="p-5">
        <dl className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          <KV label={t.suppliers.taxId}><span className="ltr font-mono">{s.tax_id ?? "—"}</span></KV>
          <KV label={t.suppliers.terms}><span dir="auto">{s.payment_terms ?? "—"}</span></KV>
          <KV label={t.invoice.currency}>{s.default_currency}</KV>
          <KV label="Email"><span className="ltr break-all">{s.email ?? "—"}</span></KV>
          <KV label="Phone"><span className="ltr">{s.phone ?? "—"}</span></KV>
          <KV label={t.suppliers.aliases}><span dir="auto">{s.aliases.join(", ") || "—"}</span></KV>
        </dl>
      </Panel>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel>
          <PanelHeader title={t.pos.title} />
          <Table>
            <thead><tr><Th>{t.pos.number}</Th><Th>{t.common.date}</Th><Th className="text-end">{t.common.total}</Th><Th>{t.common.status}</Th></tr></thead>
            <tbody>{s.purchase_orders.map((p) => (
              <tr key={p.id} className="hover:bg-sunken/70">
                <Td><Link href={`/purchase-orders/${p.id}`} className="ltr font-mono text-sm font-medium text-accent hover:underline">{p.po_number}</Link></Td>
                <Td className="text-ink-2">{date(p.order_date, locale)}</Td>
                <Td className="text-end"><span className="ltr">{money(p.total, p.currency)}</span></Td>
                <Td><StatusPill status={p.status} /></Td>
              </tr>))}</tbody>
          </Table>
        </Panel>
        <Panel>
          <PanelHeader title={t.suppliers.invoices} />
          <Table>
            <thead><tr><Th>{t.inbox.number}</Th><Th>{t.common.date}</Th><Th className="text-end">{t.common.total}</Th><Th>{t.common.status}</Th></tr></thead>
            <tbody>{s.invoices.map((i) => (
              <tr key={i.id} className="hover:bg-sunken/70">
                <Td><Link href={`/invoices/${i.id}`} className="ltr font-mono text-sm font-medium text-accent hover:underline">{i.invoice_number ?? "—"}</Link></Td>
                <Td className="text-ink-2">{date(i.invoice_date, locale)}</Td>
                <Td className="text-end"><span className="ltr">{money(i.total, i.currency)}</span></Td>
                <Td><StatusPill status={i.status} /></Td>
              </tr>))}</tbody>
          </Table>
        </Panel>
      </div>
    </div>
  );
}
