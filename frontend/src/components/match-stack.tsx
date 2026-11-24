"use client";

import { useI18n } from "@/lib/i18n";
import { num, unitPrice } from "@/lib/format";
import { cx } from "./ui";

type Field = "quantity" | "price";

/**
 * The carbon-copy three-way match: the invoice line, the purchase-order line and the goods receipt as three copies
 * of the same form. When they agree the copies sit in register; when they disagree the copies slip out of register
 * and the field that does not match is marked, with the difference. Every value is shown as text, so the meaning
 * never depends on the offset or the colour.
 */
export function MatchStack({ invoice, order, receivedQty, currency, mismatch, difference, severity }: {
  invoice: { quantity: string | null; unit_price: string | null };
  order: { quantity: string; unit_price: string } | null;
  receivedQty: string | null;
  currency: string | null;
  mismatch: Field | null;
  difference?: string | null;
  severity?: string;
}) {
  const { t } = useI18n();
  const drift = mismatch !== null;
  const tone = severity === "critical" ? "danger" : "warn";
  const copies: { key: "invoice" | "po" | "gr"; label: string; quantity: string | null; price: string | null }[] = [
    { key: "invoice", label: t.review.invoice, quantity: invoice.quantity, price: invoice.unit_price },
    ...(order ? [{ key: "po" as const, label: t.review.purchaseOrder, quantity: order.quantity, price: order.unit_price }] : []),
    ...(receivedQty != null ? [{ key: "gr" as const, label: t.review.received, quantity: receivedQty, price: null }] : []),
  ];
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-[7.5rem_1fr_1fr] gap-3 px-3 text-2xs font-medium text-ink-3">
        <span />
        <span className="text-end">{t.invoice.qty}</span>
        <span className="text-end">{t.invoice.unitPrice}</span>
      </div>
      <ol className="match-stack space-y-1" data-state={drift ? "drift" : "clean"} aria-label={t.review.threeWay}>
        {copies.map((copy, i) => {
          const marks = (field: Field) => drift && mismatch === field && copy.key === "invoice";
          return (
            <li key={copy.key} data-copy={copy.key}
              style={{ transform: drift ? `translateX(calc(var(--drift-dir, 1) * ${i * 6}px))` : undefined }}
              className={cx("grid grid-cols-[7.5rem_1fr_1fr] items-center gap-3 rounded-md border px-3 py-1.5 transition-transform duration-300 [transition-timing-function:var(--motion-ease)]",
                copy.key === "invoice" ? "border-line bg-raised" : copy.key === "po" ? "border-copy-po/25 bg-copy-po/[.07]" : "border-copy-gr/25 bg-copy-gr/[.07]")}>
              <span className="flex items-center gap-2 text-sm text-ink-2">
                <span className={cx("h-2 w-2 shrink-0 rounded-[2px]", copy.key === "invoice" ? "bg-copy-invoice/70" : copy.key === "po" ? "bg-copy-po" : "bg-copy-gr")} aria-hidden />
                {copy.label}
              </span>
              {(["quantity", "price"] as const).map((field) => {
                const value = field === "quantity" ? copy.quantity : copy.price;
                const marked = marks(field);
                return (
                  <span key={field} className={cx("justify-self-end rounded px-1.5 py-0.5 text-end font-mono text-sm num",
                    marked ? (tone === "danger" ? "bg-danger-soft text-danger ring-1 ring-danger/40" : "bg-warn-soft text-warn ring-1 ring-warn/40") : "text-ink")}>
                    <bdi className="ltr">{value == null ? "—" : field === "price" ? unitPrice(value, currency) : num(value)}</bdi>
                  </span>
                );
              })}
            </li>
          );
        })}
      </ol>
      {drift && difference != null && (
        <p className={cx("px-3 text-sm font-medium", tone === "danger" ? "text-danger" : "text-warn")}>
          {t.review.difference}: <bdi className="ltr font-mono num">{mismatch === "price" ? unitPrice(difference, currency) : num(difference)}</bdi>
        </p>
      )}
    </div>
  );
}
