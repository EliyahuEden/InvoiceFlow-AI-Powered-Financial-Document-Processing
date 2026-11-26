"use client";

import { Bot, ChevronDown, Cpu, User } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import { dateTime } from "@/lib/format";
import { label } from "@/lib/i18n/label";
import { cx } from "./ui";

export type AuditEntry = {
  id: string; created_at: string; actor_type: string; actor_label: string | null; action: string; entity_type: string;
  entity_id: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null;
  meta: Record<string, unknown>; hash: string; prev_hash: string | null;
};

const words = (code: string) => { const w = code.replaceAll("_", " "); return w.charAt(0).toUpperCase() + w.slice(1); };

/** "Invoice uploaded" for invoice.uploaded; an action without a translation reads as its record and verb. */
export function auditLabel(t: Dictionary, action: string): string {
  const known = (t.auditActions as Record<string, string>)[action];
  if (known) return known;
  const [entity = "", ...rest] = action.split(".");
  return `${label(t.auditEntities, entity, words(entity))} · ${words(rest.join(" ") || action)}`;
}

const ROUTES: Record<string, string> = {
  invoice: "/invoices/", exception: "/exceptions/", purchase_order: "/purchase-orders/", agent_run: "/investigations/",
  knowledge_document: "/knowledge/", supplier: "/suppliers/",
};
/** Where the record an event is about can be opened, if it has a page. */
export function auditHref(a: Pick<AuditEntry, "entity_type" | "entity_id" | "meta">): string | null {
  if (a.entity_id && ROUTES[a.entity_type]) return `${ROUTES[a.entity_type]}${a.entity_id}`;
  const invoice = a.meta?.invoice_id;
  return typeof invoice === "string" ? `/invoices/${invoice}` : null;
}

export const ACTOR_ICON = { agent: Bot, system: Cpu, user: User } as const;
export function actorTone(type: string) {
  return type === "agent" ? "bg-ai-soft text-ai" : type === "system" ? "bg-sunken text-ink-2" : "bg-accent-soft text-accent-ink";
}

/** The recorded before/after values of the fields an event changed. */
export function AuditDiff({ before, after, compact = false }: { before: Record<string, unknown> | null; after: Record<string, unknown> | null; compact?: boolean }) {
  const { t } = useI18n();
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  const fmt = (v: unknown) => (v === null || v === undefined ? "∅" : typeof v === "object" ? JSON.stringify(v) : String(v));
  const rows = keys.filter((k) => fmt(before?.[k]) !== fmt(after?.[k]));
  if (!rows.length) return compact ? null : <p className="text-sm text-ink-3">{t.audit.noChanges}</p>;
  return (
    <div className={cx(!compact && "overflow-hidden rounded-xl border border-line")}>
      <table className="w-full text-xs">
        {!compact && <thead className="bg-sunken text-ink-3"><tr>
          <th className="px-3 py-2 text-start font-semibold">{t.audit.change}</th>
          {before && <th className="px-3 py-2 text-start font-semibold">{t.audit.before}</th>}
          <th className="px-3 py-2 text-start font-semibold">{t.audit.after}</th></tr></thead>}
        <tbody className={cx(!compact && "divide-y divide-line")}>
          {rows.map((k) => (
            <tr key={k} className="align-top">
              <td className={cx("font-mono text-ink-3", compact ? "max-w-28 break-all py-0.5 pe-2" : "whitespace-nowrap px-3 py-2")}>{k}</td>
              {before && <td className={cx("text-ink-3 line-through decoration-line-strong", compact ? "py-0.5 pe-2" : "px-3 py-2")}><bdi className="break-all">{fmt(before?.[k])}</bdi></td>}
              <td className={cx("font-medium text-ink", compact ? "py-0.5" : "px-3 py-2")}><bdi className="break-all">{fmt(after?.[k])}</bdi></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A compact event list (the invoice History tab): readable names, expandable recorded details. */
export function AuditList({ items }: { items: AuditEntry[] }) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <ol className="relative">
      {items.map((a) => {
        const Icon = ACTOR_ICON[a.actor_type as keyof typeof ACTOR_ICON] ?? User;
        const expanded = open === a.id;
        return (
          <li key={a.id} className="border-b border-line last:border-0">
            <button className="flex w-full items-center gap-3 px-4 py-2.5 text-start hover:bg-sunken/60" onClick={() => setOpen(expanded ? null : a.id)} aria-expanded={expanded}>
              <span className={cx("grid h-7 w-7 shrink-0 place-items-center rounded-full", actorTone(a.actor_type))}>
                <Icon className="h-3.5 w-3.5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="text-sm font-semibold text-ink">{auditLabel(t, a.action)}</span>
                <span className="ms-2 text-xs text-ink-3"><bdi>{a.actor_label ?? a.actor_type}</bdi></span>
              </span>
              <span className="text-xs text-ink-3">{dateTime(a.created_at, locale)}</span>
              <ChevronDown className={cx("h-4 w-4 text-ink-3 transition-transform", expanded && "rotate-180")} aria-hidden />
            </button>
            {expanded && (
              <div className="min-w-0 bg-sunken/40 px-4 py-3 sm:ps-14">
                <p className="font-mono text-2xs text-ink-3" dir="ltr">{a.action}</p>
                <AuditDiff before={a.before} after={a.after} compact />
                {Object.keys(a.meta ?? {}).length > 0 && (
                  <pre className="mt-2 overflow-x-auto rounded bg-sunken p-2 font-mono text-2xs text-ink-2" dir="ltr">{JSON.stringify(a.meta, null, 2)}</pre>
                )}
                <p className="mt-2 break-all font-mono text-2xs text-ink-3" dir="ltr">sha256 {a.hash} ← {a.prev_hash ?? "genesis"}</p>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
