"use client";

import { money, num, unitPrice } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { cx, Table, Td, Th } from "./ui";

type POLine = {
  id: string; line_no: number; sku: string | null; description: string;
  quantity: string; received: string; invoiced: string; unit_price: string; line_total: string;
};

export type Receipt = { id: string; gr_number: string; received_date: string; received_by: string | null;
  lines: { po_line_id: string; quantity_received: string }[] };

export function PurchaseOrderLines({ lines, currency, receipts = [] }: { lines: POLine[]; currency: string; receipts?: Receipt[] }) {
  const { t } = useI18n();
  return (
    <Table>
      <thead><tr>
        <Th>#</Th><Th>{t.invoice.description} / {t.invoice.sku}</Th>
        <Th className="text-end">{t.pos.ordered}</Th><Th className="text-end">{t.recon.received}</Th>
        <Th className="text-end">{t.pos.invoiced}</Th><Th className="text-end">{t.pos.open}</Th>
        <Th className="text-end">{t.invoice.unitPrice}</Th><Th className="text-end">{t.invoice.lineTotal}</Th>
      </tr></thead>
      <tbody>{lines.map((line) => {
        const open = Math.max(0, Number(line.quantity) - Number(line.received));
        const missing = Math.max(0, Number(line.invoiced) - Number(line.received));
        return (
          <tr key={line.id} className={missing > 0 ? "bg-warn-soft/40" : undefined}>
            <Td className="text-ink-3 num">{line.line_no}</Td>
            <Td><span className="font-medium" dir="auto">{line.description}</span>
              {line.sku && <p className="mt-0.5 text-xs text-ink-3"><bdi className="font-mono">{line.sku}</bdi></p>}
              {missing > 0 && <p className="mt-1 text-xs text-warn">
                <bdi>{num(Number(missing.toFixed(4)))} {t.pos.notReceived}</bdi>
                {" · "}<bdi>{money((missing * Number(line.unit_price)).toFixed(2), currency)}</bdi>
              </p>}
            </Td>
            <Td className="text-end num">{num(line.quantity)}</Td>
            <Td className={cx("text-end num", open > 0 && "font-medium text-warn")}><bdi>{num(line.received)}</bdi>
              {Number(line.quantity) > 0 && (
                <span className="ms-auto mt-1.5 block h-1.5 w-20 overflow-hidden rounded-full bg-ink/[.08]" role="img"
                  aria-label={`${t.recon.received} ${num(line.received)} / ${t.pos.ordered} ${num(line.quantity)}`}>
                  <span className={cx("block h-full rounded-full", open > 0 ? "bg-warn" : "bg-ok")}
                    style={{ width: `${Math.min(100, (Number(line.received) / Number(line.quantity)) * 100)}%` }} />
                </span>
              )}
              {receipts.filter((receipt) => receipt.lines.some((r) => r.po_line_id === line.id)).map((receipt) => (
                <a key={receipt.id} href={`#receipt-${receipt.id}`} className="mt-1 block whitespace-nowrap text-xs text-accent underline underline-offset-2">
                  <bdi>{receipt.gr_number}</bdi>
                </a>
              ))}
            </Td>
            <Td className="text-end num">{num(line.invoiced)}</Td>
            <Td className="text-end num"><bdi className={cx("inline-block rounded-lg px-2.5 py-1 font-bold", open > 0 ? "bg-warn-soft text-warn" : "bg-sunken text-ink-2")}>{num(Number(open.toFixed(4)))}</bdi></Td>
            <Td className="text-end"><bdi>{unitPrice(line.unit_price, currency)}</bdi></Td>
            <Td className="text-end font-medium"><bdi>{money(line.line_total, currency)}</bdi></Td>
          </tr>
        );
      })}</tbody>
    </Table>
  );
}
