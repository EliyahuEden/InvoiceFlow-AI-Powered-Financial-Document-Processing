"use client";

import { Copy, Mail, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, cx, EmptyState, ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export type InboxInfo = {
  enabled: boolean; address: string | null; methods: { imap: boolean; webhook: boolean }; max_attachment_mb: number;
  recent: { id: string; created_at: string; sender: string | null; subject: string | null; status: "accepted" | "partial" | "rejected";
    source: string; attachments: number; accepted: number; problems: { filename: string | null; status: string; reason: string | null }[] }[];
};

/** Marks an invoice that arrived at the organization's forwarding address; shows nothing for a manual upload. */
export function EmailSourceBadge({ source, sender, subject, className }: { source?: string | null; sender?: string | null; subject?: string | null; className?: string }) {
  const { t } = useI18n();
  if (source !== "email") return null;
  const title = [t.emailInbox.badgeTitle.replace("{sender}", sender || "—"), subject].filter(Boolean).join(" · ");
  return <span title={title} data-testid="email-source-badge"
    className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent-ink", className)}>
    <Mail className="h-3 w-3" aria-hidden />{t.emailInbox.badge}<span className="sr-only">: {title}</span>
  </span>;
}

const TONE = { accepted: "bg-ok-soft text-ok", partial: "bg-warn-soft text-warn", rejected: "bg-danger-soft text-danger" } as const;

/** Settings → Email inbox: this organization's forwarding address, and what arrived there recently. */
export function EmailInboxPanel() {
  const { t, locale } = useI18n();
  const { data, error, mutate } = useApi<InboxInfo>("/api/org/inbox");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!data) return <Skeleton className="h-64 w-full" />;
  const e = t.emailInbox;
  const statusLabel = { accepted: e.statusAccepted, partial: e.statusPartial, rejected: e.statusRejected };

  const copy = async () => {
    try { await navigator.clipboard.writeText(data.address ?? ""); toast.success(e.copied); } catch { toast.error(t.common.error); }
  };
  const regenerate = async () => {
    setBusy(true);
    try { await api.post("/api/org/inbox/regenerate"); await mutate(); toast.success(e.regenerated); setConfirming(false); }
    catch (err) { toast.error(err instanceof ApiError ? String(err.message) : t.common.error); } finally { setBusy(false); }
  };

  return <div className="space-y-5">
    <Panel>
      <PanelHeader title={e.title} sub={e.help.replace("{mb}", String(data.max_attachment_mb))} />
      {!data.enabled || !data.address
        ? <div className="px-5 py-5"><EmptyState icon={<Mail className="h-8 w-8" />} title={e.notConfigured} body={e.notConfiguredBody} /></div>
        : <div className="space-y-4 px-5 py-5">
          <div>
            <p className="text-sm font-semibold text-ink" id="inbox-address-label">{e.addressLabel}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <code aria-labelledby="inbox-address-label" dir="ltr" data-testid="inbox-address"
                className="min-w-0 max-w-full select-all break-all rounded-xl border border-line bg-sunken px-3.5 py-2.5 font-mono text-sm text-ink">{data.address}</code>
              <Button onClick={copy}><Copy className="h-4 w-4" aria-hidden />{e.copy}</Button>
            </div>
            <p className="mt-2 text-xs text-ink-3">{e.secretHint}</p>
          </div>
          <div className="border-t border-line pt-4">
            {!confirming
              ? <Button onClick={() => setConfirming(true)}><RefreshCw className="h-4 w-4" aria-hidden />{e.regenerate}</Button>
              : <div role="alertdialog" aria-label={e.regenerateTitle} className="max-w-xl space-y-3 rounded-xl border border-warn/40 bg-warn-soft/50 px-4 py-3.5">
                <p className="text-sm font-semibold text-ink">{e.regenerateTitle}</p>
                <p className="text-sm text-ink-2">{e.regenerateBody}</p>
                <div className="flex gap-2">
                  <Button variant="danger" loading={busy} onClick={regenerate}>{e.regenerateConfirm}</Button>
                  <Button onClick={() => setConfirming(false)} disabled={busy}>{t.common.cancel}</Button>
                </div>
              </div>}
          </div>
        </div>}
    </Panel>

    <Panel>
      <PanelHeader title={e.recent} sub={e.recentHelp} />
      {data.recent.length === 0
        ? <p className="px-5 py-6 text-sm text-ink-3">{e.noMessages}</p>
        : <Table>
          <thead><tr><Th>{e.colWhen}</Th><Th>{e.colFrom}</Th><Th>{e.colSubject}</Th><Th>{e.colResult}</Th></tr></thead>
          <tbody>{data.recent.map((m) => <tr key={m.id}>
            <Td className="whitespace-nowrap text-sm text-ink-2">{dateTime(m.created_at, locale)}</Td>
            <Td className="max-w-[14rem] truncate text-sm"><bdi dir="ltr">{m.sender || "—"}</bdi></Td>
            <Td className="max-w-[16rem] truncate text-sm"><bdi>{m.subject || "—"}</bdi></Td>
            <Td>
              <span className={cx("inline-flex rounded-full px-2 py-0.5 text-xs font-semibold", TONE[m.status])}>{statusLabel[m.status]}</span>
              <span className="mt-1 block whitespace-nowrap text-xs text-ink-3">{e.filesN.replace("{accepted}", String(m.accepted)).replace("{n}", String(m.attachments))}</span>
              {m.problems.length > 0 && <ul className="mt-1 space-y-0.5 text-xs text-ink-3">
                {m.problems.map((p, i) => <li key={i}><bdi>{p.filename || "—"}</bdi>{p.reason ? <>: <bdi>{p.reason}</bdi></> : null}</li>)}
              </ul>}
            </Td>
          </tr>)}</tbody>
        </Table>}
    </Panel>
  </div>;
}
