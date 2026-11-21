"use client";

import { Bot } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ActionLabel, StatusPill } from "@/components/domain";
import { Pager, RowsSkeleton, type Page } from "@/components/list";
import { PageHeader } from "@/components/shell";
import { EmptyState, ErrorState, Panel, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { relative } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Run = { id: string; status: string; mode: string; prompt_version: string; invoice_id: string; invoice_number: string | null;
  tool_calls: number; proposed_action: string | null; created_at: string };

export default function InvestigationsPage() {
  const { t, locale } = useI18n();
  const [page, setPage] = useState(1);
  const { data, isLoading, error, mutate } = useApi<Page<Run>>(`/api/agent/runs${qs({ page, page_size: 25 })}`, { refreshInterval: 5000 });
  return (
    <div className="space-y-4">
      <PageHeader title={t.agent.title} />
      {error && <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />}
      <Panel>
        <Table>
          <thead><tr><Th>{t.inbox.number}</Th><Th>{t.common.status}</Th><Th>{t.agent.proposed}</Th><Th className="text-end">{t.agent.tools}</Th>
            <Th>{t.recon.mode}</Th><Th>{t.common.created}</Th></tr></thead>
          <tbody>
            {isLoading && !data ? <RowsSkeleton cols={6} /> : data?.items.map((r) => (
              <tr key={r.id} className="hover:bg-sunken/70">
                <Td><Link href={`/investigations/${r.id}`} className="ltr font-mono text-sm font-medium text-accent hover:underline">{r.invoice_number ?? r.invoice_id.slice(0, 8)}</Link></Td>
                <Td><StatusPill status={r.status} /></Td>
                <Td className="text-sm text-ink-2"><ActionLabel action={r.proposed_action} /></Td>
                <Td className="text-end num">{r.tool_calls}</Td>
                <Td><span className="font-mono text-xs text-ink-3">{r.mode} · {r.prompt_version}</span></Td>
                <Td className="text-xs text-ink-3">{relative(r.created_at, locale)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {data && data.items.length === 0 && <EmptyState icon={<Bot className="h-8 w-8" />} title={t.common.noResults} />}
        {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Panel>
    </div>
  );
}
