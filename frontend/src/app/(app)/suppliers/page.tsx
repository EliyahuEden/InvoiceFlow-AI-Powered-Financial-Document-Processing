"use client";

import { Building2, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { StatusPill } from "@/components/domain";
import { ImportDialog } from "@/components/import-dialog";
import { Pager, RowsSkeleton, SearchBox, type Page } from "@/components/list";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, EmptyState, ErrorState, Field, Input, Panel, Table, Td, Th } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Supplier = { id: string; name: string; name_en: string | null; tax_id: string | null; payment_terms: string | null; status: string;
  default_currency: string; invoice_count: number; open_po_count: number; aliases: string[] };

function NewSupplier({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const [f, setF] = useState({ name: "", name_en: "", tax_id: "", payment_terms: "", default_currency: "ILS" });
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/api/suppliers", { ...f, name_en: f.name_en || null, tax_id: f.tax_id || null, payment_terms: f.payment_terms || null });
      toast.success(t.suppliers.new);
      onDone();
    } catch (err) { toast.error(err instanceof ApiError ? String(err.message) : t.common.error); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3 border-b border-line bg-sunken/50 p-4 sm:grid-cols-2 lg:grid-cols-5">
      <Field label={t.common.supplier} htmlFor="supplier-name"><Input id="supplier-name" required dir="auto" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
      <Field label="English name" htmlFor="supplier-name-en"><Input id="supplier-name-en" dir="ltr" value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} /></Field>
      <Field label={t.suppliers.taxId} htmlFor="supplier-tax-id"><Input id="supplier-tax-id" dir="ltr" pattern="\d{8,10}" value={f.tax_id} onChange={(e) => setF({ ...f, tax_id: e.target.value })} /></Field>
      <Field label={t.suppliers.terms} htmlFor="supplier-terms"><Input id="supplier-terms" dir="auto" value={f.payment_terms} onChange={(e) => setF({ ...f, payment_terms: e.target.value })} /></Field>
      <div className="flex items-end"><Button type="submit" variant="primary" loading={busy} className="w-full">{t.common.save}</Button></div>
    </form>
  );
}

export default function SuppliersPage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const { data, isLoading, error, mutate } = useApi<Page<Supplier>>(`/api/suppliers${qs({ q, page, page_size: 25 })}`);
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  return (
    <div className="space-y-4">
      <PageHeader title={t.suppliers.title} actions={can("masterdata:write") && (<>
        <ImportDialog kinds={["suppliers"]} onDone={() => mutate()} />
        <Button variant="primary" aria-expanded={adding} onClick={() => setAdding((a) => !a)}><Plus className="h-4 w-4" />{t.suppliers.new}</Button></>)} />
      {error && <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />}
      <Panel>
        <div className="border-b border-line p-4"><SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.common.supplier}, ${t.suppliers.taxId}`} /></div>
        {adding && <NewSupplier onDone={() => { setAdding(false); mutate(); }} />}
        <Table>
          <thead><tr><Th>{t.common.supplier}</Th><Th>{t.suppliers.taxId}</Th><Th>{t.suppliers.terms}</Th><Th className="text-end">{t.suppliers.openPos}</Th>
            <Th className="text-end">{t.suppliers.invoices}</Th><Th>{t.common.status}</Th></tr></thead>
          <tbody>
            {isLoading && !data ? <RowsSkeleton cols={6} /> : data?.items.map((s) => (
              <tr key={s.id} className="hover:bg-sunken/70">
                <Td><Link href={`/suppliers/${s.id}`} className="font-medium text-accent hover:underline" dir="auto">{locale === "en" && s.name_en ? s.name_en : s.name}</Link>
                  {s.name_en && <span className="block text-xs text-ink-3" dir="auto">{locale === "en" ? s.name : s.name_en}</span>}</Td>
                <Td><span className="ltr font-mono text-sm">{s.tax_id ?? "—"}</span></Td>
                <Td dir="auto" className="text-ink-2">{s.payment_terms ?? "—"}</Td>
                <Td className="text-end num">{s.open_po_count}</Td>
                <Td className="text-end num">{s.invoice_count}</Td>
                <Td><StatusPill status={s.status} /></Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {data && data.items.length === 0 && <EmptyState icon={<Building2 className="h-8 w-8" />} title={t.common.noResults} />}
        {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Panel>
    </div>
  );
}
