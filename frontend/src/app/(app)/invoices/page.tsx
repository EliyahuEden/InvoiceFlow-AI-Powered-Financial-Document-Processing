"use client";

import { FileScan, FileText, Inbox, ShieldAlert, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { StatusPill } from "@/components/domain";
import { Pager, RowsSkeleton, SearchBox, Segmented, type Page } from "@/components/list";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, EmptyState, ErrorState, Panel, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { date, money, relative } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export type InvoiceRow = {
  id: string; status: string; invoice_number: string | null; supplier_name: string | null; supplier_name_en: string | null;
  supplier_matched: boolean; invoice_date: string | null; currency: string | null; total: string | null;
  po_reference: string | null; language: string | null; extraction_method: string | null; created_at: string;
  filename: string | null; text_method: string | null; open_exceptions: number; warnings: number; security_flag: boolean;
};

const FILTERS = ["", "exception", "needs_review", "reconciled", "on_hold", "approved", "processing,failed"];

export default function InboxPage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const router = useRouter();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, mutate, isLoading } = useApi<Page<InvoiceRow> & { status_counts: Record<string, number> }>(
    `/api/invoices${qs({ status, q, page, page_size: 20 })}`,
    { refreshInterval: (d) => (d?.items.some((i) => i.status === "processing") ? 3000 : 0) },
  );
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  const counts = data?.status_counts ?? {};
  const totalAll = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div>
      <PageHeader
        title={t.inbox.title}
        actions={can("invoice:upload") && (
          <Button asChild variant="primary"><Link href="/invoices/upload"><Upload className="h-4 w-4" />{t.inbox.upload}</Link></Button>
        )}
      />
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-3">
          <Segmented
            value={status}
            onChange={(v) => { setStatus(v); setPage(1); }}
            options={FILTERS.map((f) => ({
              value: f,
              label: f === "" ? t.inbox.filterAll : f === "processing,failed" ? `${t.status.processing} / ${t.status.failed}` : (t.status as Record<string, string>)[f],
              count: f === "" ? totalAll : f.split(",").reduce((a, s) => a + (counts[s] ?? 0), 0),
            }))}
          />
          <SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.inbox.number}, ${t.common.supplier}, PO`} />
        </div>
        {error ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div> : (
          <Table>
            <thead>
              <tr>
                <Th>{t.inbox.number}</Th><Th>{t.common.supplier}</Th><Th>{t.common.date}</Th>
                <Th className="text-end">{t.common.total}</Th><Th>{t.inbox.po}</Th><Th>{t.common.status}</Th>
                <Th>{t.inbox.method}</Th><Th>{t.inbox.received}</Th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? <RowsSkeleton cols={8} /> : data?.items.map((r) => (
                <tr key={r.id} onClick={() => router.push(`/invoices/${r.id}`)}
                  className="cursor-pointer transition-colors hover:bg-sunken/70">
                  <Td>
                    <Link href={`/invoices/${r.id}`} className="flex items-center gap-2 font-medium text-ink hover:text-accent" onClick={(e) => e.stopPropagation()}>
                      {r.security_flag && <ShieldAlert className="h-4 w-4 text-danger" aria-label={t.invoice.security} />}
                      <span className="ltr font-mono text-sm">{r.invoice_number ?? r.filename ?? "—"}</span>
                    </Link>
                  </Td>
                  <Td className="max-w-[16rem]">
                    <span dir="auto" className={`block truncate ${r.supplier_matched ? "text-ink" : "text-ink-3 italic"}`}>
                      {locale === "en" && r.supplier_name_en ? r.supplier_name_en : r.supplier_name ?? "—"}
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{date(r.invoice_date, locale)}</Td>
                  <Td className="text-end font-medium"><span className="ltr">{money(r.total, r.currency)}</span></Td>
                  <Td><span className="ltr font-mono text-xs text-ink-2">{r.po_reference ?? "—"}</span></Td>
                  <Td>
                    <span className="flex items-center gap-1.5">
                      <StatusPill status={r.status} />
                      {r.open_exceptions > 0 && r.status !== "exception" && <span className="h-1.5 w-1.5 rounded-full bg-danger" aria-hidden />}
                    </span>
                  </Td>
                  <Td>
                    <span className="inline-flex items-center gap-1 text-xs text-ink-3">
                      {r.text_method === "ocr" ? <FileScan className="h-3.5 w-3.5" /> : <FileText className="h-3.5 w-3.5" />}
                      {r.text_method === "ocr" ? t.invoice.ocr : r.text_method === "native" ? t.invoice.nativeText : r.text_method ?? "—"}
                      {r.language && <span className="uppercase">· {r.language}</span>}
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap text-xs text-ink-3">{relative(r.created_at, locale)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && data.items.length === 0 && (
          <EmptyState icon={<Inbox className="h-8 w-8" />} title={q || status ? t.common.noResults : t.inbox.empty} />
        )}
        {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Panel>
    </div>
  );
}
