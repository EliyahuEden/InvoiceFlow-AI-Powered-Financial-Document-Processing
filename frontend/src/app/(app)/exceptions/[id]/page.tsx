"use client";

import { ArrowLeft, ArrowRight, Bot, CheckCircle2, FileText, MessageSquare, ScanLine, Scale } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { AiSummaryView } from "@/components/ai-summary";
import { DecisionPanel, type Decision } from "@/components/decision-panel";
import { DiscrepancyTable } from "@/components/discrepancy-table";
import { DocumentViewer, type Highlight } from "@/components/document-viewer";
import { FindingTag, PriorityBadge, ReasonText, StatusPill } from "@/components/domain";
import { useSession, type Me } from "@/components/session";
import { Button, EmptyState, ErrorState, Panel, PanelHeader, Skeleton, Textarea } from "@/components/ui";
import { api, ApiError, qs, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { markReviewed } from "@/lib/review";
import type { AiSummary, InvoiceDetail, ReviewNext, ReviewQueueItem } from "@/lib/types";
import { isTyping } from "@/lib/nav";
import { useUnsavedWork } from "@/lib/use-unsaved-work";
import { label } from "@/lib/i18n/label";

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
  // N skips to the next priority item (through the unsaved-work guard); E / D jump between zones.
  // Decisions are deliberately not bound to keys.
  const skipRef = useRef(skip);
  skipRef.current = skip;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target) || busy) return;
      const k = event.key.toLowerCase();
      if (k === "n" && open) { event.preventDefault(); void skipRef.current(); }
      else if (k === "e") { event.preventDefault(); jumpTo("review-document"); }
      else if (k === "d") { event.preventDefault(); jumpTo("review-decision"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy]);
  const decide = async (decision: Decision) => {
    setBusy(decision);
    try {
      await api.post(`/api/exceptions/${e.id}/decision`, {
        decision, note: draft.note.trim() || null, action_override: decision === "approve" ? draft.override || null : null,
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
    catch (error) {
      toast.error(error instanceof ApiError && error.status === 429 ? t.login.rateLimited
        : error instanceof Error ? error.message : t.common.error);
    } finally { setBusy(null); }
  };
  if (queueClear) return <Panel data-testid="queue-clear"><EmptyState icon={<CheckCircle2 className="h-8 w-8 text-ok" />}
    title={t.review.clearTitle} body={t.review.clearBody}
    action={<Button asChild variant="primary"><Link href="/exceptions">{t.review.backToQueue}</Link></Button>} /></Panel>;
  const highlights: Highlight[] = invoice?.lines.filter((line) => line.source?.bbox?.length === 4
    && invoice.discrepancies.some((finding) => finding.status === "open" && finding.invoice_line_id === line.id)).map((line) => ({
    id: line.id, page: line.source.page ?? 1, bbox: line.source.bbox!,
    tone: invoice.discrepancies.some((finding) => finding.status === "open" && finding.invoice_line_id === line.id && finding.severity === "critical") ? "finding" : "field", label: line.description,
  })) ?? [];
  const titleFinding = e.discrepancy_types[0];
  const supplierName = (locale === "en" && (invoice?.supplier_name_en || current?.supplier_name_en))
    || invoice?.supplier_name || current?.supplier_name || invoice?.supplier_name_raw;
  const positionTotal = inReviewQueue ? summary?.needs_review : queue?.total;
  function jumpTo(id: "review-document" | "review-decision") {
    const zone = document.getElementById(id);
    zone?.focus({ preventScroll: true });
    zone?.scrollIntoView({ block: "start" });
  }

  return <div className="min-w-0 space-y-4">
    <header className="command-hero min-w-0 space-y-3 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
        <Link href="/exceptions" className="inline-flex items-center gap-1 font-medium hover:underline"><ArrowLeft className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden />{t.review.backToQueue}</Link>
        {e.invoice_number && <><span aria-hidden>/</span><bdi>{e.invoice_number}</bdi></>}
      </div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0 flex-[1_1_18rem]">
          <h1 className="break-words text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            <bdi>{supplierName || e.invoice_number || e.title}</bdi>{titleFinding && <> · {label(t.finding, titleFinding)}</>}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {current && <PriorityBadge level={current.priority.level} />}
            <StatusPill status={e.status} />
            {current && positionTotal !== undefined && <span className="rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-ink-2">
              {t.review.position} <bdi className="num">{current.priority.rank}</bdi> {t.review.of} <bdi className="num">{positionTotal}</bdi></span>}
            {e.discrepancy_types.slice(1).map((type) => <FindingTag key={type} type={type} />)}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button className="xl:hidden" onClick={() => jumpTo("review-decision")}><Scale className="h-4 w-4" aria-hidden />{open ? t.agent.decision : t.review.viewDecision}</Button>
          {open && <Button onClick={skip} loading={busy === "next"} disabled={!!busy}>{t.review.skip}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Button>}
        </div>
      </div>
    </header>
    <div className="workspace-layout">
      <section id="review-document" tabIndex={-1} aria-labelledby="review-document-title" className="workspace-evidence command-panel min-w-0 scroll-mt-24">
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
          <h2 id="review-document-title" className="inline-flex items-center gap-2 text-lg font-semibold"><FileText className="h-5 w-5 text-accent" aria-hidden />{t.review.document}</h2>
          <Link href={`/invoices/${e.invoice_id}/review`} className="text-sm font-medium text-accent underline underline-offset-4">{t.review.correctedFields}</Link>
        </div>
        {invoiceError ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => retryInvoice()} retryLabel={t.common.retry} /></div>
          : !invoice ? <div className="p-4"><Skeleton className="h-[32rem] w-full" /></div>
          : invoice.document ? <DocumentViewer key={invoice.document.id} documentId={invoice.document.id}
            pageCount={invoice.document.page_count ?? 1} filename={invoice.filename || invoice.document.filename} highlights={highlights}
            activeId={activeLine} className="mx-2 mb-2 max-h-[60vh] sm:mx-3 sm:mb-3 xl:max-h-[calc(100dvh-10rem)]" />
          : <p className="p-4 text-sm text-ink-2">{t.review.noDocument}</p>}
      </section>
      <div className="workspace-findings min-w-0 space-y-4">
        {invoice && <DiscrepancyTable invoice={invoice} onSelectLine={(lineId) => {
          setActiveLine(lineId);
          if (window.matchMedia("(max-width: 1279px)").matches) jumpTo("review-document");
        }} />}
        {e.ai_summary && !e.ai_summary.stale ? <AiSummaryView s={e.ai_summary} currency={invoice?.currency ?? current?.currency} /> : <Panel><EmptyState icon={<Bot className="h-8 w-8 text-ai" />} title={e.ai_summary?.stale ? t.exceptions.staleAi : t.exceptions.noAi}
          action={can("agent:run") && <Button variant="ai" onClick={runAgent} loading={busy === "agent"}>{t.exceptions.runAgent}</Button>} /></Panel>}
        {e.agent_run && <Button asChild className="h-auto w-full whitespace-normal py-2" variant="ai"><Link href={`/investigations/${e.agent_run.id}`}>
          <Bot className="h-4 w-4 shrink-0" aria-hidden />{t.agent.trace}<StatusPill status={e.agent_run.status} />
        </Link></Button>}
        {current && <Panel><PanelHeader title={t.review.reason} /><ul className="space-y-1.5 px-4 py-3 text-sm text-ink-2">
          {current.priority.reasons.map((reason, index) => <li key={`${reason.code}:${index}`}><ReasonText reason={reason} currency={current.currency} /></li>)}
        </ul></Panel>}
        <Panel><PanelHeader title={<span className="inline-flex items-center gap-2"><MessageSquare className="h-4 w-4" aria-hidden />{t.exceptions.comments}</span>} />
          <ul className="divide-y divide-line">{e.comments.map((comment) => <li key={comment.id} className="px-4 py-3">
            <p className="text-xs text-ink-3"><bdi>{comment.author?.full_name}</bdi> · <bdi>{dateTime(comment.created_at, locale)}</bdi></p>
            <p className="mt-1 whitespace-pre-wrap break-words text-sm" dir="auto">{comment.body}</p>
          </li>)}</ul>
          {can("exception:comment") && <div className="space-y-2 p-3">
            <Textarea dir="auto" value={draft.comment} onChange={(event) => change("comment", event.target.value)} className="min-h-12"
              aria-label={t.exceptions.addNote} placeholder={t.exceptions.addNote} maxLength={4000} disabled={!!busy} />
            <Button onClick={addComment} loading={busy === "comment"} disabled={!!busy || !draft.comment.trim()}>{t.exceptions.addNote}</Button>
          </div>}
        </Panel>
      </div>
      <aside id="review-decision" tabIndex={-1} aria-label={t.agent.decision} className="workspace-decision min-w-0 scroll-mt-24 space-y-2">
        <Button className="xl:hidden" onClick={() => jumpTo("review-document")}><ScanLine className="h-4 w-4" aria-hidden />{t.review.returnEvidence}</Button>
        {open ? <DecisionPanel proposedAction={e.proposed_action} detail={e.proposed_action_detail} allowedActions={e.allowed_actions}
          note={draft.note} override={draft.override} target={draft.target} onNote={(value) => change("note", value)}
          onOverride={(value) => change("override", value)} onTarget={(value) => change("target", value)} onDecide={decide}
          busy={busy} canDecide={can("exception:decide")} canRequestInfo={can("exception:comment") && !restricted} restricted={restricted} />
          : <Panel><PanelHeader title={t.agent.decision} /><div className="space-y-3 p-4"><p className="inline-flex items-center gap-2 font-medium text-ok"><CheckCircle2 className="h-4 w-4" aria-hidden />{t.exceptions.decided}</p>
            {e.decided_at && <p className="text-sm text-ink-2"><bdi>{e.decided_by?.full_name}</bdi> · <bdi>{dateTime(e.decided_at, locale)}</bdi></p>}
            {e.decision_note && <p className="whitespace-pre-wrap break-words text-sm" dir="auto">{e.decision_note}</p>}
            {draft.note.trim() && <div className="border-t border-line pt-3">
              <p className="text-xs text-warn">{t.review.savedDraft}</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-sm" dir="auto">{draft.note}</p>
            </div>}
            <Button variant="primary" onClick={skip} disabled={!!busy}>{t.review.reviewNext}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Button></div></Panel>}
      </aside>
    </div>
  </div>;
}
