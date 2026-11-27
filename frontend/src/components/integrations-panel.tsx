"use client";

import { Copy, KeyRound, RefreshCw, Webhook } from "lucide-react";
import { Fragment, useState } from "react";
import { toast } from "sonner";
import { api, ApiError, useApi } from "@/lib/api";
import { dateTime, relative } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";
import { Button, cx, EmptyState, Field, Input, Panel, PanelHeader, Table, Td, Th } from "./ui";

type ApiKey = { id: string; name: string; scope: "read" | "read_write"; prefix: string; created_at: string;
  last_used_at: string | null; revoked_at: string | null };
type Endpoint = { id: string; url: string; description: string | null; events: string[]; active: boolean; secret_hint: string; created_at: string };
type Attempt = { attempt: number; at: string; status_code: number | null; error: string | null; duration_ms: number };
type Delivery = { id: string; event_type: string; is_test: boolean; status: "pending" | "retrying" | "succeeded" | "failed"; attempts: number;
  last_status_code: number | null; last_error: string | null; created_at: string; next_attempt_at: string | null;
  delivered_at: string | null; attempt_log: Attempt[] };

const SCOPES = ["read", "read_write"] as const;

/** A secret that is shown once: selectable text, a copy button, and an explicit "I have stored it". */
function SecretReveal({ title, body, secret, extra, onDone }: { title: string; body: string; secret: string; extra?: React.ReactNode; onDone: () => void }) {
  const { t } = useI18n();
  const it = t.integrations;
  const copy = async () => {
    try { await navigator.clipboard.writeText(secret); toast.success(it.copied); }
    catch { toast.error(it.copyFailed); }
  };
  return (
    <div role="status" className="m-4 space-y-3 rounded-2xl border border-ok/30 bg-ok-soft p-4 text-sm">
      <p className="font-semibold text-ink">{title}</p>
      <p className="text-ink-2">{body}</p>
      <div className="flex flex-wrap items-center gap-2">
        <code dir="ltr" data-testid="one-time-secret" className="min-w-0 max-w-full flex-1 select-all break-all rounded-xl border border-line bg-surface px-3 py-2 font-mono text-sm text-ink">{secret}</code>
        <Button size="sm" onClick={copy}><Copy className="h-4 w-4" aria-hidden />{it.copy}</Button>
      </div>
      {extra}
      <Button size="sm" variant="primary" onClick={onDone}>{it.stored}</Button>
    </div>
  );
}

/** The keys of this workspace: create (the secret is shown once), see last use, revoke. */
export function ApiKeysPanel() {
  const { t, locale } = useI18n();
  const it = t.integrations;
  const { data, error, mutate } = useApi<{ items: ApiKey[] }>("/api/org/api-keys");
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [scope, setScope] = useState<(typeof SCOPES)[number]>("read");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ secret: string }>("/api/org/api-keys", { name: name.trim(), scope });
      setCreated(r.secret); setAdding(false); setName(""); setScope("read"); mutate();
    } catch (e) { toast.error(e instanceof ApiError ? String(e.message) : t.common.error); } finally { setBusy(false); }
  };
  const revoke = async (k: ApiKey) => {
    try { await api.del(`/api/org/api-keys/${k.id}`); toast.success(it.keyRevoked); setConfirming(null); mutate(); }
    catch (e) { toast.error(e instanceof ApiError ? String(e.message) : t.common.error); }
  };
  const items = data?.items ?? [];

  return (
    <Panel>
      <PanelHeader title={it.apiKeysTitle} sub={it.apiKeysSub}
        actions={!adding ? <Button size="sm" onClick={() => { setAdding(true); setCreated(null); }}><KeyRound className="h-4 w-4" aria-hidden />{it.newKey}</Button> : undefined} />
      {error && <p role="alert" className="px-5 py-3 text-sm text-danger">{it.loadError}</p>}
      {created && <SecretReveal title={it.keyCreatedTitle} body={it.keyCreatedBody} secret={created} onDone={() => setCreated(null)}
        extra={<p className="text-xs text-ink-3"><bdi dir="ltr" className="font-mono">{it.keyUsage}</bdi></p>} />}
      {adding && (
        <form className="space-y-4 border-b border-line px-5 py-5" onSubmit={(e) => { e.preventDefault(); if (name.trim() && !busy) void create(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={it.keyName} hint={it.keyNameHint} htmlFor="api-key-name">
              <Input id="api-key-name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-ink-2">{it.access}</legend>
            {SCOPES.map((s) => (
              <label key={s} className={cx("flex cursor-pointer items-start gap-3 rounded-xl border border-line px-4 py-3 text-sm hover:bg-sunken", scope === s && "border-accent/60 bg-accent-soft/40")}>
                <input type="radio" name="api-key-scope" className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]" checked={scope === s} onChange={() => setScope(s)} />
                <span><span className="block font-semibold text-ink">{s === "read" ? it.scopeRead : it.scopeReadWrite}</span>
                  <span className="text-ink-3">{s === "read" ? it.scopeReadHelp : it.scopeReadWriteHelp}</span></span>
              </label>
            ))}
          </fieldset>
          <div className="flex gap-2">
            <Button type="submit" variant="primary" loading={busy} disabled={!name.trim()}>{it.createKey}</Button>
            <Button type="button" onClick={() => setAdding(false)} disabled={busy}>{it.cancel}</Button>
          </div>
        </form>
      )}
      {data && items.length === 0 && !adding && <EmptyState icon={<KeyRound />} title={it.noKeys} />}
      {items.length > 0 && (
        <Table>
          <thead><tr><Th>{it.keyName}</Th><Th>{it.access}</Th><Th>{it.lastUsed}</Th><Th>{it.createdOn}</Th><Th><span className="sr-only">{t.common.actions}</span></Th></tr></thead>
          <tbody>{items.map((k) => (
            <tr key={k.id} className={cx(k.revoked_at && "text-ink-3")}>
              <Td><span className="block font-medium text-ink"><bdi>{k.name}</bdi></span><bdi dir="ltr" className="font-mono text-xs text-ink-3">{k.prefix}…</bdi></Td>
              <Td>{k.scope === "read" ? it.scopeRead : it.scopeReadWrite}{k.revoked_at && <span className="ms-2 rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink-3">{it.revoked}</span>}</Td>
              <Td>{k.last_used_at ? relative(k.last_used_at, locale) : it.neverUsed}</Td>
              <Td>{dateTime(k.created_at, locale)}</Td>
              <Td className="text-end">
                {!k.revoked_at && (confirming === k.id ? (
                  <span className="flex flex-wrap items-center justify-end gap-2">
                    <span className="text-sm text-ink-2">{it.revokeConfirm.replace("{name}", k.name)}</span>
                    <Button size="sm" variant="danger" onClick={() => revoke(k)}>{it.revokeKey}</Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>{it.cancel}</Button>
                  </span>
                ) : <Button size="sm" variant="danger" onClick={() => setConfirming(k.id)} aria-label={`${it.revoke} · ${k.name}`}>{it.revoke}</Button>)}
              </Td>
            </tr>))}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}

const STATUS_STYLE: Record<Delivery["status"], string> = {
  pending: "bg-info-soft text-info", retrying: "bg-warn-soft text-warn", succeeded: "bg-ok-soft text-ok", failed: "bg-danger-soft text-danger",
};

function DeliveryLog({ id }: { id: string }) {
  const { t, locale } = useI18n();
  const it = t.integrations;
  const { data, error, mutate, isValidating } = useApi<{ items: Delivery[] }>(`/api/org/webhooks/${id}/deliveries?page_size=20`, { refreshInterval: 5000 });
  const statusLabel = (s: Delivery["status"]) => ({ pending: it.statusPending, retrying: it.statusRetrying, succeeded: it.statusSucceeded, failed: it.statusFailed })[s];
  const items = data?.items ?? [];
  return (
    <div className="border-t border-line bg-sunken/40">
      <div className="flex items-center justify-between gap-3 px-5 py-3">
        <h3 className="text-sm font-bold text-ink">{it.logTitle}</h3>
        <Button size="sm" variant="ghost" onClick={() => mutate()} loading={isValidating}><RefreshCw className="h-3.5 w-3.5" aria-hidden />{it.refresh}</Button>
      </div>
      {error && <p role="alert" className="px-5 pb-3 text-sm text-danger">{it.loadError}</p>}
      {data && items.length === 0 && <p className="px-5 pb-4 text-sm text-ink-3">{it.noDeliveries}</p>}
      {items.length > 0 && (
        <Table>
          <thead><tr><Th>{it.event}</Th><Th>{it.result}</Th><Th>{it.attempts}</Th><Th>{it.when}</Th></tr></thead>
          <tbody>{items.map((d) => (
            <tr key={d.id}>
              <Td><span className="block text-ink">{label(it.eventNames, d.event_type)}</span><bdi dir="ltr" className="font-mono text-xs text-ink-3">{d.event_type}</bdi></Td>
              <Td>
                <span className={cx("rounded-full px-2 py-0.5 text-xs font-semibold", STATUS_STYLE[d.status])}>{statusLabel(d.status)}</span>
                {d.last_status_code !== null && <bdi dir="ltr" className="ms-2 font-mono text-xs text-ink-3">HTTP {d.last_status_code}</bdi>}
                {d.last_error && d.status !== "succeeded" && <span className="mt-1 block max-w-md whitespace-normal text-xs text-ink-3">{d.last_error}</span>}
                {d.status === "retrying" && d.next_attempt_at && <span className="block text-xs text-ink-3">{it.nextAttempt}: {dateTime(d.next_attempt_at, locale)}</span>}
              </Td>
              <Td className="tabular-nums">{d.attempts}</Td>
              <Td>{dateTime(d.delivered_at ?? d.created_at, locale)}</Td>
            </tr>))}
          </tbody>
        </Table>
      )}
    </div>
  );
}

/** Webhook endpoints: register, choose events, test, switch off, rotate the secret, and read each endpoint's delivery log. */
export function WebhooksPanel() {
  const { t } = useI18n();
  const it = t.integrations;
  const { data, error, mutate } = useApi<{ items: Endpoint[]; event_types: string[] }>("/api/org/webhooks");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ url: "", description: "", events: [] as string[] });
  const [busy, setBusy] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ value: string; title: string } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<{ id: string; kind: "rotate" | "remove" } | null>(null);
  const eventTypes = data?.event_types ?? [];
  const items = data?.items ?? [];
  const fail = (e: unknown) => toast.error(e instanceof ApiError ? String(e.message) : t.common.error);

  const toggleEvent = (ev: string) => setForm((f) => ({ ...f, events: f.events.includes(ev) ? f.events.filter((x) => x !== ev) : [...f.events, ev] }));
  const create = async () => {
    setBusy("create");
    try {
      const r = await api.post<{ secret: string }>("/api/org/webhooks", { url: form.url.trim(), events: form.events, description: form.description.trim() || null });
      setSecret({ value: r.secret, title: it.webhookCreatedTitle }); setAdding(false); setForm({ url: "", description: "", events: [] });
      toast.success(it.webhookAdded); mutate();
    } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const run = async (key: string, action: () => Promise<unknown>, done?: string) => {
    setBusy(key);
    try { await action(); if (done) toast.success(done); await mutate(); } catch (e) { fail(e); } finally { setBusy(null); setConfirming(null); }
  };

  return (
    <Panel>
      <PanelHeader title={it.webhooksTitle} sub={it.webhooksSub}
        actions={!adding ? <Button size="sm" onClick={() => { setAdding(true); setSecret(null); }}><Webhook className="h-4 w-4" aria-hidden />{it.newWebhook}</Button> : undefined} />
      {error && <p role="alert" className="px-5 py-3 text-sm text-danger">{it.loadError}</p>}
      {secret && <SecretReveal title={secret.title} body={it.webhookCreatedBody} secret={secret.value} onDone={() => setSecret(null)} />}
      {adding && (
        <form className="space-y-4 border-b border-line px-5 py-5" onSubmit={(e) => { e.preventDefault(); if (form.url.trim() && form.events.length && !busy) void create(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={it.url} hint={it.urlHint} htmlFor="webhook-url">
              <Input id="webhook-url" dir="ltr" type="url" inputMode="url" placeholder="https://" maxLength={2000} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} required />
            </Field>
            <Field label={it.description} hint={it.descriptionHint} htmlFor="webhook-description">
              <Input id="webhook-description" maxLength={200} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-ink-2">{it.events}</legend>
            {eventTypes.map((ev) => (
              <label key={ev} className="flex cursor-pointer items-start gap-3 rounded-xl border border-line px-4 py-3 text-sm hover:bg-sunken">
                <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]" checked={form.events.includes(ev)} onChange={() => toggleEvent(ev)} />
                <span><span className="block font-semibold text-ink">{label(it.eventNames, ev)} <bdi dir="ltr" className="font-mono text-xs font-normal text-ink-3">{ev}</bdi></span>
                  <span className="text-ink-3">{label(it.eventHelp, ev, "")}</span></span>
              </label>
            ))}
          </fieldset>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" variant="primary" loading={busy === "create"} disabled={!form.url.trim() || form.events.length === 0}>{it.createWebhook}</Button>
            <Button type="button" onClick={() => setAdding(false)} disabled={busy === "create"}>{it.cancel}</Button>
            {form.events.length === 0 && <span className="text-xs text-ink-3">{it.selectEvent}</span>}
          </div>
        </form>
      )}
      {data && items.length === 0 && !adding && <EmptyState icon={<Webhook />} title={it.noWebhooks} />}
      <ul className="divide-y divide-line">
        {items.map((w) => (
          <Fragment key={w.id}>
            <li className="space-y-3 px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
                    <bdi dir="ltr" className="break-all font-mono text-sm">{w.url}</bdi>
                    {!w.active && <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-semibold text-ink-3">{it.off}</span>}
                  </p>
                  {w.description && <p className="text-sm text-ink-2"><bdi>{w.description}</bdi></p>}
                  <p className="mt-1 text-xs text-ink-3">{w.events.map((e) => label(it.eventNames, e)).join(" · ")} · {it.secretEnds} <bdi dir="ltr" className="font-mono">{w.secret_hint}</bdi></p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" loading={busy === `test:${w.id}`} onClick={() => run(`test:${w.id}`, async () => { await api.post(`/api/org/webhooks/${w.id}/test`); setOpen(w.id); }, it.testQueued)}>{it.sendTest}</Button>
                  <Button size="sm" variant="secondary" aria-expanded={open === w.id} onClick={() => setOpen(open === w.id ? null : w.id)}>{open === w.id ? it.hideDeliveries : it.deliveries}</Button>
                  <Button size="sm" variant="ghost" loading={busy === `toggle:${w.id}`} onClick={() => run(`toggle:${w.id}`, () => api.patch(`/api/org/webhooks/${w.id}`, { active: !w.active }), it.updated)}>{w.active ? it.disable : it.enable}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirming({ id: w.id, kind: "rotate" })}>{it.rotateSecret}</Button>
                  <Button size="sm" variant="danger" onClick={() => setConfirming({ id: w.id, kind: "remove" })}>{it.remove}</Button>
                </div>
              </div>
              {confirming?.id === w.id && (
                <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-sunken px-4 py-3 text-sm">
                  <span className="text-ink-2">{confirming.kind === "rotate" ? it.rotateConfirm : it.removeConfirm}</span>
                  {confirming.kind === "rotate"
                    ? <Button size="sm" variant="primary" loading={busy === `rotate:${w.id}`} onClick={() => run(`rotate:${w.id}`, async () => {
                        const r = await api.post<{ secret: string }>(`/api/org/webhooks/${w.id}/rotate-secret`);
                        setSecret({ value: r.secret, title: it.secretRotated });
                      })}>{it.rotateSecret}</Button>
                    : <Button size="sm" variant="danger" loading={busy === `remove:${w.id}`} onClick={() => run(`remove:${w.id}`, async () => { await api.del(`/api/org/webhooks/${w.id}`); if (open === w.id) setOpen(null); }, it.removed)}>{it.remove}</Button>}
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>{it.cancel}</Button>
                </div>
              )}
            </li>
            {open === w.id && <li className="list-none"><DeliveryLog id={w.id} /></li>}
          </Fragment>
        ))}
      </ul>
    </Panel>
  );
}
