"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Download, FileSpreadsheet, Upload, X } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Segmented } from "@/components/list";
import { Button, Table, Td, Th, cx } from "@/components/ui";
import { api, ApiError, downloadFile } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

export type ImportKind = "suppliers" | "purchase-orders" | "goods-receipts";

type ImportError = { row: number; column: string; code: string; message: string };
type Preview = {
  summary: { create: number; update: number; skip: number };
  errors: ImportError[];
  error_count: number;
};

/** Spreadsheet import: choose a file, check it (nothing is written), then import it all at once. */
export function ImportDialog({ kinds, onDone }: { kinds: ImportKind[]; onDone: () => void }) {
  const { t } = useI18n();
  const m = t.imports;
  const fileId = useId();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ImportKind>(kinds[0] ?? "suppliers");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState<"check" | "commit" | null>(null);

  const reset = () => { setFile(null); setPreview(null); };
  const send = async (commit: boolean) => {
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setBusy(commit ? "commit" : "check");
    try {
      const result = await api.post<Preview>(`/api/import/${kind}?commit=${commit}`, body);
      if (commit) {
        const { create, update } = result.summary;
        toast.success(`${m.done}: ${create + update}`);
        setOpen(false);
        reset();
        onDone();
      } else {
        setPreview(result);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setBusy(null);
    }
  };
  const template = () => downloadFile(`/api/import/${kind}/template.csv`, `${kind}-template.csv`).catch(() => toast.error(t.common.error));

  const s = preview?.summary;
  const canCommit = !!preview && preview.error_count === 0 && !!s && s.create + s.update > 0;

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
      <Dialog.Trigger asChild>
        <Button><Upload className="h-4 w-4" aria-hidden />{m.open}</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[2px] data-[state=open]:animate-[fade_150ms_ease-out]" />
        <Dialog.Content
          className="fixed inset-x-0 top-[8vh] z-50 mx-auto flex max-h-[84vh] w-[calc(100%-32px)] max-w-[640px] flex-col rounded-xl border border-line bg-surface shadow-pop data-[state=open]:animate-[palette-in_180ms_cubic-bezier(.16,1,.3,1)]">
          <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <Dialog.Title className="text-lg font-semibold tracking-tight text-ink">{m.title}</Dialog.Title>
              <Dialog.Description className="text-sm text-ink-3">{m.sub}</Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label={t.common.close}><X className="h-4 w-4" aria-hidden /></Button>
            </Dialog.Close>
          </header>

          <div className="space-y-4 overflow-y-auto px-5 py-4">
            {kinds.length > 1 && (
              <Segmented value={kind} onChange={(v) => { setKind(v as ImportKind); reset(); }}
                options={kinds.map((k) => ({ value: k, label: label(m.kind, k) }))} />
            )}
            <p className="text-sm text-ink-2">{m.rules}</p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-0 flex-1">
                <label htmlFor={fileId} className="mb-1.5 block text-sm font-medium text-ink-2">{m.file}</label>
                <input id={fileId} type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }}
                  className="block w-full text-sm text-ink-2 file:me-3 file:h-9 file:rounded-md file:border-0 file:bg-sunken file:px-3 file:text-sm file:font-medium file:text-ink hover:file:bg-line/60" />
              </div>
              <Button variant="ghost" onClick={template}><Download className="h-4 w-4" aria-hidden />{m.template}</Button>
            </div>

            {preview && s && (
              <div aria-live="polite" className="space-y-3">
                <dl className="grid grid-cols-3 gap-2">
                  {([["create", s.create], ["update", s.update], ["skip", s.skip]] as const).map(([k, n]) => (
                    <div key={k} className="rounded-lg border border-line px-3 py-2">
                      <dt className="text-xs text-ink-3">{m[k]}</dt>
                      <dd className="text-xl font-medium text-ink num">{n}</dd>
                    </div>
                  ))}
                </dl>
                {preview.error_count > 0 ? (
                  <div className="space-y-2">
                    <p role="alert" className="text-sm font-medium text-danger">{m.errors} (<span className="num">{preview.error_count}</span>)</p>
                    <div className="max-h-64 overflow-y-auto rounded-lg border border-line">
                      <Table>
                        <thead><tr><Th className="w-16">{m.row}</Th><Th>{m.column}</Th><Th>{m.problem}</Th></tr></thead>
                        <tbody>
                          {preview.errors.map((e, i) => (
                            <tr key={`${e.row}-${e.column}-${i}`}>
                              <Td className="num">{e.row}</Td>
                              <Td><span className="ltr font-mono text-xs">{e.column}</span></Td>
                              <Td className="text-ink-2">{label(m.codes, e.code, e.message)}</Td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                    {preview.error_count > preview.errors.length && (
                      <p className="text-xs text-ink-3"><span className="num">{preview.error_count - preview.errors.length}</span> {m.moreErrors}</p>
                    )}
                  </div>
                ) : (
                  <p className={cx("flex items-center gap-2 text-sm", canCommit ? "text-ink" : "text-ink-3")}>
                    <FileSpreadsheet className="h-4 w-4 text-ink-3" aria-hidden />{canCommit ? m.ready : m.nothing}
                  </p>
                )}
              </div>
            )}
          </div>

          <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">
            <Button onClick={() => send(false)} disabled={!file} loading={busy === "check"}>{m.check}</Button>
            <Button variant="primary" onClick={() => send(true)} disabled={!canCommit} loading={busy === "commit"}>{m.commit}</Button>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
