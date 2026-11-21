"use client";

import { CircleCheck, CircleSlash, MapPin, PencilLine } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { money, num } from "@/lib/format";
import type { InvoiceDetail, Source } from "@/lib/types";
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

// The extraction service keys evidence by the printed field, while saved corrections use the record key.
export function fieldEvidence(inv: InvoiceDetail, f: (typeof FIELD_DEFS)[number]) {
  const printed = inv.field_sources?.[f.src];
  const recorded = inv.field_sources?.[f.key];
  const source = printed ?? recorded;
  return { source, corrected: !!(recorded?.corrected_by || printed?.corrected_by), id: `f:${printed ? f.src : f.key}` };
}

export function SourceTags({ source, corrected }: { source?: Source; corrected: boolean }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-xs font-medium">
      {source?.page && <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-accent-ink">
        <MapPin className="h-3 w-3" aria-hidden />{t.common.page} {source.page}
      </span>}
      {corrected ? <span className="inline-flex items-center gap-1 rounded-full bg-info-soft px-2 py-0.5 text-info">
        <PencilLine className="h-3 w-3" aria-hidden />{t.invoice.corrected}
      </span> : source?.verified && <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-2 py-0.5 text-ok">
        <CircleCheck className="h-3 w-3" aria-hidden />{t.ai.verified}
      </span>}
    </span>
  );
}

export function FieldList({ inv, onHover }: { inv: InvoiceDetail; onHover: (id: string | null) => void }) {
  const { t, locale } = useI18n();
  return (
    <dl className="divide-y divide-line px-4 sm:px-5">
      {FIELD_DEFS.map((f) => {
        const value = (inv as unknown as Record<string, string | null>)[f.key];
        const { source, corrected, id } = fieldEvidence(inv, f);
        const missing = value === null || value === undefined || value === "";
        const display = missing ? null : f.kind === "money" ? money(value, inv.currency) : f.kind === "date"
          ? new Date(value + "T00:00:00").toLocaleDateString(locale === "he" ? "he-IL" : "en-GB") : f.key === "tax_rate" ? `${num(value)}%` : value;
        return (
          <div key={f.key} onMouseEnter={() => source?.bbox && onHover(id)} onMouseLeave={() => onHover(null)}
            onFocus={() => source?.bbox && onHover(id)} onBlur={() => onHover(null)} tabIndex={source?.bbox ? 0 : -1}
            className={cx("grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] items-start gap-x-3 gap-y-1.5 py-3", source?.bbox && "cursor-crosshair hover:bg-hl/10 focus-visible:bg-hl/10")}>
            <dt className="text-sm text-ink-2">{f.label(t)}</dt>
            <dd className={cx("min-w-0 break-words text-end text-base", missing ? "text-ink-3" : "font-medium text-ink", f.key === "total" && "font-semibold")}>
              {missing ? <span className="inline-flex items-center gap-1 text-sm"><CircleSlash className="h-3.5 w-3.5" />{t.common.notPrinted}</span> :
                <span className={f.kind === "ltr" || f.kind === "money" ? "ltr" : ""} dir={f.kind ? undefined : "auto"}>{display}</span>}
            </dd>
            {(source?.page || corrected || source?.verified) && <dd className="col-span-2 flex flex-wrap items-center justify-between gap-2">
              <SourceTags source={source} corrected={corrected} />
              {corrected && source?.text && <span className="min-w-0 break-words text-xs text-ink-2">{t.invoice.sourceLine} · <bdi>{source.text}</bdi></span>}
            </dd>}
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
