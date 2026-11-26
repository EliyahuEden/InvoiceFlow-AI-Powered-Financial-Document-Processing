"use client";

import { AlertTriangle, ArrowRight, Bot, CheckCircle2, FileSearch, FileText, Layers, Loader2, Wrench } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { ActionLabel, AiBlock, Citation, FindingTag, StatusPill, type CitationT } from "@/components/domain";
import { Pager, SearchBox, type Page } from "@/components/list";
import { CountBadge, DetailPanel, DetailSection, FilterBar, PageHeader, Segments, useWideLayout } from "@/components/page-kit";
import { Button, cx, EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { dateTime, relative } from "@/lib/format";
import { pickLang, useI18n } from "@/lib/i18n";
import type { AiSummary } from "@/lib/types";

type Run = { id: string; status: string; mode: string; prompt_version: string; invoice_id: string; invoice_number: string | null;
  supplier_name: string | null; supplier_name_en: string | null; tool_calls: number; proposed_action: string | null;
  headline: Record<string, string> | null; evidence_count: number | null; finding_types: string[]; report_mode: string | null;
  created_at: string; updated_at: string };
type RunDetail = { id: string; status: string; mode: string; prompt_version: string; error: string | null; steps: unknown[];
  invoice_id: string; invoice_number: string | null; created_at: string; updated_at: string;
  result: { report: AiSummary | null; proposed_action: string | null } | null };

type Segment = "" | "queued,running" | "awaiting_approval" | "completed" | "failed";
const SEGMENTS: Segment[] = ["", "queued,running", "awaiting_approval", "completed", "failed"];

export default function InvestigationsPage() {
  const { t, locale } = useI18n();
  const wide = useWideLayout();
  const [page, setPage] = useState(1);
  const [segment, setSegment] = useState<Segment>("");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading, error, mutate } = useApi<Page<Run> & { status_counts?: Record<string, number> }>(
    `/api/agent/runs${qs({ page, page_size: 25, status: segment || undefined, q: q || undefined })}`,
    { refreshInterval: (d) => (d?.items.some((r) => ["queued", "running"].includes(r.status)) ? 3000 : 15000) },
  );
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  const counts = data?.status_counts ?? {};
  const count = (key: string) => key.split(",").reduce((a, s) => a + (counts[s] ?? 0), 0);
  const all = Object.values(counts).reduce((a, b) => a + b, 0);
  const selected = data?.items.find((r) => r.id === selectedId) ?? data?.items[0] ?? null;
  const segLabel: Record<Segment, string> = { "": t.inbox.filterAll, "queued,running": t.agent.segRunning,
    awaiting_approval: t.status.awaiting_approval, completed: t.status.completed, failed: t.status.failed };
  const segIcon = { "": Layers, "queued,running": Loader2, awaiting_approval: AlertTriangle, completed: CheckCircle2, failed: AlertTriangle } as const;
  const segTone = { "": "neutral", "queued,running": "accent", awaiting_approval: "warn", completed: "ok", failed: "danger" } as const;

  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={t.agent.title} sub={t.agent.subtitle} />
      <Segments label={t.common.status} value={segment} onChange={(v) => { setSegment(v); setPage(1); }}
        options={SEGMENTS.filter((s) => s === "" || count(s) > 0 || segment === s).map((s) => ({
          value: s, label: segLabel[s], count: data ? (s === "" ? all : count(s)) : undefined, icon: segIcon[s], tone: segTone[s] }))} />

      <div className="grid min-w-0 items-start gap-4 min-[1440px]:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_26rem]">
        <Panel className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-4">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{segLabel[segment]}{data && <CountBadge>{data.total}</CountBadge>}</h2>
          </div>
          <FilterBar className="border-b border-line px-5 pb-4" search={<SearchBox value={q} onChange={onQ} placeholder={`${t.common.search}: ${t.agent.searchPh}`} />}
            onClear={q || segment ? () => { setQ(""); setSegment(""); setPage(1); } : undefined} />
          {error && <div className="p-4"><ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /></div>}
          {isLoading && !data ? <div className="space-y-3 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}</div>
            : data && data.items.length === 0 ? <EmptyState icon={<Bot className="h-8 w-8" />} title={q || segment ? t.common.noResults : t.agent.empty} />
            : <ul className="divide-y divide-line">
              {data?.items.map((r) => {
                const isSelected = wide && selected?.id === r.id;
                const supplier = (locale === "en" && r.supplier_name_en) || r.supplier_name;
                const headline = r.headline ? pickLang(r.headline, locale) : null;
                return <li key={r.id} data-selected={isSelected || undefined} className={cx("relative transition-colors hover:bg-accent/[.045]", isSelected && "queue-row-selected bg-accent/[.085] hover:bg-accent/[.085]")}>
                  <div className="grid gap-x-4 gap-y-2 px-5 py-4 md:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_auto] md:items-start">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink-3"><FileText className="h-4 w-4" aria-hidden /></span>
                      <div className="min-w-0">
                        {wide ? <button type="button" aria-pressed={isSelected} onClick={() => setSelectedId(r.id)}
                          className="text-start font-mono text-sm font-bold text-ink after:absolute after:inset-0 hover:text-accent">
                          <bdi>{r.invoice_number ?? r.invoice_id.slice(0, 8)}</bdi></button>
                          : <Link href={`/investigations/${r.id}`} className="font-mono text-sm font-bold text-ink after:absolute after:inset-0 hover:text-accent"><bdi>{r.invoice_number ?? r.invoice_id.slice(0, 8)}</bdi></Link>}
                        <p className="truncate text-sm text-ink-2"><bdi>{supplier ?? "—"}</bdi></p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-2"><StatusPill status={r.status} />
                          <span className="text-xs text-ink-3">{t.agent.startedAgo.replace("{when}", relative(r.created_at, locale))}</span></div>
                      </div>
                    </div>
                    <div className="min-w-0">
                      {headline ? <p className="flex gap-2 text-sm leading-snug text-ink"><FileSearch className="mt-0.5 h-4 w-4 shrink-0 text-ai" aria-label={t.ai.generated} />
                        <span className="line-clamp-2"><bdi>{headline}</bdi></span></p>
                        : <p className="text-sm text-ink-3">{["queued", "running"].includes(r.status) ? t.agent.stillRunning : t.agent.noReport}</p>}
                      {r.proposed_action && <p className="mt-1.5 text-xs text-ink-3">{t.review.suggestedStep}: <span className="font-semibold text-ink-2"><ActionLabel action={r.proposed_action} /></span></p>}
                    </div>
                    <dl className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-3 md:flex-col md:items-end md:text-end">
                      {r.evidence_count !== null && <div><dt className="sr-only">{t.agent.sources}</dt><dd>{t.agent.evidenceN.replace("{n}", String(r.evidence_count))}</dd></div>}
                      <div><dt className="sr-only">{t.agent.tools}</dt><dd className="inline-flex items-center gap-1"><Wrench className="h-3 w-3" aria-hidden />{t.agent.toolsN.replace("{n}", String(r.tool_calls))}</dd></div>
                      <div><dt className="sr-only">{t.agent.model}</dt><dd className="font-mono" dir="ltr">{r.mode.replace("llm:", "")}</dd></div>
                    </dl>
                  </div>
                </li>;
              })}
            </ul>}
          {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
        </Panel>
        {wide && selected && <aside className="min-w-0 min-[1440px]:sticky min-[1440px]:top-20"><RunPanel run={selected} /></aside>}
      </div>
    </div>
  );
}

/** What the selected run found, as stored: the AI report (labelled, advisory), its findings and the passages it cites. */
function RunPanel({ run }: { run: Run }) {
  const { t, locale } = useI18n();
  const { data: r, error } = useApi<RunDetail>(`/api/agent/runs/${run.id}`, { refreshInterval: (d) => (d && ["queued", "running"].includes(d.status) ? 2000 : 0) });
  const report = r?.result?.report ?? null;
  const supplier = (locale === "en" && run.supplier_name_en) || run.supplier_name;
  // the passages behind the findings, each cited once, in the order the findings cite them
  const seen = new Set<string>();
  const citations: CitationT[] = (report?.findings ?? []).flatMap((f) => f.citations).filter((c) => {
    const key = c.chunk_id ?? `${c.document_id}:${c.page}:${c.quote}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 3);
  return <DetailPanel title={<bdi className="font-mono">{run.invoice_number ?? run.invoice_id.slice(0, 8)}</bdi>}
    meta={<div className="space-y-1.5"><p className="text-sm text-ink-2"><bdi>{supplier ?? "—"}</bdi></p><StatusPill status={run.status} /></div>}
    footer={<div className="flex gap-2">
      <Button variant="primary" className="flex-1" asChild><Link href={`/investigations/${run.id}`}>{t.agent.openRun}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button>
      <Button asChild><Link href={`/invoices/${run.invoice_id}`}>{t.inbox.openInvoice}</Link></Button>
    </div>}>
    {error ? <ErrorState message={t.common.error} /> : !r ? <div className="space-y-3"><Skeleton className="h-28 w-full" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-20 w-full" /></div> : <>
      {r.error && <p className="rounded-xl bg-danger-soft px-3 py-2.5 text-sm text-danger">{r.error}</p>}
      {report ? <AiBlock mode={report.mode === "offline-template" ? "offline" : r.mode}>
        <p className="font-bold leading-snug text-ink"><bdi>{pickLang(report.headline, locale)}</bdi></p>
        <p className="mt-1.5 line-clamp-4 text-sm leading-relaxed text-ink-2"><bdi>{pickLang(report.summary, locale)}</bdi></p>
      </AiBlock> : <p className="rounded-xl bg-sunken px-3 py-4 text-sm text-ink-3">{["queued", "running"].includes(r.status) ? t.agent.stillRunning : t.agent.noReport}</p>}
      {report && report.findings.length > 0 && <DetailSection title={t.agent.findings}>
        <ul className="space-y-2.5">{report.findings.map((f, i) => <li key={`${f.type}-${i}`} className="space-y-1">
          <FindingTag type={f.type} severity={f.severity} />
          <p className="line-clamp-3 text-sm leading-snug text-ink-2"><bdi>{pickLang(f.explanation, locale)}</bdi></p>
        </li>)}</ul>
      </DetailSection>}
      {citations.length > 0 && <DetailSection title={<>{t.agent.sources} <span className="font-normal text-ink-3">· {report?.evidence_count ?? citations.length}</span></>}>
        <div className="space-y-2">{citations.map((c, i) => <Citation key={c.chunk_id ?? i} c={c} index={i + 1} />)}</div>
      </DetailSection>}
      {(r.result?.proposed_action ?? run.proposed_action) && <DetailSection title={t.review.suggestedStep}>
        <p className="rounded-xl border border-line px-3.5 py-3 text-sm font-semibold text-ink"><ActionLabel action={r.result?.proposed_action ?? run.proposed_action} /></p>
      </DetailSection>}
      <details className="group rounded-xl border border-line">
        <summary className="cursor-pointer list-none px-3.5 py-2.5 text-sm font-semibold text-ink-2 hover:text-ink">{t.agent.technical}</summary>
        <dl className="space-y-1.5 border-t border-line px-3.5 py-3 text-xs">
          <div className="flex justify-between gap-3"><dt className="text-ink-3">{t.agent.model}</dt><dd className="font-mono text-ink" dir="ltr">{r.mode}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-ink-3">{t.agent.promptVersion}</dt><dd className="font-mono text-ink" dir="ltr">{r.prompt_version}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-ink-3">{t.agent.tools}</dt><dd className="text-ink num">{r.steps.length}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-ink-3">{t.common.created}</dt><dd className="text-ink">{dateTime(r.created_at, locale)}</dd></div>
        </dl>
      </details>
    </>}
  </DetailPanel>;
}
