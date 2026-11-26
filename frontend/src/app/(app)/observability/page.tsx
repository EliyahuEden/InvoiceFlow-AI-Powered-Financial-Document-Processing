"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Activity, AlertTriangle, ArrowRight, Bot, Cpu, Info, Layers } from "lucide-react";
import { BarList } from "@/components/bar-list";

// Recharts is the heaviest dependency: load the line chart after the page has rendered.
const Lines = dynamic(() => import("@/components/charts").then((m) => m.Lines), {
  ssr: false, loading: () => <div className="skeleton h-[220px] w-full rounded-xl" aria-hidden />,
});
import { Pill } from "@/components/domain";
import { Pager, type Page } from "@/components/list";
import { CountBadge, DetailPanel, FilterSelect, PageHeader, StatTile, useWideLayout } from "@/components/page-kit";
import { Button, cx, EmptyState, ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

type Summary = {
  by_model: { kind: string; provider: string; model: string; prompt_version: string; calls: number; errors: number; retries: number;
    p50_ms: number | null; p95_ms: number | null; input_tokens: number; output_tokens: number; cost_usd: number | null }[];
  daily: Record<string, number | string>[];
  agent: { runs: number; by_status: Record<string, number>; tool_usage: Record<string, number>; rejected_tool_calls: number };
  extraction: { by_method: Record<string, number>; validation_warnings: Record<string, number>; missing_fields: Record<string, number> };
  jobs: Record<string, number>; pricing_configured: boolean;
};
/** "openai / openai/gpt-oss-120b" reads as a typo: name the provider once when the model id already starts with it. */
const modelName = (provider: string, model: string) => model.startsWith(`${provider}/`) ? model : `${provider} / ${model}`;

type Call = { id: string; created_at: string; kind: string; workflow: string | null; provider: string; model: string; prompt_version: string | null;
  latency_ms: number; input_tokens: number | null; output_tokens: number | null; cost_usd: number | null; status: string; retries: number;
  error: string | null; invoice_id: string | null };

/** A code such as SUSPICIOUS_INSTRUCTIONS, read as words where no translation exists. */
const words = (code: string) => code.charAt(0) + code.slice(1).toLowerCase().replaceAll("_", " ");

export default function ObservabilityPage() {
  const { t, locale } = useI18n();
  const wide = useWideLayout();
  const { data: s, error, mutate } = useApi<Summary>("/api/observability/summary", { refreshInterval: 15000 });
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: calls, error: callsError, mutate: retryCalls } = useApi<Page<Call>>(`/api/observability/calls${qs({ kind, page, page_size: 15 })}`);
  const kinds = Array.from(new Set(s?.by_model.map((r) => r.kind) ?? []));
  const kindLabel = (k: string) => label(t.observability.kind, k);
  const modelCalls = s?.by_model.reduce((a, r) => a + r.calls, 0) ?? 0;
  const modelErrors = s?.by_model.reduce((a, r) => a + r.errors, 0) ?? 0;
  const toolCalls = s ? Object.values(s.agent.tool_usage).reduce((a, b) => a + b, 0) : 0;
  const jobs = s ? Object.values(s.jobs).reduce((a, b) => a + b, 0) : 0;
  const n = (v: number | undefined) => (s ? <bdi>{v}</bdi> : <Skeleton className="h-7 w-10" />);
  const selected = calls?.items.find((c) => c.id === selectedId) ?? calls?.items[0] ?? null;
  const methodName = (m: string) => (m.startsWith("rules+llm") ? `${t.inbox.methodRulesAi} (${m.split(":")[1] ?? ""})` : m === "rule_based" ? t.inbox.methodRules : m);

  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={t.observability.title} sub={t.observability.subtitle}
        stats={<>
          <StatTile icon={Cpu} label={t.observability.modelCalls} value={n(modelCalls)} tone="danger" active={false}
            note={s && (modelErrors > 0 ? <span className="text-danger">{t.observability.errorsN.replace("{n}", String(modelErrors))}</span> : t.observability.errorsN.replace("{n}", "0"))} />
          <StatTile icon={Bot} label={t.observability.agentRuns} value={n(s?.agent.runs)}
            note={s && <>{t.observability.toolsN.replace("{n}", String(toolCalls))} · {t.observability.rejected}: <bdi className="num">{s.agent.rejected_tool_calls}</bdi></>} />
          <StatTile icon={Layers} className="col-span-2 md:col-span-1" label={t.observability.extractionJobs} value={n(jobs)}
            note={s && (s.jobs.failed ? <span className="text-danger">{t.observability.failedN.replace("{n}", String(s.jobs.failed))}</span> : t.observability.failedN.replace("{n}", "0"))} />
        </>} />

      {/* honest notices: what is not recorded or not estimated, instead of empty tables */}
      {s && (!s.pricing_configured || modelCalls === 0) && <div className="space-y-2">
        {modelCalls === 0 && <p className="flex items-start gap-2.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2"><Info className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />{t.observability.noModelCalls}</p>}
        {!s.pricing_configured && modelCalls > 0 && <p className="flex items-start gap-2.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2"><Info className="mt-0.5 h-4 w-4 shrink-0 text-ink-3" aria-hidden />{t.observability.noPricing}</p>}
      </div>}

      <div className="grid min-w-0 gap-4 lg:grid-cols-3">
        <Panel><PanelHeader title={t.observability.toolUsage} sub={s && `${s.agent.runs} ${t.observability.agentRuns.toLocaleLowerCase()}`} />
          <div className="p-5">{!s ? <Skeleton className="h-40 w-full" /> : toolCalls === 0 ? <p className="text-sm text-ink-3">{t.common.none}</p>
            : <BarList items={Object.entries(s.agent.tool_usage).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: label(t.observability.tools, k), value: v, hint: `${k}: ${v}` }))} />}</div></Panel>
        <Panel><PanelHeader title={t.observability.warningsTitle} />
          <div className="p-5">{!s ? <Skeleton className="h-24 w-full" /> : Object.keys(s.extraction.validation_warnings).length === 0 ? <p className="text-sm text-ink-3">{t.observability.noWarnings}</p>
            : <BarList color="var(--series-2)" items={Object.entries(s.extraction.validation_warnings).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: label(t.observability.warningCodes, k, label(t.finding, k, words(k))), value: v, hint: `${k}: ${v}` }))} />}</div></Panel>
        <Panel><PanelHeader title={t.observability.methodsTitle} />
          <div className="p-5">{!s ? <Skeleton className="h-24 w-full" /> : Object.keys(s.extraction.by_method).length === 0 ? <p className="text-sm text-ink-3">{t.common.none}</p>
            : <BarList color="var(--series-3)" items={Object.entries(s.extraction.by_method).map(([k, v]) => ({ label: methodName(k), value: v, hint: `${k}: ${v}` }))} />}
            {s && jobs > 0 && <p className="mt-4 border-t border-line pt-3 text-xs text-ink-3">{t.observability.extractionJobs}: {Object.entries(s.jobs).map(([k, v]) => `${label(t.status, k)} ${v}`).join(" · ")}</p>}
          </div></Panel>
      </div>

      {s && s.daily.length >= 5 && <Panel><PanelHeader title={t.observability.daily} />
        <div className="p-4"><Lines xKey="date" data={s.daily} series={kinds.slice(0, 4).map((k) => ({ key: k, label: kindLabel(k) }))} /></div></Panel>}

      {s && s.by_model.length > 0 && <Panel>
        <PanelHeader title={t.observability.byModel} />
        <ul className="divide-y divide-line md:hidden">{s.by_model.map((r, i) => <li key={i} className="space-y-2 px-5 py-3.5">
          <div className="flex items-center justify-between gap-2"><Pill tone="neutral">{kindLabel(r.kind)}</Pill>
            <span className="text-sm text-ink-2">{t.observability.calls}: <bdi className="font-bold text-ink num">{r.calls}</bdi></span></div>
          <bdi className="block break-all font-mono text-xs text-ink" dir="ltr">{modelName(r.provider, r.model)}</bdi>
          <dl className="grid grid-cols-3 gap-2 text-xs">
            <div><dt className="text-ink-3">p50</dt><dd className="font-semibold text-ink num"><bdi dir="ltr">{r.p50_ms ?? "—"} ms</bdi></dd></div>
            <div><dt className="text-ink-3">{t.observability.tokens}</dt><dd className="font-semibold text-ink num"><bdi dir="ltr">{r.input_tokens || r.output_tokens ? `${r.input_tokens.toLocaleString()} / ${r.output_tokens.toLocaleString()}` : "—"}</bdi></dd></div>
            <div><dt className="text-ink-3">{t.observability.errors}</dt><dd className={cx("font-semibold num", r.errors ? "text-danger" : "text-ink")}>{r.errors}</dd></div>
          </dl>
        </li>)}</ul>
        <div className="hidden md:block"><Table>
          <thead><tr><Th>{t.observability.kindLabel}</Th><Th>{t.observability.model}</Th><Th>{t.observability.prompt}</Th><Th className="text-end">{t.observability.calls}</Th>
            <Th className="text-end">p50</Th><Th className="text-end">p95</Th><Th className="text-end">{t.observability.tokens}</Th>
            <Th className="text-end">{t.observability.cost}</Th><Th className="text-end">{t.observability.errors}</Th></tr></thead>
          <tbody>{s.by_model.map((r, i) => (
            <tr key={i}>
              <Td><Pill tone="neutral">{kindLabel(r.kind)}</Pill></Td>
              <Td><bdi className="whitespace-nowrap font-mono text-xs" dir="ltr">{modelName(r.provider, r.model)}</bdi></Td>
              <Td><bdi className="whitespace-nowrap font-mono text-xs text-ink-3" dir="ltr">{r.prompt_version}</bdi></Td>
              <Td className="text-end num">{r.calls}</Td>
              <Td className="whitespace-nowrap text-end num"><bdi dir="ltr">{r.p50_ms ?? "—"} ms</bdi></Td>
              <Td className="whitespace-nowrap text-end num"><bdi dir="ltr">{r.p95_ms ?? "—"} ms</bdi></Td>
              <Td className="whitespace-nowrap text-end num"><bdi dir="ltr">{r.input_tokens || r.output_tokens ? `${r.input_tokens.toLocaleString()} / ${r.output_tokens.toLocaleString()}` : "—"}</bdi></Td>
              <Td className="text-end num">{r.cost_usd === null ? "—" : <bdi dir="ltr">${r.cost_usd.toFixed(4)}</bdi>}</Td>
              <Td className={cx("text-end num", r.errors && "font-semibold text-danger")}>{r.errors}{r.retries ? ` (+${r.retries})` : ""}</Td>
            </tr>))}</tbody>
        </Table></div>
      </Panel>}

      <div className={cx("grid min-w-0 gap-4", wide && selected && "min-[1440px]:grid-cols-[minmax(0,1fr)_22rem]")}>
        <Panel className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-4">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{t.observability.recent}{calls && <CountBadge>{calls.total}</CountBadge>}</h2>
            {kinds.length > 0 && <FilterSelect label={t.observability.kindLabel} value={kind} onChange={(v) => { setKind(v); setPage(1); }}>
              <option value="">{t.common.all}</option>{kinds.map((k) => <option key={k} value={k}>{kindLabel(k)}</option>)}
            </FilterSelect>}
          </div>
          {callsError && <div className="p-4"><ErrorState message={t.common.error} retryLabel={t.common.retry} onRetry={() => retryCalls()} /></div>}
          {calls && calls.items.length === 0 ? <EmptyState icon={<Activity className="h-8 w-8" />} title={t.observability.noCallsShort} />
            : <>
            <ul className="divide-y divide-line md:hidden">{!calls ? <li className="p-5"><Skeleton className="h-24 w-full" /></li> : calls.items.map((c) => <li key={c.id} className="space-y-1 px-5 py-3">
              <div className="flex items-center justify-between gap-2"><span className="text-sm font-semibold text-ink">{kindLabel(c.kind)}</span>
                <Pill tone={c.status === "ok" ? "ok" : "danger"}>{c.status === "ok" ? "OK" : c.status}</Pill></div>
              <bdi className="block break-all font-mono text-xs text-ink-3" dir="ltr">{c.workflow ?? "—"} · {c.model}</bdi>
              <p className="flex flex-wrap gap-x-3 text-xs text-ink-3"><span>{dateTime(c.created_at, locale)}</span><bdi className="num" dir="ltr">{c.latency_ms} ms</bdi>
                {c.input_tokens !== null && <bdi className="num" dir="ltr">{c.input_tokens} / {c.output_tokens}</bdi>}</p>
              {c.error && <p className="break-words text-xs text-danger">{c.error}</p>}
            </li>)}</ul>
            <div className="hidden md:block"><Table className="queue-table">
              <thead><tr><Th>{t.common.date}</Th><Th>{t.observability.workflow}</Th><Th>{t.observability.model}</Th><Th className="text-end">{t.observability.latency}</Th>
                <Th className="text-end">{t.observability.tokens}</Th><Th>{t.common.status}</Th></tr></thead>
              <tbody>{!calls ? <tr><Td colSpan={6}><Skeleton className="h-24 w-full" /></Td></tr> : calls.items.map((c) => {
                const isSelected = wide && selected?.id === c.id;
                return <tr key={c.id} className={cx(wide && "cursor-pointer", isSelected && "queue-row-selected")}
                  onClick={(e) => { if (wide && !(e.target as HTMLElement).closest("a,button")) setSelectedId(c.id); }}>
                  <Td className="whitespace-nowrap text-xs text-ink-3">{wide ? <button type="button" aria-pressed={isSelected} onClick={() => setSelectedId(c.id)} className="text-start hover:text-ink">
                    <span className="sr-only">{t.observability.callDetail}: </span>{dateTime(c.created_at, locale)}</button> : dateTime(c.created_at, locale)}</Td>
                  <Td><span className="block text-sm text-ink">{kindLabel(c.kind)}</span><bdi className="font-mono text-xs text-ink-3" dir="ltr">{c.workflow ?? "—"}</bdi></Td>
                  <Td><bdi className="whitespace-nowrap font-mono text-xs text-ink-2" dir="ltr">{c.model}</bdi></Td>
                  <Td className="whitespace-nowrap text-end num"><bdi dir="ltr">{c.latency_ms} ms</bdi></Td>
                  <Td className="whitespace-nowrap text-end num"><bdi dir="ltr">{c.input_tokens !== null ? `${c.input_tokens} / ${c.output_tokens}` : "—"}</bdi></Td>
                  <Td><Pill tone={c.status === "ok" ? "ok" : "danger"}>{c.status === "ok" ? "OK" : c.status}</Pill></Td>
                </tr>;
              })}</tbody>
            </Table></div>
            </>}
          {calls && calls.items.length > 0 && <Pager page={calls.page} pages={calls.pages} total={calls.total} onPage={setPage} />}
        </Panel>
        {wide && selected && <aside className="flex min-w-0 flex-col [&>*]:flex-1"><CallPanel call={selected} /></aside>}
      </div>
    </div>
  );
}

/** One recorded call: its metadata only. Prompts and model output are not shown here (they can hold document content). */
function CallPanel({ call: c }: { call: Call }) {
  const { t, locale } = useI18n();
  const row = (k: string, v: React.ReactNode) => <div className="flex items-baseline justify-between gap-3 py-1.5">
    <dt className="shrink-0 text-sm text-ink-3">{k}</dt><dd className="min-w-0 break-words text-end text-sm font-medium text-ink">{v ?? "—"}</dd></div>;
  return <DetailPanel title={t.observability.callDetail}
    meta={<div className="flex flex-wrap items-center gap-2"><Pill tone={c.status === "ok" ? "ok" : "danger"}>{c.status === "ok" ? "OK" : c.status}</Pill>
      <span className="text-sm text-ink-2">{label(t.observability.kind, c.kind)}</span></div>}
    footer={c.invoice_id ? <Button variant="secondary" className="w-full" asChild><Link href={`/invoices/${c.invoice_id}`}>{t.inbox.openInvoice}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button> : undefined}>
    {c.error && <p className="flex gap-2 rounded-xl bg-danger-soft px-3 py-2.5 text-sm text-danger"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /><span className="break-words">{c.error}</span></p>}
    <dl className="divide-y divide-line">
      {row(t.common.date, dateTime(c.created_at, locale))}
      {row(t.observability.workflow, c.workflow && <bdi className="font-mono text-xs" dir="ltr">{c.workflow}</bdi>)}
      {row(t.observability.model, <bdi className="font-mono text-xs" dir="ltr">{c.provider} / {c.model}</bdi>)}
      {row(t.observability.prompt, c.prompt_version && <bdi className="font-mono text-xs" dir="ltr">{c.prompt_version}</bdi>)}
      {row(t.observability.latency, <bdi dir="ltr">{c.latency_ms} ms</bdi>)}
      {row(t.observability.tokens, c.input_tokens !== null && <bdi dir="ltr">{c.input_tokens} / {c.output_tokens}</bdi>)}
      {row(t.observability.cost, c.cost_usd !== null && <bdi dir="ltr">${c.cost_usd.toFixed(5)}</bdi>)}
      {row(t.observability.retries, <bdi className="num">{c.retries}</bdi>)}
    </dl>
  </DetailPanel>;
}
