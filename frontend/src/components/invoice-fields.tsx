"use client";

import { CircleSlash, MapPin, PencilLine } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { money, num } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";
import { cx } from "./ui";

export const FIELD_DEFS: { key: string; src: string; label: (t: ReturnType<typeof useI18n>["t"]) => string; kind?: "money" | "date" | "ltr" }[] = [
  { key: "supplier_name_raw", src: "supplier_name", label: (t) => t.invoice.supplierName },
  { key: "supplier_tax_id_raw", src: "supplier_tax_id", label: (t) => t.invoice.supplierTaxId, kind: "ltr" },
  { key: "invoice_number", src: "invoice_number", label: (t) => t.invoice.invoiceNumber, kind: "ltr" },
  { key: "invoice_date", src: "invoice_date", label: (t) => t.invoice.invoiceDate, kind: "date" },
  { key: "po_reference", src: "po_reference", label: (t) => t.invoice.poReference, kind: "ltr" },
  { key: "payment_terms", src: "payment_terms", label: (t) => t.invoice.paymentTerms },
  { key: "currency", src: "currency", label: (t) => t.invoice.currency, kind: "ltr" },
  { key: "subtotal", src: "subtotal", label: (t) => t.invoice.subtotal, kind: "money" },
  { key: "tax_rate", src: "tax_rate", label: (t) => t.invoice.taxRate, kind: "ltr" },
  { key: "tax_total", src: "tax_amount", label: (t) => t.invoice.tax, kind: "money" },
  { key: "total", src: "total", label: (t) => t.invoice.total, kind: "money" },
];

/** Read-only extracted fields with provenance: hover to locate on the page. */
export function FieldList({ inv, onHover }: { inv: InvoiceDetail; onHover: (id: string | null) => void }) {
  const { t, locale } = useI18n();
  return (
    <dl className="divide-y divide-line">
      {FIELD_DEFS.map((f) => {
        const value = (inv as unknown as Record<string, string | null>)[f.key];
        const src = inv.field_sources?.[f.src] ?? inv.field_sources?.[f.key];
        const corrected = !!src?.corrected_by;
        const missing = value === null || value === undefined || value === "";
        const display = missing ? null : f.kind === "money" ? money(value, inv.currency) : f.kind === "date"
          ? new Date(value + "T00:00:00").toLocaleDateString(locale === "he" ? "he-IL" : "en-GB") : f.key === "tax_rate" ? `${num(value)}%` : value;
        return (
          <div key={f.key} onMouseEnter={() => src?.bbox && onHover(`f:${f.src}`)} onMouseLeave={() => onHover(null)}
            onFocus={() => src?.bbox && onHover(`f:${f.src}`)} onBlur={() => onHover(null)} tabIndex={src?.bbox ? 0 : -1}
            className={cx("grid grid-cols-[9.5rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2", src?.bbox && "cursor-crosshair hover:bg-hl/10")}>
            <dt className="text-sm text-ink-3">{f.label(t)}</dt>
            <dd className={cx("truncate text-base", missing ? "text-ink-3" : "text-ink", f.key === "total" && "font-semibold")}>
              {missing ? <span className="inline-flex items-center gap-1 text-sm"><CircleSlash className="h-3.5 w-3.5" />{t.common.notPrinted}</span> :
                <span className={f.kind === "ltr" || f.kind === "money" ? "ltr" : ""} dir={f.kind ? undefined : "auto"}>{display}</span>}
            </dd>
            <span className="flex items-center gap-1 text-2xs text-ink-3">
              {corrected ? <span className="inline-flex items-center gap-0.5 text-info"><PencilLine className="h-3 w-3" />edited</span> :
                src?.page ? <span className="inline-flex items-center gap-0.5"><MapPin className="h-3 w-3" />{t.common.page_short}{src.page}</span> : null}
            </span>
          </div>
        );
      })}
    </dl>
  );
}

export function fieldHighlights(inv: InvoiceDetail) {
  const hs: { id: string; page: number; bbox: number[]; tone: "field" | "finding" }[] = [];
  for (const [k, s] of Object.entries(inv.field_sources ?? {})) {
    if (s && typeof s === "object" && s.page && s.bbox) hs.push({ id: `f:${k}`, page: s.page, bbox: s.bbox, tone: "field" });
  }
  const flagged = new Set(inv.discrepancies.map((d) => d.evidence?.invoice_line_no).filter(Boolean));
  for (const ln of inv.lines) {
    if (ln.source?.page && ln.source.bbox) {
      hs.push({ id: `l:${ln.line_no}`, page: ln.source.page, bbox: ln.source.bbox, tone: flagged.has(ln.line_no) ? "finding" : "field" });
    }
  }
  return hs;
}
