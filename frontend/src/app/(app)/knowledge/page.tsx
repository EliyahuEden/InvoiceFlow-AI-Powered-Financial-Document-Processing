"use client";

import { BookOpenText, Search, Upload } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { AiBlock, Citation, Pill, StatusPill } from "@/components/domain";
import { Segmented } from "@/components/list";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, Field, Input, Panel, PanelHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui";
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
    <form onSubmit={submit} className="grid gap-3 border-b border-line bg-sunken/50 p-4 md:grid-cols-6">
      <div className="md:col-span-2"><Field label="PDF"><Input type="file" accept="application/pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required /></Field></div>
      <div className="md:col-span-2"><Field label="Title"><Input dir="auto" required value={title} onChange={(e) => setTitle(e.target.value)} /></Field></div>
      <Field label="Type"><Select className="w-full" value={docType} onChange={(e) => setDocType(e.target.value)}>
        {Object.entries(t.knowledge.type).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
      <Field label={t.common.supplier}><Select className="w-full" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
        <option value="">—</option>{sup?.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
      <Field label={t.knowledge.effective}><Input type="date" value={eff} onChange={(e) => setEff(e.target.value)} /></Field>
      <div className="flex items-end md:col-span-5"><Button type="submit" variant="primary" loading={busy}><Upload className="h-4 w-4" />{t.knowledge.upload}</Button></div>
    </form>
  );
}

export default function KnowledgePage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const { data, mutate } = useApi<{ items: Doc[]; settings: Record<string, string | null> }>("/api/knowledge/documents",
    { refreshInterval: (d) => (d?.items.some((i) => i.status === "processing") ? 3000 : 0) });
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asking, setAsking] = useState(false);
  const [uploading, setUploading] = useState(false);

  const ask = async (question = q) => {
    if (question.trim().length < 2) return;
    setQ(question);
    setAsking(true);
    try { setAnswer(await api.post<Answer>("/api/knowledge/ask", { query: question, mode, k: 5 })); }
    catch (e) { toast.error(String((e as Error).message)); } finally { setAsking(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader title={t.knowledge.title} />
      <Panel>
        <PanelHeader title={t.knowledge.ask} actions={
          <Segmented value={mode} onChange={setMode} options={[{ value: "bm25", label: "BM25" }, { value: "dense", label: "Dense" },
            { value: "hybrid", label: "Hybrid" }, { value: "hybrid_rerank", label: "Hybrid + rerank" }]} />} />
        <form className="flex gap-2 p-4" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
            <Input dir="auto" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.knowledge.askPlaceholder} className="h-10 ps-9" />
          </div>
          <Button variant="primary" size="lg" loading={asking} type="submit">{t.knowledge.askCta}</Button>
        </form>
        {!answer && (
          <div className="flex flex-wrap gap-2 px-4 pb-4">
            {EXAMPLES.map((ex) => <button key={ex} onClick={() => ask(ex)} dir="auto"
              className="rounded-full border border-line bg-surface px-3 py-1 text-sm text-ink-2 hover:border-accent hover:text-ink">{ex}</button>)}
          </div>
        )}
        {answer && (
          <div className="grid gap-5 border-t border-line p-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <AiBlock mode={answer.mode}>
              {answer.abstained ? <p className="font-medium text-warn">{t.knowledge.abstained}</p> : null}
              <p className="text-base leading-relaxed text-ink" dir="auto">{answer.answer}</p>
              {answer.conflict_detected && <Pill tone="warn" className="mt-2">{t.knowledge.conflict}</Pill>}
              <div className="mt-3 space-y-2">{answer.citations.map((c, i) => <Citation key={i} c={c} index={i + 1} />)}</div>
            </AiBlock>
            <div>
              <p className="mb-2 text-sm font-semibold text-ink">{t.knowledge.retrieval} <span className="font-normal text-ink-3">· {answer.retrieval.mode} · {answer.retrieval.latency_ms} ms</span></p>
              <ol className="space-y-2">
                {answer.retrieval.hits.map((h) => (
                  <li key={h.chunk_id} className="rounded-md border border-line p-2.5">
                    <div className="flex items-center gap-2 text-xs text-ink-3">
                      <span className="grid h-4 w-4 place-items-center rounded bg-sunken text-2xs font-semibold text-ink-2">{h.rank}</span>
                      <Link href={`/documents/${h.document_id}?page=${h.page}&q=${encodeURIComponent(h.preview.slice(0, 120))}&title=${encodeURIComponent(h.title)}`}
                        className="truncate font-medium text-ink-2 hover:text-accent">{h.title}</Link>
                      <span>· {t.common.page_short} {h.page}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-ink-2" dir="auto">{h.preview}</p>
                    <p className="mt-1 font-mono text-2xs text-ink-3" dir="ltr">
                      {Object.entries(h.scores).filter(([, v]) => v !== null).map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(3) : v}`).join("  ")}
                    </p>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </Panel>

      <Panel>
        <PanelHeader title={t.knowledge.documents}
          sub={data && <span className="font-mono text-xs">{data.settings.embedding_model} · {data.settings.chunking_strategy} · {data.settings.retrieval_mode}{data.settings.reranker ? ` · ${data.settings.reranker}` : ""}</span>}
          actions={can("knowledge:write") && <Button onClick={() => setUploading((u) => !u)}><Upload className="h-4 w-4" />{t.knowledge.upload}</Button>} />
        {uploading && <UploadForm onDone={() => { setUploading(false); mutate(); }} />}
        {!data ? <div className="p-4"><Skeleton className="h-40 w-full" /></div> : (
          <Table>
            <thead><tr><Th>Title</Th><Th>Type</Th><Th>{t.common.supplier}</Th><Th>{t.knowledge.effective}</Th><Th>{t.knowledge.version}</Th>
              <Th className="text-end">{t.knowledge.chunks}</Th><Th>{t.common.status}</Th></tr></thead>
            <tbody>{data.items.map((d) => (
              <tr key={d.id} className="hover:bg-sunken/70">
                <Td><Link href={`/knowledge/${d.id}`} className="inline-flex items-center gap-2 font-medium hover:text-accent" dir="auto">
                  <BookOpenText className="h-4 w-4 shrink-0 text-ink-3" />{d.title}</Link></Td>
                <Td className="text-sm text-ink-2">{(t.knowledge.type as Record<string, string>)[d.doc_type]}</Td>
                <Td className="text-sm text-ink-2" dir="auto">{d.supplier_name ?? "—"}</Td>
                <Td className="text-sm text-ink-2">{date(d.effective_date, locale)}</Td>
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
