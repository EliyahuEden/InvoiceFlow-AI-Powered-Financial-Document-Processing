"use client";

import { Crosshair, FileText, Link2, PackageCheck, ShoppingCart } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { money } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";
import { FIELD_DEFS, fieldEvidence } from "./invoice-fields";
import { cx, Panel, PanelHeader } from "./ui";

const ORDER_FINDINGS = new Set(["PRICE_MISMATCH", "QUANTITY_EXCEEDS_ORDERED", "CURRENCY_MISMATCH", "MISSING_PURCHASE_ORDER", "PO_CLOSED"]);
const RECEIPT_FINDINGS = new Set(["QUANTITY_EXCEEDS_RECEIVED", "MISSING_GOODS_RECEIPT"]);

/**
 * Invoice, purchase order and goods receipt side by side. Amounts are reproducible from the records: the invoice's
 * printed subtotal, the ordered value of the order lines matched to this invoice, and their received quantity at order
 * prices. A card turns red only when reconciliation reported an open finding of its kind; it never compares on its own.
 */
export function SourceCompare({ invoice }: { invoice: InvoiceDetail }) {
  const { t } = useI18n();
  const r = t.review;
  const po = invoice.purchase_order;
  const open = invoice.discrepancies.filter((d) => d.status === "open" && d.severity !== "info").map((d) => d.type);
  const matched = new Set((invoice.reconciliation?.line_matches ?? []).map((m) => m.po_line_id).filter(Boolean));
  const lines = po?.lines.filter((l) => matched.size === 0 || matched.has(l.id)) ?? [];
  const sum = (f: (l: (typeof lines)[number]) => number) => lines.reduce((acc, l) => acc + f(l), 0).toFixed(2);
  const ordered = po ? sum((l) => Number(l.quantity) * Number(l.unit_price)) : null;
  const received = po ? sum((l) => Number(l.received) * Number(l.unit_price)) : null;
  const cards = [
    { key: "invoice", icon: FileText, title: r.invoice, ref: invoice.invoice_number, sub: r.beforeVat,
      amount: money(invoice.subtotal ?? invoice.total, invoice.currency), bad: false, none: false },
    { key: "po", icon: ShoppingCart, title: r.purchaseOrder, ref: po?.po_number ?? invoice.po_reference, sub: r.orderedValue,
      amount: ordered !== null ? money(ordered, po!.currency) : "—", bad: open.some((f) => ORDER_FINDINGS.has(f)), none: ordered === null },
    { key: "gr", icon: PackageCheck, title: r.receiptCard, ref: null, sub: r.receivedValue,
      amount: received !== null ? money(received, po!.currency) : "—", bad: open.some((f) => RECEIPT_FINDINGS.has(f)), none: received === null },
  ];
  return (
    <section aria-label={r.sourceCompare}>
      <h2 className="mb-2.5 flex items-center gap-2 text-lg font-bold text-ink"><Link2 className="h-5 w-5 text-ink-3" aria-hidden />{r.sourceCompare}</h2>
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))] gap-2.5">
        {cards.map(({ key, icon: Icon, title, ref, sub, amount, bad, none }) => { const ok = key === "gr" && !none; return (
          <li key={key} className={cx("rounded-2xl border p-4 shadow-[0_1px_2px_rgb(34_38_92/.05)]",
            bad ? "border-danger/30 bg-danger-soft/70" : ok ? "border-ok/25 bg-ok-soft/50" : "border-line bg-accent-soft/40")}>
            <p className="flex items-center justify-between gap-2 text-md font-bold text-ink">
              {title}<Icon className={cx("h-5 w-5", bad ? "text-danger" : ok ? "text-ok" : "text-accent")} aria-hidden />
            </p>
            <p className="mt-0.5 text-sm leading-snug text-ink-3">{sub}{ref && <><br /><bdi className="font-mono text-xs">{ref}</bdi></>}</p>
            <p className={cx("mt-3 whitespace-nowrap rounded-xl px-3 py-1.5 text-end text-md font-extrabold num", bad ? "bg-surface/80 text-danger" : "bg-surface/80 text-ink")}>
              <bdi className="ltr">{amount}</bdi>
            </p>
            {bad && <p className="mt-2 text-xs font-semibold text-danger">{r.findingOnThis}</p>}
          </li>
        ); })}
      </ul>
    </section>
  );
}

const TRACE_FIELDS = new Set(["total", "subtotal", "tax_total", "invoice_number", "invoice_date", "po_reference"]);

/** Key fields with where they were read: a click highlights the exact spot on the original when coordinates exist,
 *  the page is named when only the page is known, and a missing location is said plainly. */
export function EvidenceTrace({ invoice, active, onShow }: { invoice: InvoiceDetail; active: string | null; onShow: (id: string) => void }) {
  const { t, locale } = useI18n();
  const r = t.review;
  const rows = FIELD_DEFS.filter((f) => TRACE_FIELDS.has(f.key) && invoice[f.key] != null && invoice[f.key] !== "");
  const multiPage = (invoice.document?.page_count ?? 1) > 1;
  return (
    <Panel>
      <PanelHeader title={<span className="inline-flex items-center gap-2"><Crosshair className="h-5 w-5 text-accent" aria-hidden />{r.evidenceTrace}</span>} sub={r.evidenceTraceSub} />
      <ul className="divide-y divide-line">
        {rows.map((f) => {
          const { source, id } = fieldEvidence(invoice, f);
          const raw = invoice[f.key] as string;
          const value = f.kind === "money" ? money(raw, invoice.currency)
            : f.kind === "date" ? new Date(raw + "T00:00:00").toLocaleDateString(locale === "he" ? "he-IL" : "en-GB") : raw;
          const located = !!source?.bbox;
          return (
            <li key={f.key}>
              <button type="button" disabled={!located} onClick={() => onShow(id)} aria-pressed={active === id} data-trace-source={id}
                className={cx("flex w-full items-center justify-between gap-3 px-5 py-3 text-start transition-colors",
                  located ? "hover:bg-accent/[.05]" : "cursor-default", active === id && "bg-accent-soft/60")}>
                <span className="min-w-0">
                  <span className="block text-sm text-ink-2">{f.label(t)}</span>
                  {(!source?.page || multiPage) && <span className="block text-xs text-ink-3">{source?.page ? `${r.page} ${source.page}` : r.noSource}</span>}
                </span>
                {located && <span className="ms-auto inline-flex shrink-0 items-center text-accent" title={r.showOnDocument}>
                  <Crosshair className="h-4 w-4" aria-hidden /><span className="sr-only">{r.showOnDocument}</span></span>}
                <bdi className={cx("ltr rounded-lg px-2 py-1 font-bold num", active === id ? "bg-hl/40 text-ink" : "text-ink")}>{value}</bdi>
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
