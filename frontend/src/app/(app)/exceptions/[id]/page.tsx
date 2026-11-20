"use client";

import { ArrowLeft, Bot, CheckCircle2, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AiSummaryView } from "@/components/ai-summary";
import { DecisionPanel, type Decision } from "@/components/decision-panel";
import { DiscrepancyTable } from "@/components/discrepancy-table";
import { DocumentViewer, type Highlight } from "@/components/document-viewer";
import { FindingTag, PriorityBadge, ReasonText, StatusPill } from "@/components/domain";
import { useSession, type Me } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, EmptyState, ErrorState, Panel, PanelHeader, Skeleton, Textarea } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { markReviewed } from "@/lib/review";
import type { AiSummary, InvoiceDetail, ReviewNext, ReviewQueueItem } from "@/lib/types";
import { useUnsavedWork } from "@/lib/use-unsaved-work";

type Exc = {
  id: string; title: string; status: string; priority: string; discrepancy_types: string[]; proposed_action: string | null;
  proposed_action_detail: string | null; ai_summary: AiSummary | null; decision: string | null;
  decision_note: string | null; decided_by: { full_name: string } | null; decided_at: string | null; created_at: string;
  invoice_id: string; invoice_number: string | null; agent_run: { id: string; status: string; mode: string } | null;
  comments: { id: string; body: string; kind: string; author: { id?: string; full_name: string } | null; created_at: string }[];
  allowed_actions: string[];
};
type Draft = { note: string; override: string; target: string; comment: string };
const EMPTY_DRAFT: Draft = { note: "", override: "", target: "", comment: "" };
function loadDraft(key: string): Draft {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) ?? "null");
    return Object.fromEntries(Object.entries(EMPTY_DRAFT).map(([name, value]) =>
      [name, typeof saved?.[name] === "string" ? saved[name] : value])) as Draft;
  } catch { return { ...EMPTY_DRAFT }; }
}

export default function ExceptionDetail() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { me } = useSession();
  const { data: e, error, mutate } = useApi<Exc>(`/api/exceptions/${id}`, {
    refreshInterval: (data) => (data && !data.ai_summary && ["open", "draft"].includes(data.status) ? 3000 : 0),
  });
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!e || !me) return <Skeleton className="h-[500px] w-full" />;
  return <Workspace key={`${me.organization.id}:${me.user.id}:${e.id}`} exception={e} me={me} refresh={() => mutate()} />;
}

function Workspace({ exception: e, me, refresh }: { exception: Exc; me: Me; refresh: () => void }) {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const router = useRouter();
  const key = `invoiceflow:draft:${me.organization.id}:${me.user.id}:${e.id}`;
  const [draft, setDraft] = useState<Draft>(() => loadDraft(key));
  const [busy, setBusy] = useState<string | null>(null);
  const [queueClear, setQueueClear] = useState(false);
  const [recorded, setRecorded] = useState(false);
  const [activeLine, setActiveLine] = useState<string | null>(null);
  const { data: invoice, error: invoiceError, mutate: retryInvoice } = useApi<InvoiceDetail>(`/api/invoices/${e.invoice_id}`);
  const inReviewQueue = ["open", "escalated"].includes(e.status);
  const { data: queue } = useApi<{ items: ReviewQueueItem[]; total: number }>(
    `/api/review/queue${qs({ q: e.invoice_number ?? undefined, status: inReviewQueue ? "open,escalated" : e.status, page_size: 100 })}`);
  const { data: summary } = useApi<{ needs_review: number }>("/api/review/summary");
  const current = queue?.items.find((item) => item.exception_id === e.id);
  const dirty = Object.values(draft).some((value) => value.trim().length > 0);
  const navigation = useUnsavedWork(dirty, t.review.unsavedChanges);
  const open = !recorded && ["draft", "open", "pending_info", "escalated"].includes(e.status);
  const escalator = e.comments.filter((comment) => comment.kind === "escalation")
    .sort((a, b) => a.created_at.localeCompare(b.created_at)).at(-1)?.author?.id;
  const restricted = e.status === "escalated" && (me.role !== "admin" || escalator === me.user.id);
  useEffect(() => {
    try {
      if (dirty) sessionStorage.setItem(key, JSON.stringify(draft));
      else sessionStorage.removeItem(key);
    } catch { /* The navigation guard still protects drafts when storage is unavailable. */ }
  }, [draft, dirty, key]);
  useEffect(() => {
    try { sessionStorage.setItem("invoiceflow:current", e.id); } catch { /* Session progress is optional. */ }
  }, [e.id]);
  const change = (field: keyof Draft, value: string) => setDraft((previous) => ({ ...previous, [field]: value }));
  const next = async (handled = false) => {
    const result = await api.get<ReviewNext>(`/api/review/next?after=${e.id}`);
    navigation.allowNavigation();
    if (result.item) router.push(`/exceptions/${result.item.exception_id}`);
    else if (!handled && open) router.push("/exceptions");
    else setQueueClear(true);
  };
  const skip = async () => {
    if (!navigation.confirmNavigation()) return;
    setBusy("next");
    try { await next(); } catch { toast.error(t.common.error); } finally { setBusy(null); }
  };
  const decide = async (decision: Decision) => {
    setBusy(decision);
    try {
      await api.post(`/api/exceptions/${e.id}/decision`, {
        decision, note: draft.note.trim() || null, action_override: draft.override || null,
        target: decision === "request_info" ? draft.target : null,
      });
      setRecorded(true);
      markReviewed(e.id);
      toast.success(t.review.decisionRecorded);
      setDraft({ ...EMPTY_DRAFT, comment: draft.comment });
      try {
        if (draft.comment.trim()) sessionStorage.setItem(key, JSON.stringify({ ...EMPTY_DRAFT, comment: draft.comment }));
        else sessionStorage.removeItem(key);
      } catch { /* The recorded decision remains authoritative if storage is unavailable. */ }
      refresh();
      if (draft.comment.trim() && !window.confirm(t.review.unsavedChanges)) return;
      await next(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast.info(t.review.alreadyDecided);
        try { sessionStorage.setItem(key, JSON.stringify(draft)); } catch { /* The draft remains in memory. */ }
        try { await next(true); } catch { toast.error(t.common.error); refresh(); }
      } else toast.error(error instanceof ApiError ? error.message : t.common.error);
    } finally { setBusy(null); }
  };
  const addComment = async () => {
    if (!draft.comment.trim()) return;
    setBusy("comment");
    try { await api.post(`/api/exceptions/${e.id}/comments`, { body: draft.comment.trim() }); change("comment", ""); refresh(); }
    catch (error) { toast.error(error instanceof Error ? error.message : t.common.error); } finally { setBusy(null); }
  };
  const runAgent = async () => {
    setBusy("agent");
    try { await api.post(`/api/invoices/${e.invoice_id}/investigate`); toast.success(t.exceptions.runAgent); refresh(); }
    catch (error) { toast.error(error instanceof Error ? error.message : t.common.error); } finally { setBusy(null); }
  };
  if (queueClear) return <Panel data-testid="queue-clear"><EmptyState icon={<CheckCircle2 className="h-8 w-8 text-ok" />}
    title={t.review.clearTitle} body={t.review.clearBody}
    action={<Button asChild variant="primary"><Link href="/exceptions">{t.review.backToQueue}</Link></Button>} /></Panel>;
  const highlights: Highlight[] = invoice?.lines.filter((line) => line.source?.bbox?.length === 4
    && invoice.discrepancies.some((finding) => finding.status === "open" && finding.invoice_line_id === line.id)).map((line) => ({
    id: line.id, page: line.source.page ?? 1, bbox: line.source.bbox!,
    tone: invoice.discrepancies.some((finding) => finding.status === "open" && finding.invoice_line_id === line.id && finding.severity === "critical") ? "finding" : "field", label: line.description,
  })) ?? [];
  return <div className="space-y-5">
    <PageHeader back={{ href: "/exceptions", label: t.review.backToQueue }}
      title={<span className="flex flex-wrap items-center gap-3"><span dir="ltr">{e.invoice_number ?? e.title}</span><StatusPill status={e.status} /></span>}
      sub={<span className="flex flex-wrap items-center gap-2">
        {current && <><PriorityBadge level={current.priority.level} /><span className="text-sm text-ink-3">
          {t.review.position} {current.priority.rank} {t.review.of} {inReviewQueue ? summary?.needs_review : queue?.total}</span></>}
        {e.discrepancy_types.map((type) => <FindingTag key={type} type={type} />)}
      </span>}
      actions={<><Button className="xl:hidden" onClick={() => document.getElementById("review-decision")?.scrollIntoView({ block: "start" })}>{t.exceptions.decide}</Button>
        <Button onClick={skip} loading={busy === "next"} disabled={!!busy}>{t.review.skip}<ArrowLeft className="h-4 w-4 ltr:rotate-180" aria-hidden /></Button></>} />
    {current && <div className="flex flex-wrap gap-x-5 gap-y-1 border-y border-line py-3 text-sm text-ink-2">
      {current.priority.reasons.map((reason, index) => <ReasonText key={`${reason.code}:${index}`} reason={reason} currency={invoice?.currency} />)}
    </div>}
    <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
      <div id="review-document" className="min-w-0 scroll-mt-20 space-y-3 xl:sticky xl:top-20">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">{t.review.document}</h2>
          <Link href={`/invoices/${e.invoice_id}/review`} className="text-sm text-accent underline underline-offset-4">{t.review.correctedFields}</Link></div>
        {invoiceError ? <ErrorState message={t.common.error} onRetry={() => retryInvoice()} retryLabel={t.common.retry} />
          : !invoice ? <Skeleton className="h-[32rem] w-full" />
          : invoice.document ? <DocumentViewer key={invoice.document.id} documentId={invoice.document.id}
            pageCount={invoice.document.page_count ?? 1} filename={invoice.filename ?? undefined} highlights={highlights}
            activeId={activeLine} className="max-h-[35vh] xl:max-h-[80vh]" />
          : <Panel><p className="p-4 text-sm text-ink-2">{t.review.noDocument}</p></Panel>}
      </div>
      <div className="min-w-0 space-y-5">
        {invoice && <DiscrepancyTable invoice={invoice} onSelectLine={(lineId) => {
          setActiveLine(lineId);
          if (window.matchMedia("(max-width: 1279px)").matches) document.getElementById("review-document")?.scrollIntoView({ block: "start" });
        }} />}
        {open ? <DecisionPanel proposedAction={e.proposed_action} detail={e.proposed_action_detail} allowedActions={e.allowed_actions}
          note={draft.note} override={draft.override} target={draft.target} onNote={(value) => change("note", value)}
          onOverride={(value) => change("override", value)} onTarget={(value) => change("target", value)} onDecide={decide}
          busy={busy} canDecide={can("exception:decide")} canRequestInfo={can("exception:comment") && !restricted} restricted={restricted} />
          : <Panel><div className="space-y-2 p-4"><p className="font-medium text-ok">{t.exceptions.decided}</p>
            {e.decided_at && <p className="text-sm text-ink-2">{e.decided_by?.full_name} · {dateTime(e.decided_at, locale)}</p>}
            {e.decision_note && <p className="text-sm" dir="auto">{e.decision_note}</p>}
            {draft.note.trim() && <div className="border-t border-line pt-3">
              <p className="text-xs text-warn">{t.review.savedDraft}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm" dir="auto">{draft.note}</p>
            </div>}
            <Button onClick={skip} disabled={!!busy}>{t.review.reviewNext}</Button></div></Panel>}
        {e.ai_summary ? <AiSummaryView s={e.ai_summary} /> : <Panel><EmptyState icon={<Bot className="h-8 w-8 text-ai" />} title={t.exceptions.noAi}
          action={can("agent:run") && <Button variant="ai" onClick={runAgent} loading={busy === "agent"}>{t.exceptions.runAgent}</Button>} /></Panel>}
        <Panel><PanelHeader title={<span className="inline-flex items-center gap-2"><MessageSquare className="h-4 w-4" aria-hidden />{t.exceptions.comments}</span>} />
          <ul className="divide-y divide-line">{e.comments.map((comment) => <li key={comment.id} className="px-4 py-3">
            <p className="text-xs text-ink-3">{comment.author?.full_name} · {dateTime(comment.created_at, locale)}</p><p className="mt-1 text-sm" dir="auto">{comment.body}</p>
          </li>)}</ul>
          {can("exception:comment") && <div className="flex flex-wrap gap-2 border-t border-line p-3">
            <Textarea value={draft.comment} onChange={(event) => change("comment", event.target.value)} className="min-h-10 flex-1"
              aria-label={t.exceptions.addNote} placeholder={t.exceptions.addNote} maxLength={4000} disabled={!!busy} />
            <Button onClick={addComment} loading={busy === "comment"} disabled={!!busy || !draft.comment.trim()}>{t.exceptions.addNote}</Button>
          </div>}
        </Panel>
        {e.agent_run && <Link href={`/investigations/${e.agent_run.id}`} className="flex items-center justify-between border-t border-line py-3 text-sm text-ai">
          <span className="inline-flex items-center gap-2"><Bot className="h-4 w-4" aria-hidden />{t.agent.trace}</span><StatusPill status={e.agent_run.status} />
        </Link>}
      </div>
    </div>
  </div>;
}
