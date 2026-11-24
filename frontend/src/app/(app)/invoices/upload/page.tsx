"use client";

import { CheckCircle2, CircleAlert, CloudUpload, FileText, Loader2, Shield, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { StatusPill } from "@/components/domain";
import { ExtractionScene, type ExtractedFields } from "@/components/extraction-scene";
import { StationSteps } from "@/components/station-steps";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, cx, EmptyState, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { onLiveEvent } from "@/lib/events";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";
import { date, money } from "@/lib/format";

type Item = {
  key: string; name: string; size: number; state: "queued" | "uploading" | "processing" | "done" | "failed" | "duplicate" | "rejected";
  invoiceId?: string; jobId?: string; progress?: number; message?: string; status?: string; fields?: ExtractedFields;
};

/** Pipeline stage from the job's own progress points (processing.py: 5 loading, 10-55 reading/OCR, 60 extracting,
 *  85 reconciling): 0 uploaded, 1 reading, 2 extracting, 3 matching, 4 ready. */
function stageOf(it: Item): number {
  if (it.state === "done") return 4;
  if (it.state !== "processing") return 0;
  const p = it.progress ?? 0;
  return p >= 85 ? 3 : p >= 60 ? 2 : p >= 10 ? 1 : 0;
}
type Filter = "all" | "processing" | "ready" | "errors";

type JobStatus = { status: string; progress: number; message: string | null; error: string | null; entity_id: string | null };
type UploadResponse = { invoice_id: string; job_id: string };
const PARALLEL_UPLOADS = 3;

export default function UploadPage() {
  const { t, locale } = useI18n();
  const { can, me } = useSession();
  const allowed = can("invoice:upload");
  const [items, setItems] = useState<Item[]>([]);
  const [drag, setDrag] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const input = useRef<HTMLInputElement>(null);
  const queue = useRef<{ active: number; pending: (() => Promise<void>)[] }>({ active: 0, pending: [] });
  const tracked = useRef<Item[]>([]);
  const active = items.filter((i) => i.state === "processing" && i.jobId);
  const hasActive = active.length > 0;
  useEffect(() => { tracked.current = active; });
  const { data: samples, error: sampleError, mutate: reloadSamples } = useApi<{ items: { file: string; scenario: string; description: string; language: string }[] }>(
    allowed ? "/api/invoices/demo/samples" : null,
  );

  const patch = useCallback((key: string, p: Partial<Item>, onlyWhileProcessing = false) => {
    setItems((prev) => prev.map((i) => i.key === key && (!onlyWhileProcessing || i.state === "processing") ? { ...i, ...p } : i));
  }, []);

  // live progress via SSE; polling below is the fallback
  useEffect(() => onLiveEvent(({ event, data }) => {
    if (!event.startsWith("job.")) return;
    setItems((prev) => prev.map((i) => {
      if (i.state !== "processing" || i.jobId !== data.job_id) return i;
      if (event === "job.completed") return { ...i, state: "done", message: undefined };
      if (event === "job.failed") return { ...i, state: "failed", message: data.error as string | undefined };
      return { ...i, progress: typeof data.progress === "number" ? data.progress : i.progress,
        message: (data.message ?? data.error) as string | undefined };
    }));
  }), []);

  useEffect(() => {
    if (!hasActive) return;
    let cancelled = false;
    let polling = false;
    const id = setInterval(async () => {
      if (polling) return;
      polling = true;
      await Promise.all(tracked.current.map(async (it) => {
        try {
          const j = await api.get<JobStatus>(`/api/jobs/${it.jobId}`);
          const done = j.status === "succeeded";
          const failed = j.status === "failed";
          let status: string | undefined;
          if (done && it.invoiceId) status = (await api.get<{ status: string }>(`/api/invoices/${it.invoiceId}`).catch(() => null))?.status;
          if (!cancelled) patch(it.key, { progress: j.progress, message: done ? undefined : failed ? j.error ?? j.message ?? undefined : j.message ?? undefined,
            state: done ? "done" : failed ? "failed" : "processing", status }, true);
        } catch {
          if (!cancelled) patch(it.key, { message: t.upload.trackingUnavailable }, true);
        }
      }));
      polling = false;
    }, 1500);
    return () => { cancelled = true; clearInterval(id); };
  }, [hasActive, patch, t.upload.trackingUnavailable]);

  // the fields of a finished invoice, for the document-to-data scene (fetched once per finished item)
  const fetched = useRef(new Set<string>());
  useEffect(() => {
    for (const it of items) {
      if (it.state !== "done" || !it.invoiceId || fetched.current.has(it.key)) continue;
      fetched.current.add(it.key);
      void api.get<{ status: string; supplier_name: string | null; supplier_name_raw: string | null; invoice_number: string | null;
        invoice_date: string | null; total: string | null; currency: string | null }>(`/api/invoices/${it.invoiceId}`).then((inv) => patch(it.key, {
        status: inv.status,
        fields: { supplier: inv.supplier_name ?? inv.supplier_name_raw, number: inv.invoice_number,
          date: inv.invoice_date ? date(inv.invoice_date, locale) : null, total: inv.total ? money(inv.total, inv.currency) : null },
      })).catch(() => undefined);
    }
  }, [items, patch, locale]);

  const enqueue = (key: string, run: () => Promise<UploadResponse>) => {
    const pending = queue.current;
    pending.pending.push(async () => {
      patch(key, { state: "uploading" });
      try {
        const r = await run();
        patch(key, { state: "processing", invoiceId: r.invoice_id, jobId: r.job_id });
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          const d = e.detail as { invoice_id?: string };
          patch(key, { state: "duplicate", invoiceId: d?.invoice_id, message: t.upload.duplicate });
        } else {
          patch(key, { state: "rejected", message: e instanceof ApiError ? String(e.message) : t.common.error });
        }
      }
    });
    function startNext() {
      while (pending.active < PARALLEL_UPLOADS && pending.pending.length) {
        const upload = pending.pending.shift()!;
        pending.active++;
        void upload().finally(() => { pending.active--; startNext(); });
      }
    }
    startNext();
  };

  const addFiles = (files: FileList | File[]) => {
    const list = Array.from(files);
    const fresh: Item[] = list.map((f) => ({ key: crypto.randomUUID(), name: f.name, size: f.size, state: "queued" }));
    setItems((prev) => [...fresh, ...prev]);
    fresh.forEach((it, idx) => {
      const file = list[idx];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      enqueue(it.key, () => api.post("/api/invoices/upload", fd));
    });
  };

  const uploadSample = (file: string) => {
    const it: Item = { key: crypto.randomUUID(), name: file.split("/").pop()!, size: 0, state: "queued" };
    setItems((prev) => [it, ...prev]);
    enqueue(it.key, () => api.post("/api/invoices/demo/samples/upload", { file }));
  };

  const errors = (i: Item) => ["failed", "rejected", "duplicate"].includes(i.state);
  const counts = { all: items.length, processing: items.filter((i) => ["queued", "uploading", "processing"].includes(i.state)).length,
    ready: items.filter((i) => i.state === "done").length, errors: items.filter(errors).length };
  const shown = items.filter((i) => filter === "all" || (filter === "processing" ? ["queued", "uploading", "processing"].includes(i.state)
    : filter === "ready" ? i.state === "done" : errors(i)));
  const focus = items.find((i) => i.state === "processing") ?? items.find((i) => i.state === "done");
  const latestDone = items.find((i) => i.fields);
  const stages = [t.upload.stage.uploaded, t.upload.stage.reading, t.upload.stage.extracting, t.upload.stage.matching, t.upload.stage.ready];

  return (
    <div className="space-y-5">
      <PageHeader title={<span className="inline-flex items-center gap-3"><CloudUpload className="h-8 w-8 text-accent" aria-hidden />{t.upload.title}</span>}
        sub={t.upload.subtitle} back={{ href: "/invoices", label: t.nav.inbox }} />
      {!me ? <Skeleton className="h-60" /> : !allowed ? <Panel><EmptyState icon={<Shield className="h-7 w-7" />} title={t.upload.restricted} /></Panel> : (
      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="min-w-0 space-y-5">
          <Panel className="p-5">
            <h2 className="flex items-center gap-2 text-lg font-bold text-ink"><Sparkles className="h-5 w-5 text-accent" aria-hidden />{t.upload.pipelineTitle}</h2>
            <div className="mt-5">
              <StationSteps names={stages} current={focus ? stageOf(focus) : -1} done={focus?.state === "done"}
                detail={focus?.state === "processing" && focus.progress !== undefined ? `${focus.progress}%` : undefined} />
            </div>
            <p className="mt-4 flex items-center gap-2 rounded-xl bg-sunken px-3 py-2 text-sm text-ink-2" role="status">
              {counts.processing > 0 ? <><Loader2 className="h-4 w-4 animate-spin text-accent" aria-hidden />{t.upload.processingCount.replace("{n}", String(counts.processing))}</>
                : focus ? <><CheckCircle2 className="h-4 w-4 text-ok" aria-hidden />{t.upload.allDone}</> : t.upload.idle}
              {focus?.message && counts.processing > 0 && <span className="ms-auto truncate text-ink-3">{focus.message}</span>}
            </p>
          </Panel>

          <Panel>
            <PanelHeader title={t.upload.jobs} actions={<span className="num text-sm text-ink-3">{items.length}</span>} />
            <div role="tablist" aria-label={t.upload.jobs} className="flex flex-wrap gap-2 px-5 pt-4">
              {(["all", "processing", "ready", "errors"] as const).map((f) => (
                <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
                  className={cx("h-9 rounded-full border px-4 text-sm font-semibold transition-colors",
                    filter === f ? "border-accent/30 bg-accent-soft text-accent-ink" : "border-line bg-surface text-ink-2 hover:bg-sunken")}>
                  {t.upload.filters[f]} <bdi className="num">({counts[f]})</bdi>
                </button>
              ))}
            </div>
            {shown.length === 0 ? <p className="px-5 py-8 text-center text-sm text-ink-3">{items.length ? t.common.noResults : t.upload.noJobs}</p> : (
            <ul className="mt-2 divide-y divide-line">
              {shown.map((it) => (
                <li key={it.key} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="grid h-11 w-9 shrink-0 place-items-center rounded-md border border-line bg-sunken text-ink-3"><FileText className="h-4 w-4" aria-hidden /></span>
                    <div className="min-w-24 flex-1">
                      <p className="truncate text-base font-bold text-ink" dir="auto">{it.name}</p>
                      <p className="break-words text-sm text-ink-3" role="status">
                        {it.size >= 50_000 ? <><bdi className="num">{(it.size / 1024 / 1024).toFixed(1)} MB</bdi> · </> : null}
                        <span>{it.message ?? (it.state === "failed" ? t.invoice.failedTitle : it.state === "processing" ? stages[stageOf(it)] : t.upload[it.state])}</span>
                      </p>
                    </div>
                    {it.state === "done" ? <span className="inline-flex items-center gap-1.5 rounded-full bg-ok-soft px-3 py-1 text-sm font-bold text-ok"><CheckCircle2 className="h-4 w-4" aria-hidden />{t.upload.stage.ready}</span>
                      : errors(it) ? <span className={cx("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold", it.state === "duplicate" ? "bg-warn-soft text-warn" : "bg-danger-soft text-danger")}><CircleAlert className="h-4 w-4" aria-hidden />{it.state === "duplicate" ? t.upload.duplicate : t.upload.rejected}</span>
                      : <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1 text-sm font-bold text-accent-ink"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{stages[stageOf(it)]}</span>}
                    {it.status && it.state === "done" && <StatusPill status={it.status} />}
                    {it.invoiceId && ["done", "duplicate", "failed"].includes(it.state) && (
                      <Button asChild size="sm"><Link href={`/invoices/${it.invoiceId}`}>{t.upload.openInvoice}</Link></Button>
                    )}
                  </div>
                  {it.state === "processing" && it.progress !== undefined && (
                    <div className="mt-3 flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-label={it.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={it.progress}>
                        <div className="h-full rounded-full bg-gradient-to-l from-[#a78bfa] to-accent transition-[width] duration-500" style={{ width: `${it.progress}%` }} />
                      </div>
                      <bdi className="text-xs font-bold text-ink-2 num">{it.progress}%</bdi>
                    </div>
                  )}
                </li>
              ))}
            </ul>)}
          </Panel>
        </div>

        <div className="min-w-0 space-y-5">
          <section className="command-hero overflow-hidden p-0">
            <ExtractionScene fields={latestDone?.fields ?? null} active={counts.processing > 0} sourceName={latestDone?.name} />
            <div className="border-t border-line p-4 sm:p-5">
              <div
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
                className={cx("flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-8 text-center transition-colors",
                  drag ? "border-accent bg-accent-soft/70" : "border-accent/30 bg-surface/60 hover:border-accent/60")}
              >
                <CloudUpload className="h-10 w-10 text-accent" aria-hidden />
                <h2 className="mt-3 text-xl font-extrabold tracking-tight text-ink">{t.upload.drop}</h2>
                <p className="mt-1 max-w-md text-sm text-ink-3">{t.upload.limits}</p>
                <Button className="mt-4" variant="primary" type="button" onClick={() => input.current?.click()}>{t.upload.browse}</Button>
                <input ref={input} type="file" multiple accept="application/pdf,image/png,image/jpeg" hidden aria-label={t.upload.browse}
                  onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} data-testid="file-input" />
              </div>
            </div>
          </section>

          <Panel>
            <PanelHeader title={t.upload.samples} sub={t.upload.samplesHint} />
            {sampleError ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => reloadSamples()} retryLabel={t.common.retry} /></div> :
             !samples ? <div className="p-4"><Skeleton /></div> : <ul className="divide-y divide-line">
              {samples?.items.map((s) => (
                <li key={s.file} className="flex items-center gap-3 px-5 py-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink"><FileText className="h-4 w-4" aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <bdi className="block truncate font-mono text-xs text-ink">{s.file.split("/").pop()}</bdi>
                    <p className="mt-0.5 text-sm text-ink-2" dir="auto">{label(t.upload.sampleText, s.scenario, s.description)}</p>
                  </div>
                  <Button size="sm" onClick={() => uploadSample(s.file)}>{t.inbox.upload}</Button>
                </li>
              ))}
            </ul>}
          </Panel>
        </div>
      </div>)}
    </div>
  );
}
