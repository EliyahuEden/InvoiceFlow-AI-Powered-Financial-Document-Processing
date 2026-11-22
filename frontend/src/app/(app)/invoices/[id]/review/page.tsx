"use client";

import { FileSearch, Link2, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { DocumentViewer } from "@/components/document-viewer";
import { fieldEvidence, fieldHighlights, FIELD_DEFS, SourceTags } from "@/components/invoice-fields";
import { SecurityNotice, WarningList } from "@/components/domain";
import { useSession } from "@/components/session";
import { Button, cx, EmptyState, Field, Input, Panel, PanelHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useInvoice } from "@/lib/use-invoice";
import { useUnsavedWork } from "@/lib/use-unsaved-work";

type LineDraft = { id?: string; line_no: number; sku: string; description: string; quantity: string; unit_price: string; discount: string; line_total: string };

export default function ReviewPage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const { data: inv, mutate } = useInvoice();
  const { data: suppliers } = useApi<{ items: { id: string; name: string; name_en: string | null; tax_id: string | null }[] }>("/api/suppliers?page_size=100");
  const [header, setHeader] = useState<Record<string, string>>({});
  const [lines, setLines] = useState<LineDraft[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [reason, setReason] = useState("");
  const [focus, setFocus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const editable = can("invoice:edit") && inv && !["approved", "rejected", "processing"].includes(inv.status);

  useEffect(() => {
    if (!inv) return;
    const h: Record<string, string> = {};
    for (const f of FIELD_DEFS) h[f.key] = ((inv as unknown as Record<string, string | null>)[f.key] ?? "") as string;
    setHeader(h);
    setLines(inv.lines.map((l) => ({ id: l.id, line_no: l.line_no, sku: l.sku ?? "", description: l.description, quantity: l.quantity ?? "",
      unit_price: l.unit_price ?? "", discount: l.discount ?? "", line_total: l.line_total ?? "" })));
    setSupplierId(inv.supplier_id ?? "");
  }, [inv]);

  const changed = useMemo(() => {
    if (!inv) return {};
    const out: Record<string, string> = {};
    for (const f of FIELD_DEFS) {
      const orig = ((inv as unknown as Record<string, string | null>)[f.key] ?? "") as string;
      if ((header[f.key] ?? "") !== orig) out[f.key] = header[f.key];
    }
    return out;
  }, [header, inv]);
  const linesChanged = useMemo(() => !!inv && JSON.stringify(lines) !== JSON.stringify(inv.lines.map((l) => ({
    id: l.id, line_no: l.line_no, sku: l.sku ?? "", description: l.description, quantity: l.quantity ?? "", unit_price: l.unit_price ?? "",
    discount: l.discount ?? "", line_total: l.line_total ?? "" }))), [lines, inv]);
  const supplierChanged = !!inv && supplierId !== (inv.supplier_id ?? "");
  const dirty = Object.keys(changed).length > 0 || linesChanged || supplierChanged || !!reason.trim();
  useUnsavedWork(!!editable && dirty, t.review.unsavedChanges);

  if (!inv) return <Skeleton className="h-[600px] w-full" />;

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/api/invoices/${inv.id}`, {
        header: changed,
        lines: linesChanged ? lines.map((l) => ({ ...l, sku: l.sku || null, quantity: l.quantity || null, unit_price: l.unit_price || null,
          discount: l.discount || null, line_total: l.line_total || null })) : null,
        supplier_id: supplierChanged && supplierId ? supplierId : null,
        reason: reason || null,
        revision: inv.revision ?? null,
      });
      toast.success(t.invoice.saveCorrections);
      setReason("");
      await mutate();
    } catch (e) {
      toast.error(e instanceof ApiError && e.status === 409 ? t.review.staleRevision
        : e instanceof ApiError ? String(e.message) : t.common.error);
    } finally { setSaving(false); }
  };

  const setLine = (i: number, k: keyof LineDraft, v: string) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));

  return (
    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]">
      {inv.document ? (
        <DocumentViewer className="h-[56svh] min-h-80 lg:sticky lg:top-20 lg:h-[calc(100svh-7rem)]" documentId={inv.document.id}
          pageCount={inv.document.page_count ?? 1} filename={inv.document.filename} highlights={fieldHighlights(inv)} activeId={focus} />
      ) : <Panel><EmptyState icon={<FileSearch className="h-7 w-7" />} title={t.review.noDocument} /></Panel>}
      <div className="min-w-0 space-y-4">
        <SecurityNotice items={(inv.validation_warnings ?? []).filter((w) => w.code === "SUSPICIOUS_INSTRUCTIONS")} />
        <Panel className="command-panel">
          <PanelHeader title={t.invoice.fields} sub={t.invoice.corrections}
            actions={inv.document && <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-1 text-xs font-medium text-accent-ink">
              <Link2 className="h-3.5 w-3.5" aria-hidden />{t.review.document}
            </span>} />
          <div className="divide-y divide-line px-4 sm:px-5">
            {FIELD_DEFS.map((f) => {
              const { source, corrected, id } = fieldEvidence(inv, f);
              const missing = inv.missing_fields.includes(f.key) || inv.missing_fields.includes(f.src);
              const modified = changed[f.key] !== undefined;
              const original = (inv as unknown as Record<string, string | null>)[f.key];
              return (
                <div key={f.key} className={cx("space-y-1.5 py-3", focus === id && "bg-hl/10")}
                  onMouseEnter={() => source?.bbox && setFocus(id)} onMouseLeave={() => setFocus(null)}
                  onFocus={() => source?.bbox && setFocus(id)} onBlur={() => setFocus(null)}>
                  <div className="grid grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] items-center gap-3">
                  <label htmlFor={`f-${f.key}`} className="text-sm font-medium text-ink">{f.label(t)}</label>
                  <Input id={`f-${f.key}`} value={header[f.key] ?? ""} disabled={!editable}
                    dir={f.kind ? "ltr" : "auto"} type={f.kind === "date" ? "date" : "text"} inputMode={f.kind === "money" ? "decimal" : undefined}
                    onChange={(e) => setHeader((h) => ({ ...h, [f.key]: e.target.value }))}
                    className={cx("min-w-0", missing && "border-warn/60", modified && "border-info")} />
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <SourceTags source={source} corrected={corrected} />
                    {missing && <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">{t.invoice.missing}</span>}
                    {modified && <span className="rounded-full bg-info-soft px-2 py-0.5 text-xs font-medium text-info">{t.invoice.unsaved}</span>}
                    {source?.text && !corrected && !modified && <details className="min-w-0 text-xs text-ink-2">
                      <summary className="cursor-pointer rounded hover:text-accent">{t.invoice.sourceLine}</summary><bdi className="block py-1">{source.text}</bdi>
                    </details>}
                  </div>
                  {modified && <p className="text-xs text-ink-2">{t.invoice.recorded} · <bdi>{original || "—"}</bdi></p>}
                  {(corrected || modified) && source?.text && <p className="text-xs text-ink-2">{t.invoice.sourceLine} · <bdi>{source.text}</bdi></p>}
                </div>
              );
            })}
          </div>
          <div className="border-t border-line p-4">
            <Field label={t.invoice.supplierConfirm} htmlFor="supplier">
              <Select id="supplier" value={supplierId} onChange={(e) => setSupplierId(e.target.value)} disabled={!editable} className="w-full">
                <option value="">— {t.common.unknown} —</option>
                {suppliers?.items.map((s) => <option key={s.id} value={s.id}>{locale === "en" && s.name_en ? s.name_en : s.name}{s.tax_id ? ` · ${s.tax_id}` : ""}</option>)}
              </Select>
            </Field>
          </div>
        </Panel>

        <Panel className="command-panel">
          <PanelHeader title={t.invoice.lineItems} actions={editable && (
            <Button size="sm" onClick={() => setLines((ls) => [...ls, { line_no: ls.length + 1, sku: "", description: "", quantity: "", unit_price: "", discount: "", line_total: "" }])}>
              <Plus className="h-4 w-4" />{t.invoice.addLine}
            </Button>
          )} />
          <Table>
            <thead><tr><Th>{t.invoice.sku}</Th><Th>{t.invoice.description}</Th><Th>{t.invoice.qty}</Th><Th>{t.invoice.unitPrice}</Th><Th>{t.invoice.lineTotal}</Th><Th /></tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i} onMouseEnter={() => setFocus(`l:${l.line_no}`)} onMouseLeave={() => setFocus(null)}
                  onFocus={() => setFocus(`l:${l.line_no}`)} onBlur={() => setFocus(null)}>
                  <Td className="min-w-28 px-2"><Input aria-label={`${t.invoice.sku} ${l.line_no}`} dir="ltr" value={l.sku} disabled={!editable} onChange={(e) => setLine(i, "sku", e.target.value)} className="h-8 font-mono text-xs" /></Td>
                  <Td className="min-w-40 px-2"><Input aria-label={`${t.invoice.description} ${l.line_no}`} dir="auto" value={l.description} disabled={!editable} onChange={(e) => setLine(i, "description", e.target.value)} className="h-8" /></Td>
                  <Td className="min-w-20 px-2"><Input aria-label={`${t.invoice.qty} ${l.line_no}`} dir="ltr" inputMode="decimal" value={l.quantity} disabled={!editable} onChange={(e) => setLine(i, "quantity", e.target.value)} className="h-8" /></Td>
                  <Td className="min-w-28 px-2"><Input aria-label={`${t.invoice.unitPrice} ${l.line_no}`} dir="ltr" inputMode="decimal" value={l.unit_price} disabled={!editable} onChange={(e) => setLine(i, "unit_price", e.target.value)} className="h-8" /></Td>
                  <Td className="min-w-28 px-2"><Input aria-label={`${t.invoice.lineTotal} ${l.line_no}`} dir="ltr" inputMode="decimal" value={l.line_total} disabled={!editable} onChange={(e) => setLine(i, "line_total", e.target.value)} className="h-8" /></Td>
                  <Td className="w-10 px-1">{editable && (
                    <Button size="icon" variant="ghost" aria-label={`${t.invoice.removeLine} ${l.line_no}`} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i).map((x, k) => ({ ...x, line_no: k + 1 })))}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>

        {inv.validation_warnings?.some((w) => w.code !== "SUSPICIOUS_INSTRUCTIONS") && <Panel className="command-panel">
          <PanelHeader title={t.invoice.warnings} /><div className="p-4"><WarningList items={inv.validation_warnings.filter((w) => w.code !== "SUSPICIOUS_INSTRUCTIONS")} /></div>
        </Panel>}
        {editable && (
          <Panel className="command-panel flex flex-wrap items-end gap-3 p-4 shadow-pop lg:sticky lg:bottom-4">
            <div className="min-w-[min(14rem,100%)] flex-1">
              <Field label={t.invoice.reason} htmlFor="reason">
                <Input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t.exceptions.notePlaceholder} />
              </Field>
            </div>
            <Button variant="primary" onClick={save} loading={saving} disabled={!dirty}><Save className="h-4 w-4" />{t.invoice.saveCorrections}</Button>
          </Panel>
        )}
      </div>
    </div>
  );
}
