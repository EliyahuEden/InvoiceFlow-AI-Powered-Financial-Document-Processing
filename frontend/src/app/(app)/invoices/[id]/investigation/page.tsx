"use client";

import { Bot, ExternalLink } from "lucide-react";
import Link from "next/link";
import { AiSummaryView } from "@/components/ai-summary";
import { StatusPill } from "@/components/domain";
import { Button, EmptyState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { AiSummary } from "@/lib/types";
import { useInvoice } from "@/lib/use-invoice";

export default function InvestigationPage() {
  const { t, locale } = useI18n();
  const { data: inv } = useInvoice();
  const { data: exc } = useApi<{ id: string; ai_summary: AiSummary | null; status: string }>(
    inv?.exception ? `/api/exceptions/${inv.exception.id}` : null, { refreshInterval: 4000 },
  );
  if (!inv) return <Skeleton className="h-[400px] w-full" />;
  return (
    <div className="command-layout grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <div className="min-w-0">
        {exc?.ai_summary ? <AiSummaryView s={exc.ai_summary} currency={inv.currency} /> : (
          <Panel className="command-panel border-ai-line"><PanelHeader title={t.exceptions.summary} sub={t.ai.advisory} />
            <EmptyState icon={<Bot className="h-8 w-8 text-ai" />} title={t.exceptions.noAi}
              body={inv.reconciliation && inv.discrepancies.length === 0 ? t.recon.allClear : undefined} /></Panel>
        )}
      </div>
      <div className="min-w-0 space-y-4">
        {inv.exception && (
          <Panel className="command-aside p-5">
            <h2 className="text-lg font-semibold tracking-tight">{t.exceptions.decide}</h2>
            <p className="mt-2 font-medium" dir="auto">
              {(t.finding as Record<string, string>)[inv.discrepancies.find((d) => d.severity !== "info")?.type ?? ""] ?? inv.exception.title}
            </p>
            <div className="mt-3 flex items-center justify-between">
              <StatusPill status={inv.exception.status} />
              <Button asChild variant="primary" size="sm"><Link href={`/exceptions/${inv.exception.id}`}>{t.common.open}</Link></Button>
            </div>
          </Panel>
        )}
        <Panel className="command-panel">
          <PanelHeader title={t.agent.title} />
          <ul className="divide-y divide-line">
            {inv.agent_runs.length === 0 && <li className="px-4 py-3 text-sm text-ink-3">—</li>}
            {inv.agent_runs.map((r) => (
              <li key={r.id}>
                <Link href={`/investigations/${r.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-sunken/70">
                  <StatusPill status={r.status} />
                  <span className="font-mono text-xs text-ink-2">{r.mode}</span>
                  <span className="ms-auto text-xs text-ink-3">{dateTime(r.created_at, locale)}</span>
                  <ExternalLink className="h-3.5 w-3.5 text-ink-3" />
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
