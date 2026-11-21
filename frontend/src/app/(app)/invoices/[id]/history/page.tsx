"use client";

import { useParams } from "next/navigation";
import { History } from "lucide-react";
import { AuditList, type AuditEntry } from "@/components/audit-list";
import type { Page } from "@/components/list";
import { EmptyState, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function HistoryPage() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data, error, mutate } = useApi<Page<AuditEntry>>(`/api/audit?entity_id=${id}&page_size=100`);
  return (
    <Panel className="command-panel min-w-0">
      <PanelHeader title={<span className="inline-flex items-center gap-2"><History className="h-5 w-5 text-accent-ink" />{t.audit.title}</span>} />
      {error ? <div className="p-4"><ErrorState message={error.status === 403 ? t.invoice.auditRestricted : t.common.error}
        onRetry={error.status === 403 ? undefined : () => mutate()} retryLabel={t.common.retry} /></div> :
        !data ? <div className="space-y-2 p-4"><Skeleton /><Skeleton /><Skeleton /></div> :
        data.items.length ? <AuditList items={data.items} /> : <EmptyState title={t.common.none} />}
    </Panel>
  );
}
