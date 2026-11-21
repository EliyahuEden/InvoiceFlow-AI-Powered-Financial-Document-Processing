"use client";

import Link from "next/link";
import { FileSearch, ScanLine } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { findingMessage } from "@/lib/findings";
import { money, num, unitPrice } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";
import { FindingTag } from "./domain";
import { cx, Panel, PanelHeader } from "./ui";

const MONEY_TYPES = new Set(["PRICE_MISMATCH", "LINE_TOTAL_MISMATCH", "SUBTOTAL_MISMATCH", "TOTAL_MISMATCH", "TAX_MISMATCH"]);

export function DiscrepancyTable({ invoice, onSelectLine }: { invoice: InvoiceDetail; onSelectLine?: (id: string) => void }) {
  const { t } = useI18n();
  const findings = invoice.discrepancies.filter((finding) => finding.status === "open");
  const order = invoice.purchase_order;
  const expectedLabels: Record<string, string> = {
    QUANTITY_EXCEEDS_ORDERED: t.pos.ordered,
    QUANTITY_EXCEEDS_RECEIVED: t.review.received,
    PRICE_MISMATCH: t.review.purchaseOrder,
    CURRENCY_MISMATCH: t.review.purchaseOrder,
    CURRENCY_NOT_STATED: t.review.purchaseOrder,
  };
  return <Panel data-testid="discrepancy-table" className="command-panel min-w-0 overflow-hidden">
    <PanelHeader title={t.review.discrepancyTable} sub={<span className="inline-flex flex-wrap items-center gap-x-2">
      {invoice.reconciliation && <span>{(t.recon as Record<string, unknown>)[invoice.reconciliation.mode] as string ?? invoice.reconciliation.mode}</span>}
      {order ? <Link href={`/purchase-orders/${order.id}`} className="text-accent underline underline-offset-4"><bdi>{order.po_number}</bdi></Link> : <bdi>{invoice.po_reference}</bdi>}
    </span>} />
    {findings.length > 0 ? <ol className="divide-y divide-line">
      {findings.map((finding) => {
        const line = invoice.lines.find((item) => item.id === finding.invoice_line_id);
        const poLine = order?.lines.find((item) => item.id === finding.po_line_id);
        const quantityFinding = finding.type === "QUANTITY_EXCEEDS_ORDERED" || finding.type === "QUANTITY_EXCEEDS_RECEIVED";
        const format = (value: string | null) => finding.type === "PRICE_MISMATCH" ? unitPrice(value, invoice.currency)
          : MONEY_TYPES.has(finding.type) ? money(value, invoice.currency) : num(value);
        // Quantity findings compare cumulative billing, which can include older invoices.
        const includeInvoiceQuantity = quantityFinding && line?.quantity != null;
        const showCumulative = !includeInvoiceQuantity || num(line.quantity) !== num(finding.actual);
        const rows = [
          ...(includeInvoiceQuantity ? [{ label: t.review.invoice, value: line.quantity }] : []),
          ...(showCumulative ? [{ label: quantityFinding ? t.review.billedQuantity : t.review.invoice, value: finding.actual }] : []),
          ...(finding.type === "QUANTITY_EXCEEDS_RECEIVED" && poLine ? [{ label: t.pos.ordered, value: poLine.quantity }] : []),
          { label: expectedLabels[finding.type] ?? t.recon.expected, value: finding.expected },
        ];
        return <li key={finding.id} className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><FindingTag type={finding.type} severity={finding.severity} /></div>
          {line && (onSelectLine && line.source?.bbox?.length === 4 ?
            <button type="button" className="inline-flex max-w-full items-center gap-1.5 text-start text-sm font-medium text-accent underline underline-offset-4"
              title={t.review.document} onClick={() => onSelectLine(line.id)}><ScanLine className="h-4 w-4 shrink-0" aria-hidden /><bdi className="break-words">{line.description}</bdi></button>
            : <p className="text-sm font-medium" dir="auto">{line.description}</p>)}
          {(finding.actual != null || finding.expected != null || finding.difference != null || poLine?.received != null) && <dl className="divide-y divide-line overflow-hidden rounded-md border border-line">
            {rows.filter((row) => row.value != null).map((row) => <div key={row.label} className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1 px-3 py-1.5">
              <dt className="min-w-0 text-sm text-ink-2">{row.label}</dt><dd className="break-words font-semibold num"><bdi>{format(row.value)}</bdi></dd>
            </div>)}
            {poLine?.received != null && finding.type !== "QUANTITY_EXCEEDS_RECEIVED" && <div className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-1.5">
              <dt className="text-sm text-ink-2">{t.review.received}</dt><dd className="font-semibold num"><bdi>{num(poLine.received)}</bdi></dd>
            </div>}
            {finding.difference != null && <div className={cx("flex flex-wrap items-baseline justify-between gap-2 px-3 py-2",
              finding.severity === "critical" ? "bg-danger-soft text-danger" : finding.severity === "warning" ? "bg-warn-soft text-warn" : "bg-info-soft text-info")}>
              <dt className="text-sm font-medium">{t.review.difference}</dt><dd className="font-semibold num"><bdi>{format(finding.difference)}</bdi></dd>
            </div>}
          </dl>}
          <p className="text-sm leading-relaxed text-ink-2" dir="auto">{findingMessage(t, finding)}</p>
        </li>;
      })}
    </ol> : <p className="flex items-center gap-2 p-4 text-sm text-ok"><FileSearch className="h-4 w-4" aria-hidden />{t.review.noDiscrepancies}</p>}
  </Panel>;
}
