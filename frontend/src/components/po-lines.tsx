"use client";

import { money, num } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { cx, Table, Td, Th } from "./ui";

type POLine = {
  id: string; line_no: number; sku: string | null; description: string;
  quantity: string; received: string; invoiced: string; unit_price: string; line_total: string;
};

export function PurchaseOrderLines({ lines, currency }: { lines: POLine[]; currency: string }) {
  const { t } = useI18n();
  return (
    <Table>
      <thead><tr>
        <Th>#</Th><Th>{t.invoice.sku}</Th><Th>{t.invoice.description}</Th>
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
            <Td><span className="ltr font-mono text-xs">{line.sku ?? "—"}</span></Td>
            <Td><span dir="auto">{line.description}</span>
              {missing > 0 && <p className="mt-1 text-xs text-warn">
                <bdi>{num(Number(missing.toFixed(4)))} {t.pos.notReceived}</bdi>
                {" · "}<bdi>{money((missing * Number(line.unit_price)).toFixed(2), currency)}</bdi>
              </p>}
            </Td>
            <Td className="text-end num">{num(line.quantity)}</Td>
            <Td className={cx("text-end num", open > 0 && "font-medium text-warn")}>{num(line.received)}</Td>
            <Td className="text-end num">{num(line.invoiced)}</Td>
            <Td className={cx("text-end num", open > 0 && "text-warn")}>{num(Number(open.toFixed(4)))}</Td>
            <Td className="text-end"><bdi>{money(line.unit_price, currency)}</bdi></Td>
            <Td className="text-end font-medium"><bdi>{money(line.line_total, currency)}</bdi></Td>
          </tr>
        );
      })}</tbody>
    </Table>
  );
}
