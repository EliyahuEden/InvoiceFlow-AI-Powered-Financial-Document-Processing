"use client";

import { ClipboardCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { ActionLabel, FindingTag, StatusPill } from "@/components/domain";
import { Pager, RowsSkeleton, SearchBox, Segmented, type Page } from "@/components/list";
import { PageHeader } from "@/components/shell";
import { EmptyState, Panel, PanelHeader, Table, Td, Th } from "@/components/ui";
import { qs, useApi } from "@/lib/api";
import { money, relative } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Row = {
  id: string; title: string; status: string; priority: string; discrepancy_types: string[]; proposed_action: string | null;
  has_ai_summary: boolean; created_at: string; amount_at_risk: string; supplier_name: string | null; supplier_name_en: string | null;
  invoice: { id: string; invoice_number: string | null; total: string | null; currency: string | null; status: string };
};
type Resp = Page<Row> & { status_counts: Record<string, number>; pending_approvals: { approval_id: string; step: number; required_role: string;
  invoice: { id: string; invoice_number: string; total: string; currency: string }; supplier_name: string; created_at: string }[] };

export default function ExceptionsPage() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const [status, setStatus] = useState("draft,open,pending_info");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading } = useApi<Resp>(`/api/exceptions${qs({ status, q, page, page_size: 20 })}`);
  const onQ = useCallback((v: string) => { setQ(v); setPage(1); }, []);
  const c = data?.status_counts ?? {};
  const label = (ty: string) => (t.finding as Record<string, string>)[ty] ?? ty;

  return (
    <div className="space-y-5">
      <PageHeader title={t.exceptions.title} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)]">
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-3">
            <Segmented value={status} onChange={(v) => { setStatus(v); setPage(1); }} options={[
              { value: "draft,open,pending_info", label: t.status.open, count: (c.open ?? 0) + (c.draft ?? 0) + (c.pending_info ?? 0) },
              { value: "approved", label: t.exceptions.decided, count: (c.approved ?? 0) },
              { value: "rejected", label: t.status.rejected, count: c.rejected ?? 0 },
              { value: "resolved", label: t.status.resolved, count: c.resolved ?? 0 },
            ]} />
            <SearchBox value={q} onChange={onQ} placeholder={t.common.search} />
          </div>
          <Table>
            <thead><tr><Th>{t.exceptions.queue}</Th><Th>{t.common.supplier}</Th><Th className="text-end">{t.recon.atRisk}</Th>
              <Th>{t.exceptions.proposed}</Th><Th>{t.common.status}</Th><Th>{t.common.created}</Th></tr></thead>
            <tbody>
              {isLoading && !data ? <RowsSkeleton cols={6} /> : data?.items.map((e) => (
                <tr key={e.id} className="cursor-pointer hover:bg-sunken/70" onClick={() => router.push(`/exceptions/${e.id}`)}>
                  <Td className="max-w-[20rem]">
                    <Link href={`/exceptions/${e.id}`} onClick={(ev) => ev.stopPropagation()} className="block font-medium text-ink hover:text-accent">
                      {label(e.discrepancy_types[0] ?? "")} <span className="ltr font-mono text-sm text-ink-2">· {e.invoice.invoice_number}</span>
                    </Link>
                    <span className="mt-1 flex flex-wrap gap-1">
                      {e.discrepancy_types.slice(1, 3).map((ty) => <FindingTag key={ty} type={ty} />)}
                      {e.has_ai_summary && <span className="inline-flex items-center gap-1 text-2xs font-medium text-ai"><Sparkles className="h-3 w-3" />AI</span>}
                    </span>
                  </Td>
                  <Td className="max-w-[12rem]"><span dir="auto" className="block truncate text-ink-2">{locale === "en" && e.supplier_name_en ? e.supplier_name_en : e.supplier_name}</span></Td>
                  <Td className="text-end font-medium text-danger"><span className="ltr">{Number(e.amount_at_risk) ? money(e.amount_at_risk, e.invoice.currency) : "—"}</span></Td>
                  <Td className="text-sm text-ink-2"><ActionLabel action={e.proposed_action} /></Td>
                  <Td><StatusPill status={e.status} /></Td>
                  <Td className="whitespace-nowrap text-xs text-ink-3">{relative(e.created_at, locale)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          {data && data.items.length === 0 && <EmptyState icon={<ClipboardCheck className="h-8 w-8" />} title={t.exceptions.empty} />}
          {data && <Pager page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
        </Panel>
        <Panel className="self-start">
          <PanelHeader title={t.exceptions.approvals} />
          <ul className="divide-y divide-line">
            {data?.pending_approvals.length === 0 && <li className="px-4 py-6 text-center text-sm text-ink-3">—</li>}
            {data?.pending_approvals.map((a) => (
              <li key={a.approval_id}>
                <Link href={`/invoices/${a.invoice.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-sunken/70">
                  <span className="min-w-0">
                    <span className="ltr block font-mono text-sm text-ink">{a.invoice.invoice_number}</span>
                    <span dir="auto" className="block truncate text-xs text-ink-3">{a.supplier_name} · {t.invoice.step} {a.step} · {(t.roles as Record<string, string>)[a.required_role]}</span>
                  </span>
                  <span className="ltr shrink-0 font-medium">{money(a.invoice.total, a.invoice.currency)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
