"use client";

import { Bot, ChevronDown, Cpu, User } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { dateTime } from "@/lib/format";
import { cx } from "./ui";

export type AuditEntry = {
  id: string; created_at: string; actor_type: string; actor_label: string | null; action: string; entity_type: string;
  entity_id: string | null; before: Record<string, unknown> | null; after: Record<string, unknown> | null;
  meta: Record<string, unknown>; hash: string; prev_hash: string | null;
};

function Diff({ before, after }: { before: Record<string, unknown> | null; after: Record<string, unknown> | null }) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  const fmt = (v: unknown) => (v === null || v === undefined ? "∅" : typeof v === "object" ? JSON.stringify(v) : String(v));
  const rows = keys.filter((k) => fmt(before?.[k]) !== fmt(after?.[k]));
  if (!rows.length) return null;
  return (
    <table className="mt-2 w-full text-xs">
      <tbody>
        {rows.map((k) => (
          <tr key={k} className="align-top">
            <td className="w-36 py-0.5 pe-2 font-mono text-ink-3">{k}</td>
            {before && <td className="py-0.5 pe-2 text-danger line-through decoration-danger/40"><span dir="auto" className="break-all">{fmt(before?.[k])}</span></td>}
            <td className="py-0.5 text-ok"><span dir="auto" className="break-all">{fmt(after?.[k])}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AuditList({ items }: { items: AuditEntry[] }) {
  const { locale } = useI18n();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <ol className="relative">
      {items.map((a) => {
        const Icon = a.actor_type === "agent" ? Bot : a.actor_type === "system" ? Cpu : User;
        const expanded = open === a.id;
        return (
          <li key={a.id} className="border-b border-line last:border-0">
            <button className="flex w-full items-center gap-3 px-4 py-2.5 text-start hover:bg-sunken/60" onClick={() => setOpen(expanded ? null : a.id)} aria-expanded={expanded}>
              <span className={cx("grid h-7 w-7 shrink-0 place-items-center rounded-full", a.actor_type === "agent" ? "bg-ai-soft text-ai" : a.actor_type === "system" ? "bg-sunken text-ink-2" : "bg-accent-soft text-accent-ink")}>
                <Icon className="h-3.5 w-3.5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1">
                <span className="break-all font-mono text-sm text-ink">{a.action}</span>
                <span className="ms-2 text-xs text-ink-3">{a.actor_label ?? a.actor_type}</span>
              </span>
              <span className="text-xs text-ink-3">{dateTime(a.created_at, locale)}</span>
              <ChevronDown className={cx("h-4 w-4 text-ink-3 transition-transform", expanded && "rotate-180")} />
            </button>
            {expanded && (
              <div className="px-4 pb-3 ps-14">
                <Diff before={a.before} after={a.after} />
                {Object.keys(a.meta ?? {}).length > 0 && (
                  <pre className="mt-2 overflow-x-auto rounded bg-sunken p-2 font-mono text-2xs text-ink-2" dir="ltr">{JSON.stringify(a.meta, null, 2)}</pre>
                )}
                <p className="mt-2 font-mono text-2xs text-ink-3" dir="ltr">sha256 {a.hash.slice(0, 24)}… ← {a.prev_hash ? `${a.prev_hash.slice(0, 12)}…` : "genesis"}</p>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
