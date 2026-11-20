"use client";

import { CheckCircle2, CircleAlert, FileUp, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { StatusPill } from "@/components/domain";
import { PageHeader } from "@/components/shell";
import { Button, cx, Panel, PanelHeader } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { onLiveEvent } from "@/lib/events";
import { useI18n } from "@/lib/i18n";

type Item = {
  key: string; name: string; size: number; state: "queued" | "uploading" | "processing" | "done" | "failed" | "duplicate" | "rejected";
  invoiceId?: string; jobId?: string; progress: number; message?: string; status?: string;
};

type JobStatus = { status: string; progress: number; message: string | null; error: string | null; entity_id: string | null };

function stepFor(progress: number): number {
  if (progress >= 85) return 5;
  if (progress >= 60) return 3;
  if (progress >= 10) return 2;
  return 1;
}

export default function UploadPage() {
  const { t } = useI18n();
  const [items, setItems] = useState<Item[]>([]);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { data: samples } = useApi<{ items: { file: string; scenario: string; description: string; language: string }[] }>(
    "/api/invoices/demo/samples",
  );

  const patch = useCallback((key: string, p: Partial<Item>) => {
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, ...p } : i)));
  }, []);

  // live progress via SSE; polling below is the fallback
  useEffect(() => onLiveEvent(({ event, data }) => {
    if (!event.startsWith("job.")) return;
    setItems((prev) => prev.map((i) => i.jobId === data.job_id ? {
      ...i, progress: Number(data.progress ?? i.progress), message: (data.message as string) ?? i.message,
      state: event === "job.completed" ? "done" : event === "job.failed" ? "failed" : i.state,
    } : i));
  }), []);

  useEffect(() => {
    const active = items.filter((i) => i.state === "processing" && i.jobId);
    if (!active.length) return;
    const id = setInterval(async () => {
      for (const it of active) {
        try {
          const j = await api.get<JobStatus>(`/api/jobs/${it.jobId}`);
          const done = j.status === "succeeded";
          const failed = j.status === "failed";
          let status: string | undefined;
          if (done && it.invoiceId) status = (await api.get<{ status: string }>(`/api/invoices/${it.invoiceId}`)).status;
          patch(it.key, { progress: j.progress, message: j.error ?? j.message ?? undefined,
            state: done ? "done" : failed ? "failed" : "processing", status });
        } catch { /* transient */ }
      }
    }, 1500);
    return () => clearInterval(id);
  }, [items, patch]);

  const handleResult = (key: string, run: () => Promise<{ invoice_id: string; job_id: string }>) => {
    patch(key, { state: "uploading" });
    run().then((r) => patch(key, { state: "processing", invoiceId: r.invoice_id, jobId: r.job_id, progress: 5 }))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 409) {
          const d = e.detail as { invoice_id?: string };
          patch(key, { state: "duplicate", invoiceId: d?.invoice_id, message: t.upload.duplicate });
        } else {
          patch(key, { state: "rejected", message: e instanceof ApiError ? String(e.message) : t.common.error });
        }
      });
  };

  const addFiles = (files: FileList | File[]) => {
    const list = Array.from(files);
    const fresh: Item[] = list.map((f) => ({ key: `${f.name}-${f.size}-${Math.random()}`, name: f.name, size: f.size, state: "queued", progress: 0 }));
    setItems((prev) => [...fresh, ...prev]);
    fresh.forEach((it, idx) => {
      const fd = new FormData();
      fd.append("file", list[idx]);
      handleResult(it.key, () => api.post("/api/invoices/upload", fd));
    });
  };

  const uploadSample = (file: string) => {
    const it: Item = { key: `${file}-${Date.now()}`, name: file.split("/").pop()!, size: 0, state: "queued", progress: 0 };
    setItems((prev) => [it, ...prev]);
    handleResult(it.key, () => api.post("/api/invoices/demo/samples/upload", { file }));
  };

  return (
    <div className="space-y-5">
      <PageHeader title={t.upload.title} back={{ href: "/invoices", label: t.nav.inbox }} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <label
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
            className={cx(
              "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-14 text-center transition-colors",
              drag ? "border-accent bg-accent-soft/60" : "border-line-strong bg-surface hover:border-accent/60",
            )}
          >
            <FileUp className="h-9 w-9 text-accent" aria-hidden />
            <p className="mt-3 text-md font-medium text-ink">{t.upload.drop}</p>
            <p className="mt-1 text-sm text-ink-3">{t.upload.or}</p>
            <span className="mt-2"><Button variant="primary" type="button" onClick={() => input.current?.click()}>{t.upload.browse}</Button></span>
            <p className="mt-4 max-w-md text-xs text-ink-3">{t.upload.limits}</p>
            <input ref={input} type="file" multiple accept="application/pdf,image/png,image/jpeg" className="sr-only"
              onChange={(e) => e.target.files && addFiles(e.target.files)} data-testid="file-input" />
          </label>

          {items.length > 0 && (
            <Panel>
              <ul className="divide-y divide-line">
                {items.map((it) => (
                  <li key={it.key} className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {it.state === "done" ? <CheckCircle2 className="h-5 w-5 text-ok" /> :
                        ["failed", "rejected"].includes(it.state) ? <CircleAlert className="h-5 w-5 text-danger" /> :
                        it.state === "duplicate" ? <CircleAlert className="h-5 w-5 text-warn" /> :
                        <Loader2 className="h-5 w-5 animate-spin text-info" />}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-base font-medium text-ink" dir="auto">{it.name}</p>
                        <p className="truncate text-xs text-ink-3">{it.message ?? (t.upload as Record<string, unknown>)[it.state === "processing" ? "uploading" : it.state] as string}</p>
                      </div>
                      {it.status && <StatusPill status={it.status} />}
                      {it.invoiceId && ["done", "duplicate", "failed"].includes(it.state) && (
                        <Button asChild size="sm"><Link href={`/invoices/${it.invoiceId}`}>{t.upload.openInvoice}</Link></Button>
                      )}
                    </div>
                    {(it.state === "processing" || it.state === "uploading") && (
                      <div className="mt-3">
                        <div className="h-1.5 overflow-hidden rounded-full bg-sunken">
                          <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${Math.max(4, it.progress)}%` }} />
                        </div>
                        <ol className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-2xs text-ink-3">
                          {t.upload.pipeline.map((s, i) => (
                            <li key={s} className={cx(i <= stepFor(it.progress) && "text-accent-ink font-medium")}>{s}</li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>

        <div className="space-y-5">
          <Panel>
            <PanelHeader title={t.upload.samples} sub={t.upload.samplesHint} />
            <ul className="divide-y divide-line">
              {samples?.items.map((s) => (
                <li key={s.file} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs text-ink">{s.file.split("/").pop()}</p>
                    <p className="mt-0.5 text-sm text-ink-2">{s.description}</p>
                  </div>
                  <Button size="sm" onClick={() => uploadSample(s.file)}>{t.inbox.upload}</Button>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel className="p-4">
            <h2 className="flex items-center gap-2 text-md font-semibold"><Sparkles className="h-4 w-4 text-ai" />{t.upload.steps}</h2>
            <ol className="mt-3 space-y-2 text-sm text-ink-2">
              {t.upload.pipeline.map((s, i) => (
                <li key={s} className="flex gap-2.5">
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-sunken text-2xs font-semibold text-ink-2">{i + 1}</span>
                  {s}
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  );
}
