"use client";

import { useI18n } from "@/lib/i18n";
import { findingMessage } from "@/lib/findings";
import { money, num, unitPrice } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";
import { FindingTag } from "./domain";
import { Panel, PanelHeader, Table, Td, Th } from "./ui";

const MONEY_TYPES = new Set(["PRICE_MISMATCH", "LINE_TOTAL_MISMATCH", "SUBTOTAL_MISMATCH", "TOTAL_MISMATCH", "TAX_MISMATCH"]);

export function DiscrepancyTable({ invoice, onSelectLine }: { invoice: InvoiceDetail; onSelectLine?: (id: string) => void }) {
  const { t } = useI18n();
  const findings = invoice.discrepancies.filter((finding) => finding.status === "open");
  return <Panel data-testid="discrepancy-table">
    <PanelHeader title={t.review.discrepancyTable} sub={invoice.purchase_order?.po_number ?? invoice.po_reference ?? undefined} />
    <Table>
      <thead><tr><Th>{t.invoice.description}</Th><Th>{t.review.invoice}</Th><Th>{t.review.purchaseOrder} / {t.recon.expected}</Th>
        <Th>{t.review.received}</Th><Th>{t.review.difference}</Th></tr></thead>
      <tbody>{findings.map((finding) => {
        const line = invoice.lines.find((item) => item.id === finding.invoice_line_id);
        const poLine = invoice.purchase_order?.lines.find((item) => item.id === finding.po_line_id);
        const format = (value: string | null) => finding.type === "PRICE_MISMATCH" ? unitPrice(value, invoice.currency)
          : MONEY_TYPES.has(finding.type) ? money(value, invoice.currency) : num(value);
        const different = finding.expected !== null && finding.actual !== null && finding.expected !== finding.actual;
        const mark = finding.severity === "critical" ? "text-danger" : "text-warn";
        return <tr key={finding.id}>
          <Td className="min-w-48 max-w-xs"><FindingTag type={finding.type} severity={finding.severity} />
            {line && (onSelectLine && line.source?.bbox?.length === 4 ?
              <button className="mt-1 block text-start text-sm text-accent underline underline-offset-4" dir="auto"
                title={t.review.document} onClick={() => onSelectLine(line.id)}>{line.description}</button>
              : <p className="mt-1 text-sm" dir="auto">{line.description}</p>)}
            <p className="mt-1 text-xs text-ink-2">{findingMessage(t, finding)}</p>
          </Td>
          <Td className="num"><span dir="ltr" className={different ? `line-through ${mark}` : undefined}>{format(finding.actual)}</span></Td>
          <Td className="num"><span dir="ltr" className={different ? `font-semibold ${mark}` : undefined}>{format(finding.expected)}</span></Td>
          <Td className="num"><span dir="ltr">{num(poLine?.received)}</span></Td>
          <Td className="num"><span dir="ltr" className={finding.severity === "critical" ? "text-danger" : "text-warn"}>{format(finding.difference)}</span></Td>
        </tr>;
      })}</tbody>
    </Table>
    {!findings.length && <p className="p-4 text-sm text-ok">{t.review.noDiscrepancies}</p>}
  </Panel>;
}
