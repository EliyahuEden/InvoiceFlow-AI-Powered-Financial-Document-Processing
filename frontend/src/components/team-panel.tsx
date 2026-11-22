"use client";

import { Copy, KeyRound, UserMinus, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSession } from "./session";
import { Button, Field, Input, Panel, PanelHeader, Select, Table, Td, Th } from "./ui";

type Member = { id: string; email: string; full_name: string; role: string; is_active: boolean };
const ROLES = ["admin", "finance_reviewer", "procurement_manager", "read_only"];

/** A one-time password for a new teammate: 16 characters from a crypto source, no look-alike characters. */
export function generatePassword(length = 16): string {
  const chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-";
  const bytes = new Uint32Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}

/** Team management: who works in this business and with which role. Administrators add and remove people. */
export function TeamPanel() {
  const { t } = useI18n();
  const tm = t.team;
  const { can, me } = useSession();
  const admin = can("org:manage");
  const { data, mutate } = useApi<{ items: Member[] }>("/api/org/members");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", role: "finance_reviewer", password: "" });
  const [created, setCreated] = useState<{ email: string; password: string | null } | null>(null);
  const { data: options } = useApi<{ email_enabled: boolean }>("/api/auth/options");
  const emailOn = !!options?.email_enabled;
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const add = async () => {
    setBusy(true);
    // With email on, an empty password means "send an invitation"; without it, a one-time password is generated.
    const password = form.password || (emailOn ? null : generatePassword());
    try {
      const r = await api.post<{ invited: boolean }>("/api/org/members", { ...form, password });
      setCreated({ email: form.email, password: r?.invited ? null : password });
      setForm({ email: "", full_name: "", role: "finance_reviewer", password: "" });
      setAdding(false);
      mutate();
    } catch (e) {
      toast.error(e instanceof ApiError && e.status === 409 ? tm.alreadyMember : t.common.error);
    } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    try { await api.del(`/api/org/members/${id}`); toast.success(tm.removed); setConfirming(null); mutate(); }
    catch (e) { toast.error(e instanceof ApiError ? String(e.message) : t.common.error); }
  };
  const changeRole = async (id: string, role: string) => {
    try { await api.patch(`/api/org/members/${id}`, { role }); mutate(); toast.success(t.common.save); }
    catch (e) { toast.error(String((e as Error).message)); }
  };
  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email) && form.full_name.trim().length >= 2
    && (!form.password || form.password.length >= 12);

  return (
    <Panel>
      <PanelHeader title={tm.title} sub={tm.sub}
        actions={admin && !adding ? <Button size="sm" onClick={() => setAdding(true)}><UserPlus className="h-4 w-4" aria-hidden />{tm.add}</Button> : undefined} />
      {created && (
        <div role="status" className="m-4 rounded-2xl border border-ok/30 bg-ok-soft p-4 text-sm">
          <p className="font-semibold text-ink">{(created.password ? tm.createdTitle : tm.invitedTitle).replace("{email}", created.email)}</p>
          <p className="mt-1 text-ink-2">{created.password ? tm.createdHint : tm.invitedHint}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {created.password && <>
              <code dir="ltr" className="rounded-lg bg-surface px-3 py-1.5 font-mono text-ink">{created.password}</code>
              <Button size="sm" variant="secondary" onClick={() => { navigator.clipboard?.writeText(created.password ?? ""); toast.success(tm.copied); }}>
                <Copy className="h-4 w-4" aria-hidden />{tm.copy}</Button>
            </>}
            <Button size="sm" variant="ghost" onClick={() => setCreated(null)}>{t.common.close}</Button>
          </div>
        </div>
      )}
      {adding && (
        <form className="grid gap-3 border-b border-line p-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); if (valid) add(); }}>
          <Field label={tm.name} htmlFor="tm-name"><Input id="tm-name" dir="auto" value={form.full_name} maxLength={200}
            onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} /></Field>
          <Field label={t.login.email} htmlFor="tm-email"><Input id="tm-email" type="email" dir="ltr" value={form.email} maxLength={320}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} /></Field>
          <Field label={t.common.role} htmlFor="tm-role"><Select id="tm-role" className="w-full" value={form.role}
            onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
            {ROLES.map((r) => <option key={r} value={r}>{(t.roles as Record<string, string>)[r]}</option>)}</Select></Field>
          <Field label={tm.password} htmlFor="tm-password" hint={emailOn ? tm.inviteHint : tm.passwordHint}>
            <div className="flex gap-2"><Input id="tm-password" dir="ltr" value={form.password} maxLength={200}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
              <Button type="button" variant="secondary" aria-label={tm.generate} onClick={() => setForm((f) => ({ ...f, password: generatePassword() }))}>
                <KeyRound className="h-4 w-4" aria-hidden /></Button></div></Field>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" variant="primary" loading={busy} disabled={!valid}>{tm.addSubmit}</Button>
            <Button type="button" variant="ghost" onClick={() => setAdding(false)}>{t.common.cancel}</Button>
          </div>
        </form>
      )}
      <Table>
        <thead><tr><Th>{tm.name}</Th><Th>{t.login.email}</Th><Th>{t.common.role}</Th>{admin && <Th />}</tr></thead>
        <tbody>{data?.items.map((m) => (
          <tr key={m.id}>
            <Td className="font-medium" dir="auto">{m.full_name}</Td>
            <Td><span className="ltr font-mono text-sm">{m.email}</span></Td>
            <Td>{admin && m.id !== me?.user.id ? (
              <Select aria-label={`${t.common.role} · ${m.full_name}`} value={m.role} onChange={(e) => changeRole(m.id, e.target.value)}>
                {ROLES.map((r) => <option key={r} value={r}>{(t.roles as Record<string, string>)[r]}</option>)}
              </Select>) : (t.roles as Record<string, string>)[m.role]}</Td>
            {admin && <Td className="text-end">{m.id !== me?.user.id && (confirming === m.id
              ? <span className="inline-flex gap-1.5"><Button size="sm" variant="danger" onClick={() => remove(m.id)}>{tm.confirmRemove}</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>{t.common.cancel}</Button></span>
              : <Button size="sm" variant="ghost" aria-label={`${tm.remove} · ${m.full_name}`} onClick={() => setConfirming(m.id)}>
                <UserMinus className="h-4 w-4" aria-hidden />{tm.remove}</Button>)}</Td>}
          </tr>))}</tbody>
      </Table>
    </Panel>
  );
}

/** Change your own password. */
export function PasswordPanel() {
  const { t } = useI18n();
  const tm = t.team;
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.post("/api/auth/password", { current_password: current, new_password: next });
      toast.success(tm.passwordChanged);
      setCurrent(""); setNext("");
    } catch (e) {
      toast.error(e instanceof ApiError && e.status === 400 ? tm.wrongPassword : t.common.error);
    } finally { setBusy(false); }
  };
  return (
    <Panel>
      <PanelHeader title={tm.passwordTitle} sub={tm.passwordSub} />
      <form className="grid gap-3 p-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); if (current && next.length >= 12) save(); }}>
        <Field label={tm.currentPassword} htmlFor="pw-current"><Input id="pw-current" type="password" dir="ltr" autoComplete="current-password"
          value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
        <Field label={tm.newPassword} htmlFor="pw-new" hint={t.signup.passwordHint}><Input id="pw-new" type="password" dir="ltr"
          autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
        <div className="sm:col-span-2"><Button type="submit" variant="primary" loading={busy} disabled={!current || next.length < 12}>{tm.changePassword}</Button></div>
      </form>
    </Panel>
  );
}
