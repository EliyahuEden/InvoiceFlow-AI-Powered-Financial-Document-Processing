"use client";

import { ArrowRight, BookOpenText, FileSearch, ListOrdered, Search, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { AiBlock, Citation, Pill, StatusPill } from "@/components/domain";
import { SearchBox } from "@/components/list";
import { CountBadge, FilterBar, FilterSelect, PageHeader } from "@/components/page-kit";
import { useSession } from "@/components/session";
import { Button, cx, EmptyState, ErrorState, Field, Input, Panel, PanelHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { date } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

type Doc = { id: string; title: string; doc_type: string; language: string | null; status: string; chunk_count: number; version: string | null;
  effective_date: string | null; document_id: string; supplier_name: string | null };
type Answer = { answer: string; abstained: boolean; conflict_detected: boolean; mode: string; citations: import("@/components/domain").CitationT[];
  retrieval: { mode: string; latency_ms: number; hits: { chunk_id: string; title: string; page: number; rank: number; score: number;
    scores: Record<string, number | null>; doc_type: string; document_id: string; section: string | null; preview: string; effective_date: string | null }[] } };

const EXAMPLES = ["מהי סטיית המחיר המותרת בין חשבונית להזמנת רכש?", "What are the payment terms in the BlueWave agreement?",
  "האם חרמון רשאית לחייב על כמות שטרם סופקה?", "Who approves invoices above 20,000 ILS?"];

function UploadForm({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const { data: sup } = useApi<{ items: { id: string; name: string }[] }>("/api/suppliers?page_size=100");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("supplier_agreement");
  const [supplierId, setSupplierId] = useState("");
  const [eff, setEff] = useState("");
  const [policyKey, setPolicyKey] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file); fd.append("title", title); fd.append("doc_type", docType);
    if (supplierId) fd.append("supplier_id", supplierId);
    if (eff) fd.append("effective_date", eff);
    if (policyKey) fd.append("policy_key", policyKey);
    setBusy(true);
    try { await api.post("/api/knowledge/documents", fd); toast.success(t.knowledge.upload); onDone(); }
    catch (err) { toast.error(err instanceof ApiError ? String(err.message) : t.common.error); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3 border-b border-line bg-sunken/50 p-4 md:grid-cols-6">
      <div className="md:col-span-2"><Field label={t.knowledge.file} htmlFor="kb-file"><Input id="kb-file" type="file" accept="application/pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required /></Field></div>
      <div className="md:col-span-2"><Field label={t.knowledge.titleField} htmlFor="kb-title"><Input id="kb-title" dir="auto" required value={title} onChange={(e) => setTitle(e.target.value)} /></Field></div>
      <Field label={t.knowledge.typeField} htmlFor="kb-type"><Select id="kb-type" className="w-full" value={docType} onChange={(e) => setDocType(e.target.value)}>
        {Object.entries(t.knowledge.type).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
      <Field label={t.common.supplier} htmlFor="kb-supplier"><Select id="kb-supplier" className="w-full" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
        <option value="">—</option>{sup?.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
      <Field label={t.knowledge.effective} htmlFor="kb-effective"><Input id="kb-effective" type="date" value={eff} onChange={(e) => setEff(e.target.value)} /></Field>
      <div className="md:col-span-3"><Field label={t.knowledge.policyKey} htmlFor="kb-policy-key" hint={t.knowledge.policyKeyHint}>
        <Input id="kb-policy-key" dir="ltr" pattern="[a-z0-9][a-z0-9_\-]{0,79}" maxLength={80}
          value={policyKey} onChange={(e) => setPolicyKey(e.target.value)} />
      </Field></div>
      <div className="flex items-end md:col-span-2"><Button type="submit" variant="primary" loading={busy}><Upload className="h-4 w-4" />{t.knowledge.upload}</Button></div>
    </form>
  );
}

const MODES = [{ value: "bm25", label: "BM25" }, { value: "dense", label: "Dense" }, { value: "hybrid", label: "Hybrid" }, { value: "hybrid_rerank", label: "Hybrid + rerank" }] as const;

export default function KnowledgePage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const { data, error, mutate } = useApi<{ items: Doc[]; settings: Record<string, string | null> }>("/api/knowledge/documents",
    { refreshInterval: (d) => (d?.items.some((i) => i.status === "processing") ? 3000 : 0) });
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<string>("hybrid");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);
  const [failed, setFailed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [docQ, setDocQ] = useState("");
  const [docType, setDocType] = useState("");
  const [docLang, setDocLang] = useState("");

  const ask = async (question = q) => {
    if (asking || question.trim().length < 2) return;
    setQ(question);
    setAnswer(null);
    setFailed(false);
    setAsking(true);
    try { setAnswer(await api.post<Answer>("/api/knowledge/ask", { query: question, mode, k: 5 })); }
    catch (e) { setFailed(true); toast.error(e instanceof ApiError && e.status === 429 ? t.login.rateLimited : String((e as Error).message)); }
    finally { setAsking(false); }
  };

  // the library is small (one organization's agreements and policies), so it filters in the browser
  const docs = (data?.items ?? []).filter((d) => (!docType || d.doc_type === docType) && (!docLang || d.language === docLang)
    && (!docQ || `${d.title} ${d.supplier_name ?? ""}`.toLowerCase().includes(docQ.toLowerCase())));
  const types = [...new Set((data?.items ?? []).map((d) => d.doc_type))];
  const langs = [...new Set((data?.items ?? []).map((d) => d.language).filter((l): l is string => !!l))];

  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={t.knowledge.hero} sub={t.knowledge.subtitle} />

      {/* the question: one prominent field, the retrieval strategy, and questions to start from */}
      <Panel className="p-4 sm:p-6">
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute start-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-3" aria-hidden />
            <Input dir="auto" value={q} aria-label={t.knowledge.ask} maxLength={1000} onChange={(e) => setQ(e.target.value)}
              placeholder={t.knowledge.askPlaceholder} className="h-14 rounded-2xl ps-12 text-md" />
          </div>
          <Button variant="primary" size="lg" className="h-14 rounded-2xl px-6" loading={asking} disabled={q.trim().length < 2} type="submit">
            {t.knowledge.askCta}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
          </Button>
        </form>
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">
          <div role="group" aria-label={t.knowledge.mode} className="flex flex-wrap items-center gap-1.5">
            <span className="me-1 text-sm font-semibold text-ink-2">{t.knowledge.mode}</span>
            {MODES.map((m) => <button key={m.value} type="button" aria-pressed={mode === m.value} onClick={() => setMode(m.value)}
              className={cx("h-8 rounded-full border px-3 font-mono text-xs font-semibold transition-colors",
                mode === m.value ? "border-accent/40 bg-accent-soft text-accent-ink" : "border-line bg-surface text-ink-2 hover:bg-sunken")}>{m.label}</button>)}
          </div>
        </div>
        {!answer && !asking && <div className="mt-5 border-t border-line pt-4">
          <p className="mb-2 text-sm font-semibold text-ink-2">{t.knowledge.tryAsking}</p>
          <ul className="flex flex-wrap gap-2">{EXAMPLES.map((ex) => <li key={ex}>
            <button type="button" onClick={() => ask(ex)} className="inline-flex max-w-full items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-start text-sm text-ink transition-colors hover:border-accent/30 hover:bg-accent-soft/30">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-ink-3" aria-hidden /><bdi>{ex}</bdi>
            </button></li>)}</ul>
        </div>}
      </Panel>

      {/* the result: the answer (AI, advisory, cited) beside the ranked passages it could draw on */}
      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <section aria-label={t.knowledge.answerTitle} aria-busy={asking} className="min-w-0">
          {asking ? <Panel className="space-y-3 p-5"><Skeleton className="h-5 w-1/3" /><Skeleton /><Skeleton className="w-11/12" /><Skeleton className="w-3/4" /></Panel>
            : failed ? <ErrorState message={t.knowledge.askFailed} onRetry={() => ask()} retryLabel={t.common.retry} />
            : answer ? <AiBlock mode={answer.mode} className="knowledge-answer" title={t.knowledge.answerTitle}>
              {(answer.abstained || answer.conflict_detected) && <div className="mb-3 flex flex-wrap gap-2">
                {answer.abstained && <Pill tone="warn">{t.knowledge.abstained}</Pill>}
                {answer.conflict_detected && <Pill tone="warn">{t.knowledge.conflict}</Pill>}
              </div>}
              <p className="whitespace-pre-line break-words text-lg font-medium leading-relaxed text-ink" dir="auto">{answer.answer}</p>
              {answer.citations.length > 0 && <div className="mt-5">
                <h2 className="mb-2 text-sm font-semibold text-ink">{t.ai.sources}</h2>
                <div className="grid gap-2 xl:grid-cols-2">{answer.citations.map((c, i) => <Citation key={c.chunk_id ?? i} c={c} index={i + 1} />)}</div>
              </div>}
            </AiBlock>
            : <Panel className="flex items-start gap-4 p-5">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-ai-soft text-ai"><FileSearch className="h-5 w-5" aria-hidden /></span>
              <div><h2 className="font-bold text-ink">{t.knowledge.answerTitle}</h2><p className="mt-1 max-w-[56ch] text-sm leading-relaxed text-ink-3">{t.knowledge.emptyAnswer}</p></div>
            </Panel>}
        </section>

        <Panel className="min-w-0">
          <PanelHeader title={t.knowledge.retrieval}
            sub={answer ? <bdi className="font-mono text-xs">{answer.retrieval.mode} · {answer.retrieval.latency_ms} ms</bdi> : t.knowledge.passagesSub} />
          {asking ? <div className="space-y-3 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
            : !answer ? <div className="flex items-start gap-3 p-5 text-sm text-ink-3"><ListOrdered className="h-5 w-5 shrink-0" aria-hidden /><p>{t.knowledge.evidenceHint}</p></div>
            : answer.retrieval.hits.length === 0 ? <p className="p-5 text-sm text-ink-2">{t.ai.noCitation}</p>
            : <ol className="divide-y divide-line">
              {answer.retrieval.hits.map((h) => <li key={h.chunk_id} className="p-4">
                <div className="flex items-start gap-3">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-sunken text-sm font-bold text-ink-2 num">{h.rank}</span>
                  <div className="min-w-0 flex-1">
                    <Link href={`/documents/${h.document_id}?page=${h.page}&q=${encodeURIComponent(h.preview.slice(0, 120))}&title=${encodeURIComponent(h.title)}`}
                      className="break-words font-semibold text-ink underline-offset-4 hover:text-accent hover:underline"><bdi>{h.title}</bdi></Link>
                    <p className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-3"><span>{label(t.knowledge.type, h.doc_type)}</span>
                      <span>{t.common.page_short} {h.page}</span>{h.section && <bdi>{h.section}</bdi>}{h.effective_date && <span>{t.knowledge.effective} {date(h.effective_date, locale)}</span>}</p>
                    <p className="mt-2 line-clamp-3 text-sm leading-snug text-ink-2" dir="auto">{h.preview}</p>
                    <details className="mt-1.5 text-xs text-ink-3"><summary className="cursor-pointer hover:text-ink-2">{t.knowledge.scores}</summary>
                      <p className="mt-1 break-words font-mono" dir="ltr">{Object.entries(h.scores).filter(([, v]) => v !== null).map(([k, v]) => `${k}=${v?.toFixed(3)}`).join("  ")}</p>
                    </details>
                  </div>
                </div>
              </li>)}
            </ol>}
        </Panel>
      </div>

      {/* the library the answers come from */}
      <Panel className="min-w-0">
        <div className="flex flex-wrap items-start justify-between gap-3 px-5 pb-3 pt-4">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{t.knowledge.documents}{data && <CountBadge>{data.items.length}</CountBadge>}</h2>
            {data && <p className="mt-1 text-xs text-ink-3">{t.knowledge.indexLabel}: <bdi className="break-all font-mono">{data.settings.embedding_model} · {data.settings.chunking_strategy} · {data.settings.retrieval_mode}{data.settings.reranker ? ` · ${data.settings.reranker}` : ""}</bdi></p>}
          </div>
          {can("knowledge:write") && <Button aria-expanded={uploading} onClick={() => setUploading((u) => !u)}><Upload className="h-4 w-4" aria-hidden />{t.knowledge.upload}</Button>}
        </div>
        {uploading && <UploadForm onDone={() => { setUploading(false); mutate(); }} />}
        <FilterBar className="border-b border-line px-5 pb-4" active={[docType, docLang].filter(Boolean).length}
          onClear={docQ || docType || docLang ? () => { setDocQ(""); setDocType(""); setDocLang(""); } : undefined}
          search={<SearchBox value={docQ} onChange={setDocQ} placeholder={t.knowledge.searchDocs} />}>
          <FilterSelect label={t.knowledge.typeField} value={docType} onChange={setDocType}>
            <option value="">{t.common.all}</option>{types.map((ty) => <option key={ty} value={ty}>{label(t.knowledge.type, ty)}</option>)}
          </FilterSelect>
          <FilterSelect label={t.common.language} value={docLang} onChange={setDocLang}>
            <option value="">{t.common.all}</option>{langs.map((l) => <option key={l} value={l}>{l.toUpperCase()}</option>)}
          </FilterSelect>
        </FilterBar>
        {error ? <div className="p-4"><ErrorState message={t.common.error} retryLabel={t.common.retry} onRetry={() => mutate()} /></div>
          : !data ? <div className="p-4"><Skeleton className="h-40 w-full" /></div>
          : data.items.length === 0 ? <EmptyState icon={<BookOpenText className="h-8 w-8" />} title={t.knowledge.empty} />
          : docs.length === 0 ? <EmptyState title={t.common.noResults} /> : <>
            <ul className="divide-y divide-line md:hidden">{docs.map((d) => <li key={d.id}>
              <Link href={`/knowledge/${d.id}`} className="flex items-start gap-3 p-4 transition-colors hover:bg-sunken">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink-3"><BookOpenText className="h-4 w-4" aria-hidden /></span>
                <span className="min-w-0 flex-1"><span className="block font-semibold text-ink"><bdi>{d.title}</bdi></span>
                  <span className="mt-0.5 block text-xs text-ink-3">{label(t.knowledge.type, d.doc_type)} · {date(d.effective_date, locale)}{d.language && <> · <bdi>{d.language.toUpperCase()}</bdi></>}</span>
                  <span className="mt-2 block"><StatusPill status={d.status} /></span></span>
              </Link></li>)}</ul>
            <div className="hidden md:block"><Table className="queue-table">
              <thead><tr><Th>{t.knowledge.titleField}</Th><Th>{t.knowledge.typeField}</Th><Th>{t.knowledge.effective}</Th><Th>{t.common.language}</Th><Th>{t.knowledge.version}</Th>
                <Th className="text-end">{t.knowledge.chunks}</Th><Th>{t.common.status}</Th></tr></thead>
              <tbody>{docs.map((d) => (
                <tr key={d.id}>
                  <Td><div className="flex min-w-[14rem] items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink-3"><BookOpenText className="h-4 w-4" aria-hidden /></span>
                    <div className="min-w-0"><Link href={`/knowledge/${d.id}`} className="font-semibold text-ink underline-offset-4 hover:text-accent hover:underline"><bdi>{d.title}</bdi></Link>
                      {d.supplier_name && <p className="text-xs text-ink-3"><bdi>{d.supplier_name}</bdi></p>}</div>
                  </div></Td>
                  <Td className="whitespace-nowrap text-sm text-ink-2">{label(t.knowledge.type, d.doc_type)}</Td>
                  <Td className="whitespace-nowrap text-sm text-ink-2">{date(d.effective_date, locale)}</Td>
                  <Td className="text-sm text-ink-2"><bdi>{d.language?.toUpperCase() ?? "—"}</bdi></Td>
                  <Td className="text-sm text-ink-2 num">{d.version ?? "—"}</Td>
                  <Td className="text-end num">{d.chunk_count}</Td>
                  <Td><StatusPill status={d.status} /></Td>
                </tr>))}</tbody>
            </Table></div>
          </>}
      </Panel>
    </div>
  );
}
