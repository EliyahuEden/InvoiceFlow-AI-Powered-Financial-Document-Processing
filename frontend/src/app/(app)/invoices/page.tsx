"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, CheckCircle2, FileScan, Files, FileText, Inbox, Loader, Plus, ShieldAlert, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { StatusPill } from "@/components/domain";
import { Pager, RowsSkeleton, SearchBox, Segmented, type Page } from "@/components/list";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, EmptyState, ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
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
  const [sort, setSort] = useState("-created_at");
  const { data, error, mutate, isLoading } = useApi<Page<InvoiceRow> & { status_counts: Record<string, number> }>(
    `/api/invoices${qs({ status, q, page, page_size: 20, sort })}`,
    { refreshInterval: (d) => (d?.items.some((i) => i.status === "processing") ? 3000 : 0) },
  );
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  const counts = data?.status_counts ?? {};
  const totalAll = Object.values(counts).reduce((a, b) => a + b, 0);
  const metrics = [
    { label: t.overview.invoices, value: totalAll, icon: Files, tone: "bg-accent-soft text-accent-ink" },
    { label: t.status.exception, value: counts.exception ?? 0, icon: TriangleAlert, tone: "bg-danger-soft text-danger" },
    { label: t.status.reconciled, value: counts.reconciled ?? 0, icon: CheckCircle2, tone: "bg-ok-soft text-ok" },
    { label: t.status.processing, value: counts.processing ?? 0, icon: Loader, tone: "bg-info-soft text-info" },
  ];
  const sortHeading = (key: string, label: string, end = false) => {
    const active = sort.replace(/^-/, "") === key;
    const Icon = active ? (sort.startsWith("-") ? ArrowDown : ArrowUp) : ArrowUpDown;
    return <Th className={end ? "text-end" : ""} aria-sort={active ? (sort.startsWith("-") ? "descending" : "ascending") : undefined}>
      <button type="button" className="inline-flex items-center gap-1 rounded px-0.5 py-1 hover:text-ink"
        onClick={() => { setSort(sort === key ? `-${key}` : key); setPage(1); }}>{label}<Icon aria-hidden className="h-3 w-3" /></button>
    </Th>;
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title={t.inbox.title} sub={t.inbox.subtitle}
        actions={can("invoice:upload") && (
          <Button asChild variant="primary"><Link href="/invoices/upload"><Plus className="h-4 w-4" />{t.inbox.upload}</Link></Button>
        )}
      />
      <dl className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {metrics.map(({ label, value, icon: Icon, tone }) => (
          <div key={label} className="command-metric flex min-w-0 items-center gap-3 px-3 py-4 sm:px-5">
            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-2xl ${tone}`}><Icon className="h-5 w-5" aria-hidden /></span>
            <div className="min-w-0"><dt className="text-xs font-medium text-ink-2 sm:text-sm">{label}</dt>
              <dd className="mt-1 text-2xl font-semibold leading-none tracking-tight text-ink num sm:text-3xl">{data ? value : "—"}</dd>
            </div>
          </div>
        ))}
      </dl>
      <div className="command-layout grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(13rem,0.27fr)]">
      <Panel className="command-panel min-w-0">
        <div className="space-y-3 border-b border-line p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold tracking-tight">{t.overview.invoices}</h2>
            <SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.inbox.number}, ${t.common.supplier}, PO`} />
          </div>
          <Segmented
            value={status}
            onChange={(v) => { setStatus(v); setPage(1); }}
            options={FILTERS.map((f) => ({
              value: f,
              label: f === "" ? t.inbox.filterAll : f === "processing,failed" ? `${t.status.processing} / ${t.status.failed}` : (t.status as Record<string, string>)[f],
              count: !data ? undefined : f === "" ? totalAll : f.split(",").reduce((a, s) => a + (counts[s] ?? 0), 0),
            }))}
          />
        </div>
        {error ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div> : (
          <Table>
            <thead>
              <tr>
                {sortHeading("invoice_number", t.inbox.number)}<Th>{t.common.supplier}</Th>
                {sortHeading("invoice_date", t.common.date)}{sortHeading("total", t.common.total, true)}
                <Th>{t.common.status}</Th>{sortHeading("created_at", t.inbox.received)}
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? <RowsSkeleton cols={6} /> : data?.items.map((r) => (
                <tr key={r.id} onClick={() => router.push(`/invoices/${r.id}`)}
                  className="cursor-pointer transition-colors hover:bg-sunken/70">
                  <Td>
                    <Link href={`/invoices/${r.id}`} className="flex items-center gap-2 font-medium text-ink hover:text-accent" onClick={(e) => e.stopPropagation()}>
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                        {r.security_flag ? <ShieldAlert className="h-4 w-4 text-danger" aria-label={t.invoice.security} /> : <FileText className="h-4 w-4" aria-hidden />}
                      </span>
                      <span className="min-w-0">
                        <bdi className="block max-w-52 truncate text-sm font-semibold">{r.invoice_number ?? r.filename ?? "—"}</bdi>
                        <span className="flex items-center gap-1 text-xs font-normal text-ink-3">
                          {r.text_method === "ocr" && <FileScan className="h-3 w-3" aria-hidden />}
                          {r.text_method === "ocr" ? t.invoice.ocr : r.text_method === "native" ? t.invoice.nativeText : r.text_method}
                          {r.language && <bdi className="uppercase">{r.language}</bdi>}
                        </span>
                      </span>
                    </Link>
                  </Td>
                  <Td className="max-w-[16rem]">
                    <span dir="auto" className={`block truncate ${r.supplier_matched ? "text-ink" : "text-ink-3 italic"}`}>
                      {locale === "en" && r.supplier_name_en ? r.supplier_name_en : r.supplier_name ?? "—"}
                    </span>
                    {r.po_reference && <bdi className="block font-mono text-xs text-ink-3">{r.po_reference}</bdi>}
                  </Td>
                  <Td className="whitespace-nowrap text-ink-2">{date(r.invoice_date, locale)}</Td>
                  <Td className="text-end font-medium"><span className="ltr">{money(r.total, r.currency)}</span></Td>
                  <Td>
                    <span className="flex items-center gap-1.5">
                      <StatusPill status={r.status} />
                    </span>
                    {r.open_exceptions > 0 && <span className="mt-1 block text-xs text-danger">{t.overview.openExceptions} · {r.open_exceptions}</span>}
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
      <Panel className="command-aside min-w-0">
        <PanelHeader title={t.inbox.statusBreakdown} />
        <div className="space-y-4 p-4">
          {!data && !error && <Skeleton />}
          {data && totalAll === 0 && <p className="text-sm text-ink-3">{t.common.none}</p>}
          {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([key, count]) => (
            <div key={key}>
              <div className="flex items-center justify-between gap-2"><StatusPill status={key} /><bdi className="text-sm font-semibold num">{count}</bdi></div>
              <div aria-hidden className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sunken"><div className="h-full rounded-full bg-accent/60" style={{ width: `${count / totalAll * 100}%` }} /></div>
            </div>
          ))}
        </div>
      </Panel>
      </div>
    </div>
  );
}
