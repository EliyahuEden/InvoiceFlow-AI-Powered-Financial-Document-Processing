"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { BarList } from "@/components/bar-list";

// Recharts is the heaviest dependency: load the line chart after the page has rendered.
const Lines = dynamic(() => import("@/components/charts").then((m) => m.Lines), {
  ssr: false, loading: () => <div className="skeleton h-[220px] w-full rounded-xl" aria-hidden />,
});
import { Pill } from "@/components/domain";
import { Pager, Segmented, type Page } from "@/components/list";
import { PageHeader } from "@/components/shell";
import { ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Summary = {
  by_model: { kind: string; provider: string; model: string; prompt_version: string; calls: number; errors: number; retries: number;
    p50_ms: number | null; p95_ms: number | null; input_tokens: number; output_tokens: number; cost_usd: number | null }[];
  daily: Record<string, number | string>[];
  agent: { runs: number; by_status: Record<string, number>; tool_usage: Record<string, number>; rejected_tool_calls: number };
  extraction: { by_method: Record<string, number>; validation_warnings: Record<string, number>; missing_fields: Record<string, number> };
  jobs: Record<string, number>; pricing_configured: boolean;
};
type Call = { id: string; created_at: string; kind: string; workflow: string; provider: string; model: string; latency_ms: number;
  input_tokens: number | null; output_tokens: number | null; cost_usd: number | null; status: string; retries: number; error: string | null };

export default function ObservabilityPage() {
  const { t, locale } = useI18n();
  const { data: s, error, mutate } = useApi<Summary>("/api/observability/summary", { refreshInterval: 15000 });
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const { data: calls, error: callsError, mutate: retryCalls } = useApi<Page<Call>>(`/api/observability/calls${qs({ kind, page, page_size: 15 })}`);
  const kinds = Array.from(new Set(s?.by_model.map((r) => r.kind) ?? []));
  return (
    <div className="space-y-5">
      <PageHeader title={t.observability.title} sub={s && !s.pricing_configured ? t.observability.noPricing : undefined} />
      <Panel>
        <PanelHeader title={t.observability.calls} />
        {error ? <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} /> : !s ? <div className="p-4"><Skeleton className="h-40 w-full" /></div> : (
          <Table>
            <thead><tr><Th>Kind</Th><Th>Provider / model</Th><Th>Prompt</Th><Th className="text-end">{t.observability.calls}</Th>
              <Th className="text-end">p50</Th><Th className="text-end">p95</Th><Th className="text-end">{t.observability.tokens} in/out</Th>
              <Th className="text-end">{t.observability.cost}</Th><Th className="text-end">{t.observability.errors}</Th></tr></thead>
            <tbody>{s.by_model.map((r, i) => (
              <tr key={i}>
                <Td><Pill tone="neutral">{r.kind}</Pill></Td>
                <Td className="font-mono text-xs">{r.provider} / {r.model}</Td>
                <Td className="font-mono text-xs text-ink-3">{r.prompt_version}</Td>
                <Td className="text-end num">{r.calls}</Td>
                <Td className="text-end num">{r.p50_ms ?? "—"} ms</Td>
                <Td className="text-end num">{r.p95_ms ?? "—"} ms</Td>
                <Td className="text-end num">{r.input_tokens || r.output_tokens ? `${r.input_tokens.toLocaleString()} / ${r.output_tokens.toLocaleString()}` : "—"}</Td>
                <Td className="text-end num">{r.cost_usd === null ? "—" : `$${r.cost_usd.toFixed(4)}`}</Td>
                <Td className={`text-end num ${r.errors ? "font-medium text-danger" : ""}`}>{r.errors}{r.retries ? ` (+${r.retries} retry)` : ""}</Td>
              </tr>))}</tbody>
          </Table>
        )}
      </Panel>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Panel><PanelHeader title="Agent tool calls" sub={s && `${s.agent.runs} runs · ${s.agent.rejected_tool_calls} ${t.agent.rejectedCalls}`} />
          <div className="p-4">{s && <BarList items={Object.entries(s.agent.tool_usage).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k, value: v }))} />}</div></Panel>
        <Panel><PanelHeader title={t.invoice.warnings} />
          <div className="p-4">{s && <BarList color="var(--series-2)" items={Object.entries(s.extraction.validation_warnings).map(([k, v]) => ({ label: k, value: v }))} />}
            {s && Object.keys(s.extraction.validation_warnings).length === 0 && <p className="text-sm text-ink-3">—</p>}</div></Panel>
        <Panel><PanelHeader title={t.invoice.method} />
          <div className="space-y-4 p-4">{s && <BarList color="var(--series-3)" items={Object.entries(s.extraction.by_method).map(([k, v]) => ({ label: k, value: v }))} />}
            <div className="text-xs text-ink-3">Jobs: {s && Object.entries(s.jobs).map(([k, v]) => `${k} ${v}`).join(" · ")}</div></div></Panel>
      </div>
      {s && s.daily.length > 1 && (
        <Panel><PanelHeader title={t.observability.calls} /><div className="p-4">
          <Lines xKey="date" data={s.daily} series={kinds.slice(0, 4).map((k) => ({ key: k, label: k }))} /></div></Panel>
      )}
      <Panel>
        <PanelHeader title="Recent calls" actions={<Segmented value={kind} onChange={(v) => { setKind(v); setPage(1); }}
          options={[{ value: "", label: t.common.all }, ...kinds.map((k) => ({ value: k, label: k }))]} />} />
        {callsError && <ErrorState message={t.common.error} retryLabel={t.common.retry} onRetry={() => retryCalls()} />}
        <Table>
          <thead><tr><Th>{t.common.date}</Th><Th>Workflow</Th><Th>Model</Th><Th className="text-end">{t.observability.latency}</Th>
            <Th className="text-end">{t.observability.tokens}</Th><Th>{t.common.status}</Th></tr></thead>
          <tbody>{calls?.items.map((c) => (
            <tr key={c.id}>
              <Td className="text-xs text-ink-3">{dateTime(c.created_at, locale)}</Td>
              <Td className="font-mono text-xs">{c.workflow}</Td>
              <Td className="font-mono text-xs text-ink-2">{c.model}</Td>
              <Td className="text-end num">{c.latency_ms} ms</Td>
              <Td className="text-end num">{c.input_tokens !== null ? `${c.input_tokens}/${c.output_tokens}` : "—"}</Td>
              <Td><Pill tone={c.status === "ok" ? "ok" : "danger"}>{c.status}</Pill>{c.error && <span className="ms-2 text-xs text-danger">{c.error.slice(0, 60)}</span>}</Td>
            </tr>))}</tbody>
        </Table>
        {calls && <Pager page={calls.page} pages={calls.pages} total={calls.total} onPage={setPage} />}
      </Panel>
    </div>
  );
}
