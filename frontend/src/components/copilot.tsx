"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, ArrowUp, BadgeCheck, Building2, ExternalLink, FileText, Layers, Loader2, ScrollText, ShieldAlert, ShieldCheck, ShoppingCart, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button, cx } from "./ui";

type Citation = { kind: "invoice" | "exception" | "supplier" | "purchase_order" | "document"; id: string; label: string; href: string };
type Step = { tool: string; status?: string; latency_ms?: number };
type Reply = { answer: string; citations: Citation[]; follow_ups: string[]; steps: Step[]; mode: string; language: string; verified: boolean };
type Msg = { role: "user"; content: string } | ({ role: "assistant"; content: string } & Omit<Reply, "answer">);

const ICON: Record<Citation["kind"], React.ElementType> = {
  invoice: FileText, exception: AlertTriangle, supplier: Building2, purchase_order: ShoppingCart, document: ScrollText,
};

/** The record the reviewer is looking at, so "this invoice" means something. */
export function pageContext(path: string): Record<string, string> {
  const invoiceId = path.match(/^\/invoices\/([0-9a-zA-Z-]+)(?:\/|$)/)?.[1];
  if (invoiceId && invoiceId !== "upload") return { invoice_id: invoiceId };
  const exceptionId = path.match(/^\/exceptions\/([0-9a-zA-Z-]+)/)?.[1];
  return exceptionId ? { exception_id: exceptionId } : {};
}

/** AP Copilot: ask about the queue, invoices, suppliers and policies. Read-only: it looks things
 *  up through the same permission-checked tools as the agent and never approves or pays. */
export function CopilotPanel({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useI18n();
  const c = t.copilot;
  const path = usePathname();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [msgs, busy]);

  const send = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: q }]);
    setDraft("");
    setBusy(true);
    setError(false);
    try {
      const r = await api.post<Reply>("/api/copilot/ask", { question: q, history, context: pageContext(path) });
      const { answer, ...rest } = r;
      setMsgs((m) => [...m, { role: "assistant", content: answer, ...rest }]);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  const ctx = pageContext(path);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/15 backdrop-blur-[2px] data-[state=open]:animate-[fade_150ms_ease-out]" />
        <Dialog.Content aria-describedby={undefined}
          className="fixed inset-y-2 end-2 z-50 flex w-[calc(100%-1rem)] max-w-[480px] flex-col overflow-hidden rounded-3xl border border-line bg-bg shadow-pop data-[state=open]:animate-[palette-in_200ms_cubic-bezier(.16,1,.3,1)]">
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_40%_at_80%_0%,rgb(var(--atmosphere-a)/.55),transparent_70%),radial-gradient(60%_40%_at_0%_100%,rgb(var(--atmosphere-c)/.5),transparent_70%)]" />
          <header className="relative flex items-start justify-between gap-3 px-5 pb-3 pt-5">
            <div className="flex items-start gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-[#818cf8] to-[#a78bfa] text-white shadow-[0_10px_24px_-10px_rgb(99_102_241/.8)]"><Sparkles className="h-5 w-5" aria-hidden /></span>
              <div>
                <Dialog.Title className="text-xl font-extrabold tracking-tight text-ink">{c.title}</Dialog.Title>
                <p className="flex items-center gap-1.5 text-xs text-ink-3"><ShieldCheck className="h-3.5 w-3.5" aria-hidden />{c.readOnly}</p>
              </div>
            </div>
            <Dialog.Close asChild><Button variant="ghost" size="icon" aria-label={t.common.close}><X className="h-5 w-5" /></Button></Dialog.Close>
          </header>

          <div className="relative flex-1 space-y-4 overflow-y-auto px-5 py-3" aria-live="polite">
            {msgs.length === 0 && (
              <div className="space-y-3">
                <p className="text-base text-ink-2">{c.intro}</p>
                {c.topics.map((topic) => (
                  <section key={topic.title} className="space-y-1.5">
                    <h3 className="text-sm font-bold text-ink-3">{topic.title}</h3>
                    <ul className="flex flex-wrap gap-1.5">
                      {topic.questions.map((s) => (
                        <li key={s}><button type="button" onClick={() => send(s)}
                          className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-start text-sm font-semibold text-ink-2 shadow-[0_1px_2px_rgb(34_38_92/.05)] transition-colors hover:border-accent/30 hover:bg-accent-soft hover:text-accent-ink">{s}</button></li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )}
            {msgs.map((m, i) => m.role === "user" ? (
              <p key={i} dir="auto" className="ms-auto w-fit max-w-[85%] whitespace-pre-line rounded-2xl rounded-se-md bg-primary px-4 py-2.5 text-base text-primary-ink shadow-[0_8px_20px_-10px_rgb(var(--primary)/.6)]">{m.content}</p>
            ) : (
              <div key={i} className="space-y-2.5">
                <article className="rounded-2xl border border-line bg-surface p-4 shadow-raise">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    {m.verified
                      ? <span className="inline-flex items-center gap-1.5 text-sm font-bold text-ok"><BadgeCheck className="h-4 w-4" aria-hidden />{c.verifiedAnswer}</span>
                      : <span className="inline-flex items-center gap-1.5 text-sm font-bold text-warn"><ShieldAlert className="h-4 w-4" aria-hidden />{c.unverified}</span>}
                    <span className="rounded-full border border-ai-line bg-ai-soft px-2 py-0.5 text-xs font-bold text-ai">{m.mode === "offline" ? c.offline : c.ai}</span>
                  </div>
                  <p dir="auto" className="whitespace-pre-line text-base leading-relaxed text-ink">{m.content}</p>
                </article>
                {m.citations.length > 0 && (
                  <section className="rounded-2xl border border-line bg-surface p-3 shadow-raise">
                    <h3 className="mb-1.5 flex items-center gap-1.5 px-1 text-sm font-bold text-ink"><Layers className="h-4 w-4 text-ink-3" aria-hidden />{c.sources}</h3>
                    <ul className="space-y-1.5" aria-label={c.sources}>
                      {m.citations.map((ci) => {
                        const Icon = ICON[ci.kind];
                        return (
                          <li key={`${ci.kind}:${ci.id}`}>
                            <Link href={ci.href} onClick={() => onOpenChange(false)}
                              className="flex items-center gap-2.5 rounded-xl border border-line px-3 py-2 text-sm transition-colors hover:border-accent/30 hover:bg-accent-soft/50">
                              <Icon className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                              <bdi className="min-w-0 flex-1 truncate font-semibold text-ink">{ci.label}</bdi>
                              <span className="shrink-0 text-xs text-ink-3">{c.kinds[ci.kind]}</span>
                              <ExternalLink className="h-3.5 w-3.5 shrink-0 text-ink-3 rtl:-scale-x-100" aria-hidden />
                            </Link>
                          </li>);
                      })}
                    </ul>
                  </section>
                )}
                {m.steps.length > 0 && (
                  <details className="px-1 text-xs text-ink-3">
                    <summary className="cursor-pointer select-none">{c.steps.replace("{n}", String(m.steps.length))}</summary>
                    <ol className="mt-1.5 space-y-1 ps-4">
                      {m.steps.map((s, j) => (
                        <li key={j} className="flex items-center gap-2"><code dir="ltr" className="font-mono text-ink-2">{s.tool}</code>
                          {s.status === "rejected" && <span className="text-danger">{c.refused}</span>}</li>))}
                    </ol>
                  </details>
                )}
                {m.follow_ups.length > 0 && i === msgs.length - 1 && (
                  <div className="flex flex-wrap gap-1.5">
                    {m.follow_ups.map((f) => <button key={f} type="button" onClick={() => send(f)}
                      className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-semibold text-ink-2 hover:border-accent/30 hover:bg-accent-soft hover:text-accent-ink">{f}</button>)}
                  </div>
                )}
              </div>
            ))}
            {busy && <p className="flex items-center gap-2 text-sm text-ink-3"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{c.thinking}</p>}
            {error && <p role="alert" className="rounded-2xl bg-danger-soft px-4 py-2.5 text-sm text-danger">{c.error}</p>}
            <div ref={end} />
          </div>

          <form className="relative p-4" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
            {(ctx.invoice_id || ctx.exception_id) && (
              <p className="mb-2 text-xs text-ink-3">{ctx.invoice_id ? c.aboutInvoice : c.aboutCase}</p>
            )}
            <div className="flex items-end gap-2 rounded-3xl border border-line bg-surface p-2 shadow-raise focus-within:border-accent/60 focus-within:ring-4 focus-within:ring-accent/15">
              <textarea aria-label={c.placeholder} value={draft} rows={1} maxLength={1000} placeholder={c.placeholder} dir="auto"
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(draft); } }}
                className="max-h-36 min-h-[2.5rem] flex-1 resize-none bg-transparent px-3 py-2 text-base text-ink outline-none placeholder:text-ink-3" />
              <Button type="submit" variant="primary" size="icon" aria-label={c.send} disabled={!draft.trim() || busy}
                className={cx("shrink-0 rounded-full")}><ArrowUp className="h-4 w-4" /></Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
