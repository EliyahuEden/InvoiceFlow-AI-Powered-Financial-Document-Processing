"use client";

import { Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { DocumentViewer } from "@/components/document-viewer";
import { fieldHighlights, FIELD_DEFS } from "@/components/invoice-fields";
import { useSession } from "@/components/session";
import { Button, Field, Input, Panel, PanelHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useInvoice } from "@/lib/use-invoice";

type LineDraft = { line_no: number; sku: string; description: string; quantity: string; unit_price: string; discount: string; line_total: string };

export default function ReviewPage() {
  const { t } = useI18n();
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
    setLines(inv.lines.map((l) => ({ line_no: l.line_no, sku: l.sku ?? "", description: l.description, quantity: l.quantity ?? "",
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
    line_no: l.line_no, sku: l.sku ?? "", description: l.description, quantity: l.quantity ?? "", unit_price: l.unit_price ?? "",
    discount: l.discount ?? "", line_total: l.line_total ?? "" }))), [lines, inv]);
  const supplierChanged = !!inv && supplierId !== (inv.supplier_id ?? "");
  const dirty = Object.keys(changed).length > 0 || linesChanged || supplierChanged;

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
      });
      toast.success(t.invoice.saveCorrections);
      setReason("");
      mutate();
    } catch (e) {
      toast.error(e instanceof ApiError ? String(e.message) : t.common.error);
    } finally { setSaving(false); }
  };

  const setLine = (i: number, k: keyof LineDraft, v: string) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, [k]: v } : l)));

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      {inv.document && (
        <DocumentViewer className="h-[calc(100vh-14rem)] min-h-[560px] xl:sticky xl:top-20" documentId={inv.document.id}
          pageCount={inv.document.page_count ?? 1} filename={inv.document.filename} highlights={fieldHighlights(inv)} activeId={focus} />
      )}
      <div className="space-y-5">
        <Panel>
          <PanelHeader title={t.invoice.tabs.review} sub={t.invoice.corrections} />
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Field label={t.invoice.supplierConfirm} htmlFor="supplier">
                <Select id="supplier" value={supplierId} onChange={(e) => setSupplierId(e.target.value)} disabled={!editable} className="w-full">
                  <option value="">— {t.common.unknown} —</option>
                  {suppliers?.items.map((s) => <option key={s.id} value={s.id}>{s.name}{s.tax_id ? ` · ${s.tax_id}` : ""}</option>)}
                </Select>
              </Field>
            </div>
            {FIELD_DEFS.map((f) => {
              const src = inv.field_sources?.[f.src];
              const missing = inv.missing_fields.includes(f.key) || inv.missing_fields.includes(f.src);
              return (
                <Field key={f.key} label={`${f.label(t)}${changed[f.key] !== undefined ? " •" : ""}`} htmlFor={`f-${f.key}`}
                  hint={src?.text ? `${t.invoice.sourceLine}: ${src.text}` : missing ? t.invoice.missing : undefined}>
                  <Input id={`f-${f.key}`} value={header[f.key] ?? ""} disabled={!editable}
                    dir={f.kind ? "ltr" : "auto"} type={f.kind === "date" ? "date" : "text"} inputMode={f.kind === "money" ? "decimal" : undefined}
                    onFocus={() => setFocus(`f:${f.src}`)} onBlur={() => setFocus(null)}
                    onChange={(e) => setHeader((h) => ({ ...h, [f.key]: e.target.value }))}
                    className={missing ? "border-warn/60 bg-warn-soft/30" : changed[f.key] !== undefined ? "border-info/60" : ""} />
                </Field>
              );
            })}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title={t.invoice.lineItems} actions={editable && (
            <Button size="sm" onClick={() => setLines((ls) => [...ls, { line_no: ls.length + 1, sku: "", description: "", quantity: "", unit_price: "", discount: "", line_total: "" }])}>
              <Plus className="h-4 w-4" />
            </Button>
          )} />
          <Table>
            <thead><tr><Th>{t.invoice.sku}</Th><Th>{t.invoice.description}</Th><Th>{t.invoice.qty}</Th><Th>{t.invoice.unitPrice}</Th><Th>{t.invoice.lineTotal}</Th><Th /></tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i} onMouseEnter={() => setFocus(`l:${l.line_no}`)} onMouseLeave={() => setFocus(null)}>
                  <Td className="w-32 px-2"><Input dir="ltr" value={l.sku} disabled={!editable} onChange={(e) => setLine(i, "sku", e.target.value)} className="h-8 font-mono text-xs" /></Td>
                  <Td className="px-2"><Input dir="auto" value={l.description} disabled={!editable} onChange={(e) => setLine(i, "description", e.target.value)} className="h-8" /></Td>
                  <Td className="w-20 px-2"><Input dir="ltr" inputMode="decimal" value={l.quantity} disabled={!editable} onChange={(e) => setLine(i, "quantity", e.target.value)} className="h-8" /></Td>
                  <Td className="w-28 px-2"><Input dir="ltr" inputMode="decimal" value={l.unit_price} disabled={!editable} onChange={(e) => setLine(i, "unit_price", e.target.value)} className="h-8" /></Td>
                  <Td className="w-28 px-2"><Input dir="ltr" inputMode="decimal" value={l.line_total} disabled={!editable} onChange={(e) => setLine(i, "line_total", e.target.value)} className="h-8" /></Td>
                  <Td className="w-10 px-1">{editable && (
                    <Button size="icon" variant="ghost" aria-label="Remove line" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i).map((x, k) => ({ ...x, line_no: k + 1 })))}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>

        {editable && (
          <Panel className="sticky bottom-4 flex flex-wrap items-end gap-3 p-4 shadow-pop">
            <div className="min-w-56 flex-1">
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
