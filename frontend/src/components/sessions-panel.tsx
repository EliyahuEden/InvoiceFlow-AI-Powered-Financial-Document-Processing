"use client";

import { Laptop, Smartphone } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, Panel, PanelHeader } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { relative } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Row = { id: string; current: boolean; created_at: string; last_used_at: string | null; expires_at: string;
  ip: string | null; user_agent: string | null };

/** "Chrome on Windows" from a user-agent string; unknown parts stay unknown. */
export function deviceLabel(ua: string | null, unknown: string, on: string): { label: string; mobile: boolean } {
  if (!ua) return { label: unknown, mobile: false };
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Firefox\//.test(ua) ? "Firefox"
    : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : null;
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows"
    : /Mac OS X|Macintosh/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : null;
  const label = browser && os ? `${browser} ${on} ${os}` : browser ?? os ?? unknown;
  return { label, mobile: /iPhone|Android|Mobile/.test(ua) };
}

/** The current user's signed-in browsers, with "sign out" for the ones that are not this device. */
export function SessionsPanel() {
  const { t, locale } = useI18n();
  const st = t.sessions;
  const { data, mutate } = useApi<{ items: Row[] }>("/api/auth/sessions");
  const [busy, setBusy] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  // this device first, then the most recently used; a long history folds behind "show all"
  const rows = [...(data?.items ?? [])].sort((a, b) => Number(b.current) - Number(a.current)
    || (b.last_used_at ?? b.created_at).localeCompare(a.last_used_at ?? a.created_at));
  const shown = all ? rows : rows.slice(0, 5);
  const signOut = async (id: string) => {
    setBusy(id);
    try { await api.del(`/api/auth/sessions/${id}`); toast.success(st.signedOut); mutate(); }
    catch { toast.error(t.common.error); } finally { setBusy(null); }
  };
  return (
    <Panel>
      <PanelHeader title={st.title} sub={st.sub} />
      <ul className="divide-y divide-line">
        {shown.map((s) => {
          const d = deviceLabel(s.user_agent, st.unknownDevice, st.on);
          const Icon = d.mobile ? Smartphone : Laptop;
          return (
            <li key={s.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink-2"><Icon className="h-4 w-4" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                  <span dir="ltr">{d.label}</span>
                  {s.current && <span className="rounded-full bg-ok-soft px-2 py-0.5 text-xs font-semibold text-ok">{st.thisDevice}</span>}
                </p>
                <p className="text-xs text-ink-3">
                  {st.lastActive} {relative(s.last_used_at ?? s.created_at, locale)}{s.ip && <> · <span dir="ltr">{s.ip}</span></>}
                </p>
              </div>
              {!s.current && (
                <Button variant="secondary" size="sm" loading={busy === s.id} onClick={() => signOut(s.id)}
                  aria-label={`${st.signOut} · ${d.label}`}>{st.signOut}</Button>
              )}
            </li>
          );
        })}
      </ul>
      {rows.length > 5 && <div className="border-t border-line px-4 py-2.5">
        <Button variant="ghost" size="sm" aria-expanded={all} onClick={() => setAll(!all)}>{all ? st.showFewer : st.showAll.replace("{n}", String(rows.length))}</Button>
      </div>}
    </Panel>
  );
}
