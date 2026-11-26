"use client";

import { CheckCircle2, CircleAlert, CloudUpload, FileText, Inbox, Loader2, Shield } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { StatusPill } from "@/components/domain";
import { ExtractionScene, type ExtractedFields } from "@/components/extraction-scene";
import { StationSteps } from "@/components/station-steps";
import { useSession } from "@/components/session";
import { CountBadge, PageHeader } from "@/components/page-kit";
import { Button, cx, EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui";
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

  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); if (!drag) setDrag(true); };
  const onDragLeave = (e: React.DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDrag(false); };
  const onDrop = (e: React.DragEvent) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); };

  return (
    <div className="min-w-0 space-y-5">
      <PageHeader title={t.upload.title} sub={t.upload.subtitle}
        actions={<Button asChild variant="ghost"><Link href="/invoices"><Inbox className="h-4 w-4" aria-hidden />{t.nav.inbox}</Link></Button>} />
      {!me ? <Skeleton className="h-60" /> : !allowed ? <Panel><EmptyState icon={<Shield className="h-7 w-7" />} title={t.upload.restricted} /></Panel> : <>
      <div className="grid min-w-0 items-stretch gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        {/* the drop zone is the whole panel: the illustration of what happens to a file, then the action */}
        <section aria-label={t.upload.drop} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
          className={cx("command-panel relative flex min-w-0 flex-col p-3 transition-[box-shadow,background-color] duration-200", drag && "bg-accent-soft/40 shadow-pop")}>
          <div className={cx("flex flex-1 flex-col rounded-[14px] border-2 border-dashed transition-colors duration-200",
            drag ? "border-accent bg-accent-soft/50" : "border-accent/25")}>
            <div className="order-2 sm:order-1"><ExtractionScene fields={latestDone?.fields ?? null} active={counts.processing > 0} sourceName={latestDone?.name} /></div>
            <div className="order-1 flex flex-col items-center px-5 pb-7 pt-6 text-center sm:order-2 sm:pt-1">
              <CloudUpload className={cx("h-9 w-9 text-accent transition-transform duration-200", drag && "-translate-y-1 scale-110")} aria-hidden />
              <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-ink" aria-live="polite">{drag ? t.upload.dropRelease : t.upload.drop}</h2>
              <p className="mt-1.5 max-w-[46ch] text-sm leading-relaxed text-ink-3">{t.upload.limits}</p>
              <Button className="mt-5" size="lg" variant="primary" type="button" onClick={() => input.current?.click()}><CloudUpload className="h-4 w-4" aria-hidden />{t.upload.browse}</Button>
              <input ref={input} type="file" multiple accept="application/pdf,image/png,image/jpeg" hidden aria-label={t.upload.browse}
                onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} data-testid="file-input" />
            </div>
          </div>
        </section>

        {/* where each file is: the pipeline for the file in focus, then every job */}
        <Panel className="flex min-w-0 flex-col">
          <div className="px-5 pb-5 pt-4">
            <h2 className="text-lg font-bold tracking-tight text-ink">{t.upload.pipelineTitle}</h2>
            <div className="mt-5">
              <StationSteps names={stages} current={focus ? stageOf(focus) : -1} done={focus?.state === "done"}
                detail={focus?.state === "processing" && focus.progress !== undefined ? `${focus.progress}%` : undefined} />
            </div>
            <p className="mt-4 flex items-center gap-2 rounded-xl bg-sunken px-3 py-2 text-sm text-ink-2" role="status">
              {counts.processing > 0 ? <><Loader2 className="h-4 w-4 animate-spin text-accent" aria-hidden />{counts.processing === 1 ? t.upload.processingOne : t.upload.processingCount.replace("{n}", String(counts.processing))}</>
                : focus ? <><CheckCircle2 className="h-4 w-4 text-ok" aria-hidden />{t.upload.allDone}</> : t.upload.idle}
              {focus?.message && counts.processing > 0 && <span className="ms-auto truncate text-ink-3">{focus.message}</span>}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 pb-1 pt-4">
            <h2 className="flex items-center gap-2 text-lg font-bold tracking-tight text-ink">{t.upload.jobs}{items.length > 0 && <CountBadge>{items.length}</CountBadge>}</h2>
          </div>
          <div role="tablist" aria-label={t.upload.jobs} className="flex flex-wrap gap-1.5 px-5 pt-2">
            {(["all", "processing", "ready", "errors"] as const).map((f) => (
              <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
                className={cx("h-8 rounded-full border px-3 text-sm font-semibold transition-colors",
                  filter === f ? "border-accent/30 bg-accent-soft text-accent-ink" : "border-line bg-surface text-ink-2 hover:bg-sunken")}>
                {t.upload.filters[f]} <bdi className="num">({counts[f]})</bdi>
              </button>
            ))}
          </div>
          {shown.length === 0 ? <div className="flex flex-1 flex-col items-center justify-center px-5 py-10 text-center">
              <span className="grid h-11 w-11 place-items-center rounded-2xl bg-sunken text-ink-3"><FileText className="h-5 w-5" aria-hidden /></span>
              <p className="mt-3 text-sm text-ink-3">{items.length ? t.common.noResults : t.upload.noJobs}</p>
            </div> : (
          <ul className="mt-2 divide-y divide-line">
            {shown.map((it) => (
              <li key={it.key} className="px-5 py-3">
                <div className="flex items-center gap-3">
                  <span className={cx("grid h-10 w-8 shrink-0 place-items-center rounded-md border",
                    it.state === "done" ? "border-ok/25 bg-ok-soft text-ok" : errors(it) ? "border-danger/20 bg-danger-soft text-danger" : "border-line bg-sunken text-ink-3")}>
                    <FileText className="h-4 w-4" aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold text-ink"><bdi>{it.name}</bdi></p>
                    <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-ink-3" role="status">
                      {it.state === "done" ? <span className="inline-flex items-center gap-1 font-semibold text-ok"><CheckCircle2 className="h-3.5 w-3.5" aria-hidden />{t.upload.stage.ready}</span>
                        : errors(it) ? <span className={cx("inline-flex items-center gap-1 font-semibold", it.state === "duplicate" ? "text-warn" : "text-danger")}><CircleAlert className="h-3.5 w-3.5" aria-hidden />{it.state === "duplicate" ? t.upload.duplicate : it.state === "failed" ? t.invoice.failedTitle : t.upload.rejected}</span>
                        : <span className="inline-flex items-center gap-1 font-semibold text-accent-ink"><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />{it.state === "processing" ? stages[stageOf(it)] : it.state === "queued" ? t.upload.queued : t.upload.uploading}</span>}
                      {it.size >= 50_000 && <><span aria-hidden>·</span><bdi className="num">{(it.size / 1024 / 1024).toFixed(1)} MB</bdi></>}
                      {it.message && it.state !== "duplicate" && <><span aria-hidden>·</span><span className="break-words">{it.message}</span></>}
                    </p>
                  </div>
                  {it.status && it.state === "done" && <StatusPill status={it.status} />}
                  {it.invoiceId && ["done", "duplicate", "failed"].includes(it.state) && (
                    <Button asChild size="sm"><Link href={`/invoices/${it.invoiceId}`}>{t.upload.openInvoice}</Link></Button>
                  )}
                </div>
                {it.state === "processing" && it.progress !== undefined && (
                  <div className="mt-2.5 flex items-center gap-2 ps-11">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-label={it.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={it.progress}>
                      <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${it.progress}%` }} />
                    </div>
                    <bdi className="text-xs font-bold text-ink-2 num">{it.progress}%</bdi>
                  </div>
                )}
              </li>
            ))}
          </ul>)}
        </Panel>
      </div>

      {/* the bundled synthetic samples, uploaded through the same pipeline as any file */}
      <Panel className="grid min-w-0 gap-4 p-5 lg:grid-cols-[minmax(14rem,0.7fr)_minmax(0,2.3fr)] lg:items-center">
        <div>
          <h2 className="text-lg font-bold tracking-tight text-ink">{t.upload.samples}</h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-3">{t.upload.samplesHint}</p>
        </div>
        {sampleError ? <ErrorState message={t.common.error} onRetry={() => reloadSamples()} retryLabel={t.common.retry} />
          : !samples ? <div className="grid gap-3 md:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
          : <ul className="grid gap-3 md:grid-cols-3">
            {samples.items.map((s) => (
              <li key={s.file} className="flex min-w-0 flex-col gap-3 rounded-[14px] border border-line p-3.5 transition-colors hover:border-accent/30 hover:bg-accent-soft/20">
                <div className="flex min-w-0 items-start gap-3">
                  <span className="grid h-10 w-8 shrink-0 place-items-center rounded-md border border-line bg-sunken text-ink-3"><FileText className="h-4 w-4" aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <bdi className="block truncate font-mono text-xs font-semibold text-ink">{s.file.split("/").pop()}</bdi>
                    <p className="mt-1 line-clamp-3 text-sm leading-snug text-ink-2">{label(t.upload.sampleText, s.scenario, s.description)}</p>
                  </div>
                </div>
                <Button size="sm" className="mt-auto self-start" onClick={() => uploadSample(s.file)}><CloudUpload className="h-3.5 w-3.5" aria-hidden />{t.inbox.upload}</Button>
              </li>
            ))}
          </ul>}
      </Panel>
      </>}
    </div>
  );
}
