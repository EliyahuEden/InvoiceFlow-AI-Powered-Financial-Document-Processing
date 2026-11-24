"use client";

import Link from "next/link";
import { useState } from "react";
import { useSession } from "@/components/session";
import { Button, Field, Input, Panel, PanelHeader } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { InvoiceDetail } from "@/lib/types";

type Action = "void" | "archive" | "restore" | "link_credit";
type Match = { id: string; invoice_number: string | null; status: string; currency: string | null; total: string | null };

export function InvoiceLifecycle({ invoice, onUpdated }: { invoice: InvoiceDetail; onUpdated: () => void }) {
  const { t } = useI18n();
  const { can } = useSession();
  const m = t.invoiceLifecycle;
  const [action, setAction] = useState<Action>();
  const [reason, setReason] = useState("");
  const [search, setSearch] = useState("");
  const [original, setOriginal] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  const base = action === "link_credit" && invoice.supplier_id && search.trim().length >= 2
    ? { q: search.trim(), supplier_id: invoice.supplier_id, page_size: 20 } : null;
  const { data: active } = useApi<{ items: Match[] }>(base ? `/api/invoices${qs(base)}` : null);
  const { data: archived } = useApi<{ items: Match[] }>(base ? `/api/invoices${qs({ ...base, archived: "true" })}` : null);
  const matches = [...(active?.items ?? []), ...(archived?.items ?? [])].filter((row) => row.id !== invoice.id
    && row.currency === invoice.currency && !["processing", "failed", "voided", "credit_note"].includes(row.status));
  const actions: Action[] = [];
  if (invoice.archived_at) actions.push("restore");
  else if (invoice.payment?.paid_on || ["voided", "rejected", "credit_note"].includes(invoice.status)) actions.push("archive");
  else if (!invoice.payment?.scheduled_for && invoice.status !== "processing") {
    actions.push("void");
    if (invoice.supplier_id && invoice.currency && !["approved", "failed"].includes(invoice.status)) actions.push("link_credit");
  }
  const names: Record<Action, string> = { void: m.void, archive: m.archive, restore: m.restore, link_credit: m.linkCredit };
  const canUpdate = can("approval:decide") && actions.length > 0;
  if (!canUpdate && !invoice.archived_at && !invoice.credit_for_invoice_id && !invoice.credit_notes?.length) return null;

  const submit = async () => {
    setBusy(true); setMessage(undefined);
    try {
      await api.post(`/api/invoices/${invoice.id}/lifecycle`, { action, reason, original_invoice_id: original || null });
      setAction(undefined); setReason(""); setSearch(""); setOriginal(""); onUpdated();
    } catch (err) { setMessage(err instanceof ApiError ? err.message : t.common.error); }
    finally { setBusy(false); }
  };
  return <Panel>
    <PanelHeader title={m.title} />
    <div className="space-y-3 p-4">
      {invoice.archived_at && <p>{m.archived}</p>}
      {invoice.credit_for_invoice_id && <Link className="text-accent underline" href={`/invoices/${invoice.credit_for_invoice_id}`}>{m.original}</Link>}
      {!!invoice.credit_notes?.length && <div><p>{m.credits}</p><ul className="space-y-1">
        {invoice.credit_notes.map((note) => <li key={note.id}><Link className="text-accent underline" href={`/invoices/${note.id}`}>
          {note.number || t.status.credit_note} · {money(note.total, invoice.currency)}</Link></li>)}
      </ul></div>}
      {message && <p role="alert" className="text-danger">{message}</p>}
      {canUpdate && !action && <div className="flex flex-wrap gap-2">{actions.map((kind) =>
        <Button key={kind} disabled={busy} onClick={() => setAction(kind)}>{names[kind]}</Button>)}</div>}
      {canUpdate && action && <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        {action === "link_credit" && <>
          <Field label={m.searchOriginal} htmlFor="credit-search"><Input id="credit-search" value={search}
            onChange={(e) => { setSearch(e.target.value); setOriginal(""); }} /></Field>
          <Field label={m.original} htmlFor="credit-original"><select id="credit-original" className="w-full rounded-md border border-line bg-surface p-2"
            required value={original} onChange={(e) => setOriginal(e.target.value)}>
            <option value="">{m.chooseOriginal}</option>
            {matches.map((row) => <option value={row.id} key={row.id}>{row.invoice_number || t.common.unknown} · {money(row.total, row.currency)}</option>)}
          </select></Field>
        </>}
        <Field label={m.reason} htmlFor="invoice-lifecycle-reason"><Input id="invoice-lifecycle-reason" required maxLength={1000}
          value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex gap-2"><Button type="submit" variant="primary" loading={busy}>{names[action]}</Button>
          <Button type="button" disabled={busy} onClick={() => { setAction(undefined); setReason(""); setMessage(undefined); }}>{t.common.cancel}</Button></div>
      </form>}
    </div>
  </Panel>;
}
