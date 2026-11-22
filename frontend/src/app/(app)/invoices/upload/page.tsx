"use client";

import { CheckCircle2, CircleAlert, FileText, FileUp, Loader2, Shield, Workflow } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { StatusPill } from "@/components/domain";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, cx, EmptyState, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { onLiveEvent } from "@/lib/events";
import { useI18n } from "@/lib/i18n";

type Item = {
  key: string; name: string; size: number; state: "queued" | "uploading" | "processing" | "done" | "failed" | "duplicate" | "rejected";
  invoiceId?: string; jobId?: string; progress?: number; message?: string; status?: string;
};

type JobStatus = { status: string; progress: number; message: string | null; error: string | null; entity_id: string | null };
type UploadResponse = { invoice_id: string; job_id: string };
const PARALLEL_UPLOADS = 3;

export default function UploadPage() {
  const { t } = useI18n();
  const { can, me } = useSession();
  const allowed = can("invoice:upload");
  const [items, setItems] = useState<Item[]>([]);
  const [drag, setDrag] = useState(false);
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
      const fd = new FormData();
      fd.append("file", list[idx]);
      enqueue(it.key, () => api.post("/api/invoices/upload", fd));
    });
  };

  const uploadSample = (file: string) => {
    const it: Item = { key: crypto.randomUUID(), name: file.split("/").pop()!, size: 0, state: "queued" };
    setItems((prev) => [it, ...prev]);
    enqueue(it.key, () => api.post("/api/invoices/demo/samples/upload", { file }));
  };

  return (
    <div className="space-y-5">
      <PageHeader title={t.upload.title} back={{ href: "/invoices", label: t.nav.inbox }} />
      {!me ? <Skeleton className="h-60" /> : !allowed ? <Panel><EmptyState icon={<Shield className="h-7 w-7" />} title={t.upload.restricted} /></Panel> : (
      <div className="command-layout grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1.85fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <Panel className="command-panel p-3 sm:p-5">
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
            className={cx(
              "flex min-h-80 flex-col items-center justify-center rounded-[20px] border-2 border-dashed px-4 py-12 text-center transition-colors",
              drag ? "border-accent bg-accent-soft" : "border-line-strong bg-sunken hover:border-accent/60",
            )}
          >
            <span className="grid h-16 w-16 place-items-center rounded-[20px] border border-line bg-surface text-accent-ink shadow-raise"><FileUp className="h-8 w-8" aria-hidden /></span>
            <h2 className="mt-5 text-xl font-semibold tracking-tight text-ink sm:text-2xl">{t.upload.drop}</h2>
            <p className="mt-2 max-w-md text-sm text-ink-2">{t.upload.limits}</p>
            <Button className="mt-5" variant="primary" type="button" onClick={() => input.current?.click()}>{t.upload.browse}</Button>
            <input ref={input} type="file" multiple accept="application/pdf,image/png,image/jpeg" hidden aria-label={t.upload.browse}
              onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} data-testid="file-input" />
          </div>
          </Panel>

          {items.length > 0 && (
            <Panel className="command-panel">
              <PanelHeader title={t.inbox.received} actions={<span className="num text-sm text-ink-2">{items.length}</span>} />
              <ul className="divide-y divide-line">
                {items.map((it) => (
                  <li key={it.key} className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-3">
                      {it.state === "done" ? <CheckCircle2 className="h-5 w-5 text-ok" /> :
                        ["failed", "rejected"].includes(it.state) ? <CircleAlert className="h-5 w-5 text-danger" /> :
                        it.state === "duplicate" ? <CircleAlert className="h-5 w-5 text-warn" /> :
                        <Loader2 className="h-5 w-5 animate-spin text-info" />}
                      <div className="min-w-24 flex-1">
                        <p className="truncate text-base font-medium text-ink" dir="auto">{it.name}</p>
                        <p className="break-words text-sm text-ink-2" role="status">{it.message ?? (it.state === "failed" ? t.invoice.failedTitle : it.state === "processing" ? t.invoice.processingNow : t.upload[it.state])}</p>
                      </div>
                      {it.status && <StatusPill status={it.status} />}
                      {it.invoiceId && ["done", "duplicate", "failed"].includes(it.state) && (
                        <Button asChild size="sm"><Link href={`/invoices/${it.invoiceId}`}>{t.upload.openInvoice}</Link></Button>
                      )}
                    </div>
                    {it.state === "processing" && it.progress !== undefined && (
                      <div className="mt-3 flex items-center gap-2">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-label={it.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={it.progress}>
                          <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${it.progress}%` }} />
                        </div>
                        <bdi className="text-xs font-semibold num">{it.progress}%</bdi>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel className="command-panel">
            <PanelHeader title={t.upload.samples} sub={t.upload.samplesHint} />
            {sampleError ? <div className="p-4"><ErrorState message={t.common.error} onRetry={() => reloadSamples()} retryLabel={t.common.retry} /></div> :
             !samples ? <div className="p-4"><Skeleton /></div> : <ul className="divide-y divide-line">
              {samples?.items.map((s) => (
                <li key={s.file} className="flex items-center gap-3 px-4 py-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink"><FileText className="h-4 w-4" aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <bdi className="block truncate font-mono text-xs text-ink">{s.file.split("/").pop()}</bdi>
                    <p className="mt-0.5 text-sm text-ink-2">{s.description}</p>
                  </div>
                  <Button size="sm" onClick={() => uploadSample(s.file)}>{t.inbox.upload}</Button>
                </li>
              ))}
            </ul>}
          </Panel>
        </div>
          <Panel className="command-aside">
            <PanelHeader title={<span className="inline-flex items-center gap-2"><Workflow className="h-5 w-5 text-accent-ink" />{t.upload.steps}</span>} />
            <ol className="p-5 text-sm font-medium text-ink-2">
              {t.upload.pipeline.map((s, i) => (
                <li key={s} className="relative flex min-h-12 items-start gap-3 pb-4 last:min-h-0 last:pb-0">
                  {i !== t.upload.pipeline.length - 1 && <span aria-hidden className="absolute bottom-0 start-[13px] top-7 w-px bg-line-strong" />}
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink">{i + 1}</span>
                  <span className="pt-1">
                  {s}
                  </span>
                </li>
              ))}
            </ol>
          </Panel>
      </div>)}
    </div>
  );
}
