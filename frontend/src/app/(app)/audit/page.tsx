"use client";

import { ShieldCheck, ShieldX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { AuditList, type AuditEntry } from "@/components/audit-list";
import { Pager, Segmented, type Page } from "@/components/list";
import { PageHeader } from "@/components/shell";
import { Button, ErrorState, Panel, Skeleton } from "@/components/ui";
import { api, qs, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function AuditPage() {
  const { t } = useI18n();
  const [actor, setActor] = useState("");
  const [page, setPage] = useState(1);
  const [verify, setVerify] = useState<{ valid: boolean; checked: number } | null>(null);
  const [checking, setChecking] = useState(false);
  const { data, error, mutate } = useApi<Page<AuditEntry>>(`/api/audit${qs({ actor_type: actor, page, page_size: 30 })}`);
  return (
    <div className="space-y-4">
      <PageHeader title={t.audit.title} actions={
        <>
          {verify && (verify.valid
            ? <span className="inline-flex items-center gap-1.5 text-sm text-ok"><ShieldCheck className="h-4 w-4" />{t.audit.valid} · {verify.checked}</span>
            : <span className="inline-flex items-center gap-1.5 text-sm text-danger"><ShieldX className="h-4 w-4" />{t.audit.broken}</span>)}
          <Button variant="primary" loading={checking} onClick={async () => {
            setChecking(true);
            try { setVerify(await api.get("/api/audit/verify")); }
            catch { setVerify(null); toast.error(t.common.error); } finally { setChecking(false); }
          }}>{t.audit.verify}</Button>
        </>
      } />
      <Panel>
        <div className="border-b border-line p-4">
          <Segmented value={actor} onChange={(v) => { setActor(v); setPage(1); }} options={[
            { value: "", label: t.common.all }, { value: "user", label: "User" }, { value: "agent", label: "AI agent" }, { value: "system", label: "System" }]} />
        </div>
        {error ? <div className="p-4"><ErrorState onRetry={() => mutate()} retryLabel={t.common.retry} message={error.status === 403 ? "Your role cannot read the audit trail." : t.common.error} /></div> :
          !data ? <div className="space-y-2 p-4"><Skeleton /><Skeleton /><Skeleton /></div> : <AuditList items={data.items} />}
        {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </Panel>
    </div>
  );
}
