"use client";

import Link from "next/link";
import { useState } from "react";
import { useSession } from "@/components/session";
import { Button, Field, Input, Panel, PanelHeader } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { InvoiceDetail } from "@/lib/types";

export function InvoicePayment({ invoice, onUpdated }: { invoice: InvoiceDetail; onUpdated: () => void }) {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const [action, setAction] = useState<"schedule" | "record_paid">();
  const [valueDate, setValueDate] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const payment = invoice.payment;
  if (!payment || invoice.status !== "approved") return null;
  const m = t.payment;

  const update = async (next: "schedule" | "record_paid" | "clear_schedule") => {
    setBusy(true);
    setError(undefined);
    try {
      await api.post(`/api/invoices/${invoice.id}/payment`, { action: next, date: valueDate || null, reference: reference || null });
      setAction(undefined);
      setReference("");
      onUpdated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
    } finally { setBusy(false); }
  };

  return <Panel>
    <PanelHeader title={m.title} sub={m.hint} />
    <div className="space-y-3 p-4">
      <p>{m[payment.status]}{(payment.paid_on || payment.scheduled_for) && ` · ${date(payment.paid_on ?? payment.scheduled_for, locale)}`}</p>
      {payment.reference && <p>{m.reference} · <bdi>{payment.reference}</bdi></p>}
      {error && <p role="alert" className="text-danger">{error}</p>}
      {can("approval:decide") && payment.status !== "paid" && !action && <div className="flex flex-wrap gap-2">
        <Button disabled={busy} onClick={() => { setValueDate(payment.scheduled_for ?? ""); setAction("schedule"); }}>{m.schedule}</Button>
        <Button disabled={busy} onClick={() => { setValueDate(""); setAction("record_paid"); }}>{m.record}</Button>
        {payment.status === "scheduled" && <Button disabled={busy} onClick={() => void update("clear_schedule")}>{m.clear}</Button>}
      </div>}
      {action && <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void update(action); }}>
        <Field label={m.paymentDate} htmlFor="payment-date"><Input id="payment-date" type="date" required value={valueDate} onChange={(e) => setValueDate(e.target.value)} /></Field>
        {action === "record_paid" && <Field label={m.reference} htmlFor="payment-reference">
          <Input id="payment-reference" required maxLength={120} value={reference} onChange={(e) => setReference(e.target.value)} />
        </Field>}
        <div className="flex gap-2">
          <Button variant="primary" type="submit" loading={busy}>{action === "schedule" ? m.schedule : m.record}</Button>
          <Button type="button" disabled={busy} onClick={() => { setAction(undefined); setReference(""); }}>{t.common.cancel}</Button>
        </div>
      </form>}
    </div>
  </Panel>;
}

type Due = { id: string; number: string | null; date: string; currency: string | null; amount: string | null; overdue: boolean; held: boolean };

export function PaymentReminders() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const { data } = useApi<{ items: Due[] }>(can("approval:decide") ? "/api/payments/due" : null, { refreshInterval: 30_000 });
  if (!data?.items.length) return null;
  const m = t.payment;
  return <Panel>
    <PanelHeader title={m.due} />
    <ul className="divide-y divide-line">
      {data.items.map((entry) => <li key={entry.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
        <Link className="font-medium text-accent" href={`/invoices/${entry.id}`}>{entry.number || t.nav.inbox}</Link>
        <span>{money(entry.amount, entry.currency)} · {date(entry.date, locale)}{entry.held ? ` · ${m.held}` : entry.overdue ? ` · ${m.overdue}` : ""}</span>
      </li>)}
    </ul>
  </Panel>;
}
