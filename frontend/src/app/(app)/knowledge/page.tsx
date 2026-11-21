"use client";

import { ArrowRight, BookOpenText, FileSearch, Search, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { AiBlock, Citation, Pill, StatusPill } from "@/components/domain";
import { Segmented } from "@/components/list";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, EmptyState, ErrorState, Field, Input, Panel, PanelHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { date } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

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
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file); fd.append("title", title); fd.append("doc_type", docType);
    if (supplierId) fd.append("supplier_id", supplierId);
    if (eff) fd.append("effective_date", eff);
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
      <div className="flex items-end md:col-span-5"><Button type="submit" variant="primary" loading={busy}><Upload className="h-4 w-4" />{t.knowledge.upload}</Button></div>
    </form>
  );
}

export default function KnowledgePage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const { data, error, mutate } = useApi<{ items: Doc[]; settings: Record<string, string | null> }>("/api/knowledge/documents",
    { refreshInterval: (d) => (d?.items.some((i) => i.status === "processing") ? 3000 : 0) });
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);
  const [uploading, setUploading] = useState(false);

  const ask = async (question = q) => {
    if (asking || question.trim().length < 2) return;
    setQ(question);
    setAnswer(null);
    setAsking(true);
    try { setAnswer(await api.post<Answer>("/api/knowledge/ask", { query: question, mode, k: 5 })); }
    catch (e) { toast.error(String((e as Error).message)); } finally { setAsking(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader title={t.knowledge.hero} sub={t.knowledge.subtitle} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          <Panel className="p-4 sm:p-5">
            <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); ask(); }}>
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute start-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-2" aria-hidden />
                <Input dir="auto" value={q} aria-label={t.knowledge.ask} maxLength={1000} onChange={(e) => setQ(e.target.value)}
                  placeholder={t.knowledge.askPlaceholder} className="h-12 rounded-full ps-10" />
              </div>
              <Button variant="primary" className="h-12" loading={asking} disabled={q.trim().length < 2} type="submit">
                {t.knowledge.askCta}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
              </Button>
            </form>
            <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <span className="text-sm text-ink-2">{t.knowledge.mode}</span>
              <Segmented value={mode} onChange={setMode} options={[{ value: "bm25", label: "BM25" }, { value: "dense", label: "Dense" },
                { value: "hybrid", label: "Hybrid" }, { value: "hybrid_rerank", label: "Hybrid + rerank" }]} />
            </div>
          </Panel>
          {asking && <Panel className="space-y-3 p-5" aria-label={t.common.loading}><Skeleton /><Skeleton className="w-3/4" /></Panel>}
          {!answer && !asking && <Panel>
            <PanelHeader title={t.knowledge.examples} />
            <ul className="divide-y divide-line">
              {EXAMPLES.map((ex) => <li key={ex}><button onClick={() => ask(ex)}
                className="flex w-full items-center justify-between gap-3 px-5 py-3 text-start text-sm text-ink hover:bg-sunken">
                <bdi dir="auto">{ex}</bdi><ArrowRight className="h-4 w-4 shrink-0 text-ink-3 rtl:rotate-180" aria-hidden />
              </button></li>)}
            </ul>
          </Panel>}
          {answer && <AiBlock mode={answer.mode} className="knowledge-answer">
            {answer.abstained && <Pill tone="warn" className="mb-2">{t.knowledge.abstained}</Pill>}
            <p className="whitespace-pre-line break-words text-lg font-medium leading-relaxed text-ink" dir="auto">{answer.answer}</p>
            {answer.conflict_detected && <Pill tone="warn" className="mt-2">{t.knowledge.conflict}</Pill>}
            {answer.citations.length > 0 && <div className="mt-5">
              <h2 className="mb-2 text-sm font-semibold text-ink">{t.ai.sources}</h2>
              <div className="grid gap-2 xl:grid-cols-2">{answer.citations.map((c, i) => <Citation key={c.chunk_id ?? i} c={c} index={i + 1} />)}</div>
            </div>}
          </AiBlock>}
        </div>
        <Panel className="min-w-0">
          <PanelHeader title={t.knowledge.retrieval}
            sub={answer && <bdi className="font-mono text-xs">{answer.retrieval.mode} · {answer.retrieval.latency_ms} ms</bdi>} />
          {!answer ? <div className="flex items-start gap-3 p-5 text-sm text-ink-2">
            <FileSearch className="h-5 w-5 shrink-0 text-ink-3" aria-hidden />
            <p>{asking ? t.common.loading : t.knowledge.evidenceHint}</p>
          </div> : answer.retrieval.hits.length === 0 ? <p className="p-5 text-sm text-ink-2">{t.ai.noCitation}</p> :
            <ol className="divide-y divide-line">
              {answer.retrieval.hits.map((h) => <li key={h.chunk_id} className="p-4">
                <div className="flex items-start gap-2.5">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-sunken text-sm font-semibold num">{h.rank}</span>
                  <div className="min-w-0 flex-1">
                    <Link href={`/documents/${h.document_id}?page=${h.page}&q=${encodeURIComponent(h.preview.slice(0, 120))}&title=${encodeURIComponent(h.title)}`}
                      className="break-words font-semibold text-ink underline-offset-4 hover:text-accent hover:underline"><bdi>{h.title}</bdi></Link>
                    <p className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-3"><span>{(t.knowledge.type as Record<string,string>)[h.doc_type] ?? h.doc_type}</span>
                      <span>{t.common.page_short} {h.page}</span>{h.section && <bdi>{h.section}</bdi>}{h.effective_date && <span>{t.knowledge.effective} {date(h.effective_date, locale)}</span>}</p>
                  </div>
                </div>
                <p className="mt-2 line-clamp-2 text-sm text-ink-2" dir="auto">{h.preview}</p>
                <details className="mt-1 text-xs text-ink-3"><summary className="cursor-pointer">{t.knowledge.scores}</summary>
                  <p className="mt-1 break-words font-mono" dir="ltr">{Object.entries(h.scores).filter(([, v]) => v !== null).map(([k, v]) => `${k}=${v?.toFixed(3)}`).join("  ")}</p>
                </details>
              </li>)}
            </ol>}
        </Panel>
      </div>

      <Panel>
        <PanelHeader title={t.knowledge.documents}
          sub={data && <bdi className="break-all font-mono text-xs">{data.settings.embedding_model} · {data.settings.chunking_strategy} · {data.settings.retrieval_mode}{data.settings.reranker ? ` · ${data.settings.reranker}` : ""}</bdi>}
          actions={can("knowledge:write") && <Button variant="primary" aria-expanded={uploading} onClick={() => setUploading((u) => !u)}><Upload className="h-4 w-4" />{t.knowledge.upload}</Button>} />
        {uploading && <UploadForm onDone={() => { setUploading(false); mutate(); }} />}
        {error ? <ErrorState message={t.common.error} retryLabel={t.common.retry} onRetry={() => mutate()} /> : !data ? <div className="p-4"><Skeleton className="h-40 w-full" /></div> : data.items.length === 0 ? <EmptyState title={t.knowledge.empty} /> : (
          <Table>
            <thead><tr><Th>{t.knowledge.titleField}</Th><Th>{t.knowledge.typeField}</Th><Th>{t.common.supplier}</Th><Th>{t.knowledge.effective}</Th><Th>{t.common.language}</Th><Th>{t.knowledge.version}</Th>
              <Th className="text-end">{t.knowledge.chunks}</Th><Th>{t.common.status}</Th></tr></thead>
            <tbody>{data.items.map((d) => (
              <tr key={d.id} className="hover:bg-sunken/70">
                <Td><Link href={`/knowledge/${d.id}`} className="inline-flex items-center gap-2 font-medium hover:text-accent" dir="auto">
                  <BookOpenText className="h-4 w-4 shrink-0 text-ink-3" />{d.title}</Link></Td>
                <Td className="text-sm text-ink-2">{(t.knowledge.type as Record<string, string>)[d.doc_type]}</Td>
                <Td className="text-sm text-ink-2" dir="auto">{d.supplier_name ?? "—"}</Td>
                <Td className="text-sm text-ink-2">{date(d.effective_date, locale)}</Td>
                <Td className="text-sm text-ink-2"><bdi>{d.language?.toUpperCase() ?? "—"}</bdi></Td>
                <Td className="text-sm text-ink-2">{d.version ?? "—"}</Td>
                <Td className="text-end num">{d.chunk_count}</Td>
                <Td><StatusPill status={d.status} /></Td>
              </tr>))}</tbody>
          </Table>
        )}
      </Panel>
    </div>
  );
}
