"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { ArrowRight, Bot, Building2, FileText, Languages, Loader2, Moon, Search, ShoppingCart, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useNav } from "@/lib/nav";
import { currentTheme, setTheme } from "@/lib/theme";
import { confirmDraftNavigation } from "@/lib/use-unsaved-work";
import type { NextResp } from "@/lib/types";
import { useSession } from "./session";
import { cx } from "./ui";

type Hit = { id: string; href: string; title: string; sub?: string | null; icon: React.ElementType };
type Results = { invoices: Hit[]; suppliers: Hit[]; pos: Hit[] };
const EMPTY: Results = { invoices: [], suppliers: [], pos: [] };

/** ⌘K / Ctrl+K: jump anywhere and search invoices, suppliers and purchase orders through the
 *  existing list APIs (tenant-scoped and permission-checked by the backend). */
export function CommandPalette({ open, onOpenChange, onAskCopilot }: {
  open: boolean; onOpenChange: (open: boolean) => void; onAskCopilot?: () => void;
}) {
  const { t, locale, setLocale } = useI18n();
  const { can } = useSession();
  const nav = useNav();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results>(EMPTY);
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (!open) { setQuery(""); setResults(EMPTY); } }, [open]);
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setResults(EMPTY); setLoading(false); return; }
    setLoading(true);
    let cancelled = false;
    const timer = setTimeout(async () => {
      const enc = encodeURIComponent(q);
      const [inv, sup, po] = await Promise.all([
        api.get<{ items: { id: string; invoice_number: string | null; supplier_name: string | null }[] }>(`/api/invoices?q=${enc}&page_size=5`).catch(() => ({ items: [] })),
        api.get<{ items: { id: string; name: string }[] }>(`/api/suppliers?q=${enc}&page_size=5`).catch(() => ({ items: [] })),
        api.get<{ items: { id: string; po_number: string; supplier_name?: string | null }[] }>(`/api/purchase-orders?q=${enc}&page_size=5`).catch(() => ({ items: [] })),
      ]);
      if (cancelled) return;
      setResults({
        invoices: inv.items.map((i) => ({ id: i.id, href: `/invoices/${i.id}`, title: i.invoice_number ?? "—", sub: i.supplier_name, icon: FileText })),
        suppliers: sup.items.map((s) => ({ id: s.id, href: `/suppliers/${s.id}`, title: s.name, icon: Building2 })),
        pos: po.items.map((p) => ({ id: p.id, href: `/purchase-orders/${p.id}`, title: p.po_number, sub: p.supplier_name, icon: ShoppingCart })),
      });
      setLoading(false);
    }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  const q = query.trim().toLowerCase();
  const destinations = useMemo(() => nav.flatMap((g) => g.items).filter((i) => !q || i.label.toLowerCase().includes(q)), [nav, q]);
  const go = (href: string) => {
    if (confirmDraftNavigation()) { onOpenChange(false); router.push(href); }
  };
  type Action = { id: string; label: string; icon: React.ElementType; run: () => void };
  const allActions: (Action | false)[] = [
    can("exception:decide") && { id: "next", label: t.review.reviewNext, icon: Sparkles, run: async () => {
      try {
        const r = await api.get<NextResp>("/api/review/next");
        if (r.item) go(`/exceptions/${r.item.exception_id}`); else toast.success(t.review.clearTitle);
      } catch { toast.error(t.common.error); }
    } },
    !!onAskCopilot && { id: "copilot", label: t.copilot.open, icon: Bot, run: () => { onOpenChange(false); onAskCopilot(); } },
    { id: "theme", label: t.palette.toggleTheme, icon: Moon, run: () => { setTheme(currentTheme() === "dark" ? "light" : "dark"); onOpenChange(false); } },
    { id: "lang", label: t.palette.switchLanguage, icon: Languages, run: () => { setLocale(locale === "he" ? "en" : "he"); onOpenChange(false); } },
  ];
  const actions = allActions.filter((a): a is Action => !!a && (!q || a.label.toLowerCase().includes(q)));
  const groups: [string, Hit[]][] = [[t.palette.invoices, results.invoices], [t.palette.suppliers, results.suppliers], [t.palette.purchaseOrders, results.pos]];
  const nothing = !loading && !destinations.length && !actions.length && groups.every(([, hits]) => !hits.length);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[3px] data-[state=open]:animate-[fade_150ms_ease-out]" />
        <Dialog.Content aria-label={t.palette.title} aria-describedby={undefined}
          className="fixed inset-x-3 top-[12vh] z-50 mx-auto max-w-[640px] overflow-hidden rounded-xl border border-line bg-surface shadow-pop data-[state=open]:animate-[palette-in_180ms_cubic-bezier(.16,1,.3,1)]">
          <Dialog.Title className="sr-only">{t.palette.title}</Dialog.Title>
          <Command shouldFilter={false} loop label={t.palette.title} className="flex max-h-[min(70vh,560px)] flex-col">
            <div className="flex items-center gap-3 border-b border-line px-5">
              <Search className="h-5 w-5 shrink-0 text-ink-3" aria-hidden />
              <Command.Input value={query} onValueChange={setQuery} placeholder={t.palette.placeholder}
                className="h-14 w-full bg-transparent text-md text-ink outline-none placeholder:text-ink-3" />
              {loading && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-ink-3" aria-label={t.palette.searching} />}
            </div>
            <Command.List className="overflow-y-auto p-2">
              {nothing && <p className="px-4 py-10 text-center text-sm text-ink-3">{t.palette.empty}</p>}
              {groups.map(([label, hits]) => hits.length > 0 && (
                <Command.Group key={label} heading={label} className="palette-group">
                  {hits.map((h) => <Row key={h.href} value={h.href} icon={h.icon} title={h.title} sub={h.sub} onSelect={() => go(h.href)} />)}
                </Command.Group>
              ))}
              {actions.length > 0 && (
                <Command.Group heading={t.palette.actions} className="palette-group">
                  {actions.map((a) => <Row key={a.id} value={`action:${a.id}`} icon={a.icon} title={a.label} onSelect={a.run} />)}
                </Command.Group>
              )}
              {destinations.length > 0 && (
                <Command.Group heading={t.palette.navigate} className="palette-group">
                  {destinations.map((d) => <Row key={d.href} value={`nav:${d.href}`} icon={d.icon} title={d.label}
                    hint={d.key ? `G ${d.key.toUpperCase()}` : undefined} onSelect={() => go(d.href)} />)}
                </Command.Group>
              )}
            </Command.List>
            <div className="flex items-center justify-between gap-3 border-t border-line bg-sunken/60 px-5 py-2.5 text-xs text-ink-3">
              <span><Kbd>↑</Kbd> <Kbd>↓</Kbd> {t.palette.move} · <Kbd>Enter</Kbd> {t.palette.open}</span>
              <span><Kbd>Esc</Kbd> {t.common.close}</span>
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Row({ value, icon: Icon, title, sub, hint, onSelect }: {
  value: string; icon: React.ElementType; title: string; sub?: string | null; hint?: string; onSelect: () => void;
}) {
  return (
    <Command.Item value={value} onSelect={onSelect}
      className="group flex cursor-pointer items-center gap-3 rounded-2xl px-3 py-2.5 text-ink-2 data-[selected=true]:bg-sunken data-[selected=true]:text-ink">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-sunken text-ink-2 group-data-[selected=true]:bg-surface"><Icon className="h-4 w-4" aria-hidden /></span>
      <span className="min-w-0 flex-1"><bdi className="block truncate font-medium text-ink">{title}</bdi>
        {sub && <bdi className="block truncate text-xs text-ink-3">{sub}</bdi>}</span>
      {hint ? <span className="text-xs text-ink-3">{hint}</span>
        : <ArrowRight className={cx("h-4 w-4 text-ink-3 opacity-0 group-data-[selected=true]:opacity-100 rtl:rotate-180")} aria-hidden />}
    </Command.Item>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="inline-flex min-w-[1.5rem] items-center justify-center rounded-md border border-line bg-surface px-1.5 py-0.5 font-sans text-[0.7rem] font-semibold text-ink-2 shadow-[0_1px_0_rgb(var(--line))]">{children}</kbd>;
}
