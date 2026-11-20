"use client";

import { CheckCircle2, CircleX, Pause, Wrench } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { AiSummaryView } from "@/components/ai-summary";
import { ActionLabel, Pill, StatusPill } from "@/components/domain";
import { PageHeader } from "@/components/shell";
import { cx, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { AiSummary } from "@/lib/types";

type Step = { tool: string; source: string; status: string; input: Record<string, unknown>; output_preview?: string; error?: string; latency_ms: number; note?: string };
type Run = { id: string; status: string; mode: string; prompt_version: string; thread_id: string; steps: Step[]; invoice_id: string;
  invoice_number: string | null; created_at: string; updated_at: string;
  result: { report: AiSummary | null; proposed_action: string | null; path: string[] | null; decision: Record<string, string> | null } | null };

const NODES = ["load_context", "reconcile", "investigate", "explain", "draft_exception", "human_review", "finalize"];

export default function RunDetail() {
  const { t, locale } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: r } = useApi<Run>(`/api/agent/runs/${id}`, { refreshInterval: (d) => (d && ["queued", "running"].includes(d.status) ? 2000 : 0) });
  const [open, setOpen] = useState<number | null>(null);
  if (!r) return <Skeleton className="h-96 w-full" />;
  const path = r.result?.path ?? [];
  const visited = (n: string) => path.some((p) => p.startsWith(n));
  return (
    <div className="space-y-5">
      <PageHeader back={{ href: "/investigations", label: t.agent.title }}
        title={<span className="flex items-center gap-3">{t.agent.title} <Link href={`/invoices/${r.invoice_id}`} className="ltr font-mono text-xl text-ink-2 hover:text-accent">{r.invoice_number}</Link><StatusPill status={r.status} /></span>}
        sub={<span className="font-mono text-xs">{r.mode} · {r.prompt_version} · thread {r.thread_id}</span>} />
      <Panel className="overflow-x-auto p-4">
        <p className="mb-3 text-sm font-semibold">{t.agent.path} <span className="font-normal text-ink-3">· LangGraph · PostgreSQL checkpoints</span></p>
        <ol className="flex min-w-max items-center gap-2">
          {NODES.map((n, i) => (
            <li key={n} className="flex items-center gap-2">
              <span className={cx("rounded-md border px-2.5 py-1.5 font-mono text-xs",
                visited(n) ? (n === "human_review" && r.status === "awaiting_approval" ? "border-ai bg-ai-soft text-ai" : "border-accent/40 bg-accent-soft text-accent-ink") : "border-line text-ink-3")}>
                {n}{n === "human_review" && r.status === "awaiting_approval" && <Pause className="ms-1 inline h-3 w-3" aria-label="paused" />}
              </span>
              {i < NODES.length - 1 && <span className="h-px w-5 bg-line-strong" aria-hidden />}
            </li>
          ))}
        </ol>
        {r.result?.decision && (
          <p className="mt-3 text-sm text-ink-2">{t.agent.decision}: <b className="text-ink">{r.result.decision.decision}</b> · {r.result.decision.by}
            {r.result.decision.note && <span dir="auto"> — {r.result.decision.note}</span>}</p>
        )}
      </Panel>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div>{r.result?.report ? <AiSummaryView s={r.result.report} /> : <Skeleton className="h-64 w-full" />}</div>
        <Panel className="self-start">
          <PanelHeader title={t.agent.trace} sub={<span>{r.steps.length} {t.agent.tools} · {t.agent.proposed}: <ActionLabel action={r.result?.proposed_action} /></span>} />
          <ol className="divide-y divide-line">
            {r.steps.map((s, i) => (
              <li key={i}>
                <button className="flex w-full items-center gap-2.5 px-4 py-2 text-start hover:bg-sunken/60" onClick={() => setOpen(open === i ? null : i)}>
                  {s.status === "ok" ? <CheckCircle2 className="h-4 w-4 text-ok" /> : s.status === "rejected" ? <CircleX className="h-4 w-4 text-danger" /> : <Wrench className="h-4 w-4 text-ink-3" />}
                  <span className="font-mono text-sm text-ink">{s.tool}</span>
                  <Pill tone={s.source === "llm" ? "ai" : "neutral"}>{s.source}</Pill>
                  <span className="ms-auto text-xs text-ink-3 num">{s.latency_ms} ms</span>
                </button>
                {open === i && (
                  <div className="space-y-2 px-4 pb-3">
                    <pre className="overflow-x-auto rounded bg-sunken p-2 font-mono text-2xs text-ink-2" dir="ltr">{JSON.stringify(s.input, null, 2)}</pre>
                    {s.error && <p className="text-xs text-danger">{s.error}</p>}
                    {s.output_preview && <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-sunken p-2 font-mono text-2xs text-ink-2" dir="ltr">{s.output_preview}</pre>}
                  </div>
                )}
              </li>
            ))}
          </ol>
          <p className="border-t border-line px-4 py-2 text-xs text-ink-3">{dateTime(r.created_at, locale)} → {dateTime(r.updated_at, locale)}</p>
        </Panel>
      </div>
    </div>
  );
}
