"use client";

import { ArrowUpRight, Boxes, ClipboardList, FileText, Truck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { StatusPill } from "@/components/domain";
import { PurchaseOrderLines, type Receipt } from "@/components/po-lines";
import { PageHeader } from "@/components/shell";
import { useSession } from "@/components/session";
import { Button, ErrorState, Field, Input, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { date, money, num } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Detail = { id: string; po_number: string; supplier_id: string; supplier_name: string; supplier_name_en: string | null;
  order_date: string; currency: string; status: string; total: string; notes: string | null;
  lines: { id: string; line_no: number; sku: string | null; description: string; quantity: string; unit_price: string; unit: string | null; line_total: string; received: string; invoiced: string }[];
  goods_receipts: Receipt[];
  invoices: { id: string; invoice_number: string | null; status: string; total: string | null }[] };

function OrderActions({ order, onUpdated }: { order: Detail; onUpdated: () => void }) {
  const { t } = useI18n();
  const { can } = useSession();
  const m = t.orderLifecycle;
  const [action, setAction] = useState<"edit" | "close" | "cancel">();
  const [notes, setNotes] = useState("");
  const [orderDate, setOrderDate] = useState("");
  const [lines, setLines] = useState(order.lines);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  if (!can("masterdata:write") || ["closed", "cancelled"].includes(order.status)) return null;
  const hasHistory = order.goods_receipts.length > 0 || order.invoices.length > 0;
  const startEdit = () => { setNotes(order.notes ?? ""); setOrderDate(order.order_date); setLines(order.lines); setAction("edit"); };
  const submit = async () => {
    const path = `/api/purchase-orders/${order.id}`;
    setBusy(true); setError(undefined);
    try {
      if (action === "edit") {
        await api.patch(path, hasHistory ? { notes } : { notes, order_date: orderDate,
          lines: lines.map(({ sku, description, quantity, unit_price, unit }) => ({ sku, description, quantity, unit_price, unit })) });
      } else {
        await api.post(`${path}/transition`, { action, reason });
      }
      setAction(undefined); setReason(""); onUpdated();
    } catch (e) { setError(e instanceof ApiError ? e.message : t.common.error); }
    finally { setBusy(false); }
  };
  return <Panel>
    <PanelHeader title={m.title} />
    <div className="space-y-3 p-4">
      {error && <p role="alert" className="text-danger">{error}</p>}
      {!action && <div className="flex flex-wrap gap-2">
        <Button onClick={startEdit}>{m.edit}</Button><Button onClick={() => setAction("close")}>{m.close}</Button>
        {!hasHistory && <Button onClick={() => setAction("cancel")}>{m.cancel}</Button>}
      </div>}
      {action && <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        {action === "edit" ? <>
          <Field label={m.notes} htmlFor="po-edit-notes"><Input id="po-edit-notes" value={notes} maxLength={5000} onChange={(e) => setNotes(e.target.value)} /></Field>
          {!hasHistory && <>
            <Field label={m.date} htmlFor="po-edit-date"><Input id="po-edit-date" type="date" required value={orderDate} onChange={(e) => setOrderDate(e.target.value)} /></Field>
            {lines.map((line, index) => <fieldset key={line.id} className="grid gap-2 border-t border-line pt-2 sm:grid-cols-3">
              <legend>{t.pos.lines} {line.line_no}</legend>
              {([ ["description", m.description], ["quantity", m.quantity], ["unit_price", m.unitPrice] ] as const).map(([key, label]) => (
                <Field key={key} label={label} htmlFor={`po-edit-${index}-${key}`}>
                  <Input id={`po-edit-${index}-${key}`} required value={line[key]} inputMode={key === "description" ? "text" : "decimal"}
                    onChange={(event) => setLines(lines.map((item, i) => i === index ? { ...item, [key]: event.target.value } : item))} />
                </Field>
              ))}
            </fieldset>)}
          </>}
        </> : <Field label={m.reason} htmlFor="po-transition-reason">
          <Input id="po-transition-reason" required maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>}
        <div className="flex gap-2"><Button variant="primary" type="submit" loading={busy}>{action === "edit" ? t.common.save : m[action]}</Button>
          <Button type="button" disabled={busy} onClick={() => { setAction(undefined); setReason(""); setError(undefined); }}>{t.common.cancel}</Button></div>
      </form>}
    </div>
  </Panel>;
}

export default function PODetail() {
  const { t, locale } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: p, error, mutate } = useApi<Detail>(`/api/purchase-orders/${id}`);
  // The PO response omits invoice currency. Join only invoice IDs returned by both APIs.
  const { data: invoiceList } = useApi<{ items: { id: string; currency: string | null }[] }>(
    p?.invoices.length ? `/api/invoices${qs({ q: p.po_number, page_size: 100 })}` : null);
  const currencies = new Map(invoiceList?.items.map((i) => [i.id, i.currency]));
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!p) return <Skeleton className="h-96 w-full" />;
  return (
    <div className="space-y-5">
      <PageHeader back={{ href: "/purchase-orders", label: t.pos.title }} title={<>{t.recon.po} <bdi>{p.po_number}</bdi></>}
        sub={<><Link href={`/suppliers/${p.supplier_id}`} className="underline underline-offset-4 hover:text-accent" dir="auto">{locale === "en" && p.supplier_name_en ? p.supplier_name_en : p.supplier_name}</Link> · {date(p.order_date, locale)} · <bdi>{p.currency}</bdi></>}
        actions={<StatusPill status={p.status} />} />
      <OrderActions order={p} onUpdated={() => void mutate()} />
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: t.pos.orderedValue, value: money(p.total, p.currency), icon: ClipboardList },
          { label: t.pos.lines, value: p.lines.length, icon: Boxes },
          { label: t.pos.receipts, value: p.goods_receipts.length, icon: Truck },
          { label: t.pos.linkedInvoices, value: p.invoices.length, icon: FileText },
        ].map(({ label, value, icon: Icon }) => <div key={label} className="command-metric flex min-w-0 flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-3">
          <Icon className="h-5 w-5 shrink-0 text-accent" aria-hidden />
          <div className="flex min-w-0 flex-col-reverse">
            <dt className="text-sm text-ink-2">{label}</dt><dd className="break-words text-xl font-semibold num"><bdi>{value}</bdi></dd>
          </div>
        </div>)}
      </dl>
      <Panel>
        <PanelHeader title={t.pos.orderedReceived} sub={p.notes && <bdi>{p.notes}</bdi>} />
        <PurchaseOrderLines lines={p.lines} currency={p.currency} receipts={p.goods_receipts} />
      </Panel>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel>
          <PanelHeader title={t.pos.receipts} />
          <ul className="divide-y divide-line">
            {p.goods_receipts.length === 0 && <li className="px-4 py-4 text-sm text-warn">{(t.finding as Record<string, string>).MISSING_GOODS_RECEIPT}</li>}
            {p.goods_receipts.map((g) => (
              <li key={g.id} id={`receipt-${g.id}`} className="scroll-mt-24 px-5 py-4 target:bg-accent-soft">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <a href={`#receipt-${g.id}`} className="font-semibold text-accent underline-offset-4 hover:underline"><bdi>{g.gr_number}</bdi></a>
                  <span className="text-sm text-ink-2">{t.pos.receiptDate} · {date(g.received_date, locale)}</span>
                </div>
                {g.received_by && <p className="mt-1 text-sm text-ink-2">{t.pos.receivedBy} · <bdi>{g.received_by}</bdi></p>}
                <ul className="mt-2 divide-y divide-line rounded-md bg-sunken px-3">
                  {g.lines.map((line, index) => {
                    const item = p.lines.find((l) => l.id === line.po_line_id);
                    return <li key={index} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-sm">
                      <bdi>{item?.description ?? line.po_line_id}</bdi>
                      <span className="text-ink-2">{t.recon.received} <bdi className="font-medium num">{num(line.quantity_received)}</bdi></span>
                    </li>;
                  })}
                </ul>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel>
          <PanelHeader title={t.pos.linkedInvoices} />
          {p.invoices.length === 0 ? <p className="p-5 text-sm text-ink-2">{t.pos.noInvoices}</p> :
            <Table><thead><tr><Th>{t.inbox.number}</Th><Th>{t.common.status}</Th><Th className="text-end">{t.common.total}</Th><Th>{t.invoice.currency}</Th></tr></thead>
              <tbody>{p.invoices.map((i) => <tr key={i.id}>
                <Td><Link href={`/invoices/${i.id}`} className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline">
                  <bdi>{i.invoice_number ?? i.id.slice(0, 8)}</bdi><ArrowUpRight className="h-3.5 w-3.5 rtl:-scale-x-100" aria-hidden /></Link></Td>
                <Td><StatusPill status={i.status} /></Td><Td className="text-end num"><bdi>{money(i.total)}</bdi></Td>
                <Td><bdi>{currencies.get(i.id) ?? "—"}</bdi></Td>
              </tr>)}</tbody>
            </Table>}
        </Panel>
      </div>
    </div>
  );
}
