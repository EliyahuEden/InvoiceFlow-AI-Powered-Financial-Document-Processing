"use client";

import { useParams } from "next/navigation";
import { AuditList, type AuditEntry } from "@/components/audit-list";
import type { Page } from "@/components/list";
import { Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function HistoryPage() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data, error } = useApi<Page<AuditEntry>>(`/api/audit?entity_id=${id}&page_size=100`);
  return (
    <Panel>
      <PanelHeader title={t.audit.title} />
      {error ? <p className="p-4 text-sm text-ink-3">{error.status === 403 ? "Your role cannot read the audit trail." : t.common.error}</p> :
        !data ? <div className="space-y-2 p-4"><Skeleton /><Skeleton /><Skeleton /></div> : <AuditList items={data.items} />}
    </Panel>
  );
}
