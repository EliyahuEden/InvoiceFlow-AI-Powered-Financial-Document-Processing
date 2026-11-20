"use client";

import { Bot, Check, HelpCircle, MessageSquare, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { AiSummaryView } from "@/components/ai-summary";
import { ActionLabel, FindingTag, StatusPill } from "@/components/domain";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, EmptyState, ErrorState, Field, Panel, PanelHeader, Select, Skeleton, Textarea } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { AiSummary } from "@/lib/types";

type Exc = {
  id: string; title: string; status: string; priority: string; discrepancy_types: string[]; proposed_action: string | null;
  proposed_action_detail: string | null; ai_summary: AiSummary | null; created_by_agent: boolean; decision: string | null;
  decision_note: string | null; decided_by: { full_name: string } | null; decided_at: string | null; created_at: string;
  invoice_id: string; invoice_number: string | null; agent_run: { id: string; status: string; mode: string } | null;
  comments: { id: string; body: string; kind: string; author: { full_name: string } | null; created_at: string }[];
  allowed_actions: string[];
};

export default function ExceptionDetail() {
  const { t, locale } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { can } = useSession();
  const { data: e, error, mutate } = useApi<Exc>(`/api/exceptions/${id}`, {
    refreshInterval: (d) => (d && !d.ai_summary ? 3000 : 0),
  });
  const [note, setNote] = useState("");
  const [override, setOverride] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!e) return <Skeleton className="h-[500px] w-full" />;
  const open = ["draft", "open", "pending_info"].includes(e.status);
  const label = (ty: string) => (t.finding as Record<string, string>)[ty] ?? ty;

  const decide = async (decision: string) => {
    setBusy(decision);
    try {
      await api.post(`/api/exceptions/${e.id}/decision`, { decision, note: note || null, action_override: override || null });
      toast.success(decision === "approve" ? t.exceptions.approve : decision === "reject" ? t.exceptions.reject : t.exceptions.requestInfo);
      setNote("");
      mutate();
    } catch (err) {
      toast.error(err instanceof ApiError ? String(err.message) : t.common.error);
    } finally { setBusy(null); }
  };
  const addComment = async () => {
    if (!comment.trim()) return;
    setBusy("comment");
    try { await api.post(`/api/exceptions/${e.id}/comments`, { body: comment }); setComment(""); mutate(); }
    catch (err) { toast.error(String((err as Error).message)); } finally { setBusy(null); }
  };
  const runAgent = async () => {
    try { await api.post(`/api/invoices/${e.invoice_id}/investigate`); toast.success(t.exceptions.runAgent); mutate(); }
    catch (err) { toast.error(String((err as Error).message)); }
  };

  return (
    <div>
      <PageHeader back={{ href: "/exceptions", label: t.exceptions.title }}
        title={<span className="flex flex-wrap items-center gap-3">{label(e.discrepancy_types[0] ?? "")}
          <Link href={`/invoices/${e.invoice_id}`} className="ltr font-mono text-xl text-ink-2 hover:text-accent">{e.invoice_number}</Link>
          <StatusPill status={e.status} /></span>}
        sub={<span className="flex flex-wrap gap-1.5">{e.discrepancy_types.map((ty) => <FindingTag key={ty} type={ty} />)}</span>}
        actions={<Button asChild><Link href={`/invoices/${e.invoice_id}/reconciliation`}>{t.invoice.tabs.reconciliation}</Link></Button>} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div>
          {e.ai_summary ? <AiSummaryView s={e.ai_summary} /> : (
            <Panel><EmptyState icon={<Bot className="h-8 w-8 text-ai" />} title={t.exceptions.noAi}
              action={can("agent:run") && <Button variant="ai" onClick={runAgent}><Bot className="h-4 w-4" />{t.exceptions.runAgent}</Button>} /></Panel>
          )}
        </div>
        <div className="space-y-5">
          <Panel>
            <PanelHeader title={t.exceptions.decide} />
            <div className="space-y-4 p-4">
              <div className="rounded-md bg-sunken p-3">
                <p className="text-xs text-ink-3">{t.exceptions.proposed} · {t.ai.deterministic}</p>
                <p className="mt-0.5 font-medium text-ink"><ActionLabel action={override || e.proposed_action} /></p>
                {e.proposed_action_detail && !override && <p className="mt-0.5 text-sm text-ink-2">{e.proposed_action_detail}</p>}
              </div>
              {open && can("exception:decide") && (
                <>
                  <Field label={t.exceptions.changeAction} htmlFor="override">
                    <Select id="override" className="w-full" value={override} onChange={(ev) => setOverride(ev.target.value)}>
                      <option value="">—</option>
                      {e.allowed_actions.map((a) => <option key={a} value={a}>{(t.action as Record<string, string>)[a] ?? a}</option>)}
                    </Select>
                  </Field>
                  <Field label={t.exceptions.note} htmlFor="note">
                    <Textarea id="note" value={note} onChange={(ev) => setNote(ev.target.value)} placeholder={t.exceptions.notePlaceholder} />
                  </Field>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="primary" loading={busy === "approve"} disabled={!!busy} onClick={() => decide("approve")}><Check className="h-4 w-4" />{t.exceptions.approve}</Button>
                    <Button variant="danger" loading={busy === "reject"} disabled={!!busy || !note.trim()} onClick={() => decide("reject")} title={!note.trim() ? t.exceptions.notePlaceholder : undefined}>
                      <X className="h-4 w-4" />{t.exceptions.reject}</Button>
                    <Button loading={busy === "request_info"} disabled={!!busy} onClick={() => decide("request_info")}><HelpCircle className="h-4 w-4" />{t.exceptions.requestInfo}</Button>
                  </div>
                </>
              )}
              {open && !can("exception:decide") && can("exception:comment") && (
                <Button loading={busy === "request_info"} onClick={() => decide("request_info")}><HelpCircle className="h-4 w-4" />{t.exceptions.requestInfo}</Button>
              )}
              {!open && e.decided_at && (
                <div className="text-sm">
                  <p className="text-ink-2">{t.exceptions.decided}: <b className="text-ink">{e.decision}</b> · {e.decided_by?.full_name} · {dateTime(e.decided_at, locale)}</p>
                  {e.decision_note && <p className="mt-1 text-ink" dir="auto">{e.decision_note}</p>}
                </div>
              )}
            </div>
          </Panel>
          <Panel>
            <PanelHeader title={<span className="inline-flex items-center gap-2"><MessageSquare className="h-4 w-4 text-ink-3" />{t.exceptions.comments}</span>} />
            <ul className="divide-y divide-line">
              {e.comments.map((c) => (
                <li key={c.id} className="px-4 py-2.5">
                  <p className="text-xs text-ink-3">{c.author?.full_name} · {dateTime(c.created_at, locale)} {c.kind !== "note" && `· ${c.kind}`}</p>
                  <p className="mt-0.5 text-sm text-ink" dir="auto">{c.body}</p>
                </li>
              ))}
            </ul>
            {can("exception:comment") && (
              <div className="flex gap-2 border-t border-line p-3">
                <Textarea value={comment} onChange={(ev) => setComment(ev.target.value)} className="min-h-10" placeholder={t.exceptions.addNote} />
                <Button onClick={addComment} loading={busy === "comment"} disabled={!comment.trim()}>{t.exceptions.addNote}</Button>
              </div>
            )}
          </Panel>
          {e.agent_run && (
            <Link href={`/investigations/${e.agent_run.id}`} className="flex items-center justify-between rounded-lg border border-ai-line bg-ai-soft/50 px-4 py-3 text-sm hover:bg-ai-soft">
              <span className="inline-flex items-center gap-2 text-ai"><Bot className="h-4 w-4" />{t.agent.trace}</span>
              <StatusPill status={e.agent_run.status} />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
