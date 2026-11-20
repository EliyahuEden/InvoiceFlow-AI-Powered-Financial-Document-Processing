"use client";

import { Check, Minus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useSession } from "@/components/session";
import { PageHeader } from "@/components/shell";
import { Button, Field, Input, Panel, PanelHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type Org = { id: string; name: string; settings: { tolerances: Record<string, string | number>; approval: Record<string, string>; auto_investigate?: boolean };
  ai_mode: string; roles: Record<string, string[]> };
type Member = { id: string; email: string; full_name: string; role: string; is_active: boolean };

export default function SettingsPage() {
  const { t } = useI18n();
  const { can, me } = useSession();
  const admin = can("org:manage");
  const { data: org, mutate } = useApi<Org>("/api/org");
  const { data: members, mutate: mutateMembers } = useApi<{ items: Member[] }>("/api/org/members");
  const [tol, setTol] = useState<Record<string, string>>({});
  const [appr, setAppr] = useState<Record<string, string>>({});
  const [auto, setAuto] = useState(true);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!org) return;
    setTol(Object.fromEntries(Object.entries(org.settings.tolerances).map(([k, v]) => [k, String(v)])));
    setAppr({ ...org.settings.approval });
    setAuto(org.settings.auto_investigate ?? true);
  }, [org]);
  if (!org) return <Skeleton className="h-96 w-full" />;

  const save = async () => {
    setBusy(true);
    try { await api.patch("/api/org/settings", { tolerances: tol, approval: appr, auto_investigate: auto }); toast.success(t.common.save); mutate(); }
    catch (e) { toast.error(e instanceof ApiError ? String(e.message) : t.common.error); } finally { setBusy(false); }
  };
  const changeRole = async (id: string, role: string) => {
    try { await api.patch(`/api/org/members/${id}`, { role }); mutateMembers(); toast.success(t.common.save); }
    catch (e) { toast.error(String((e as Error).message)); }
  };
  const allPerms = Array.from(new Set(Object.values(org.roles).flat())).sort();

  return (
    <div className="space-y-5">
      <PageHeader title={t.settings.title} sub={!admin ? t.settings.adminOnly : undefined} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel>
          <PanelHeader title={t.settings.tolerances} sub={t.ai.deterministic} />
          <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
            {Object.keys(tol).map((k) => (
              <Field key={k} label={(t.settings as Record<string, string>)[k] ?? k} htmlFor={k}>
                <Input id={k} dir="ltr" inputMode="decimal" value={tol[k]} disabled={!admin} onChange={(e) => setTol({ ...tol, [k]: e.target.value })} />
              </Field>
            ))}
          </div>
        </Panel>
        <Panel>
          <PanelHeader title={t.settings.approval} />
          <div className="space-y-4 p-4">
            <Field label={`${t.settings.dual_approval_threshold} (₪)`} htmlFor="dual">
              <Input id="dual" dir="ltr" inputMode="decimal" value={appr.dual_approval_threshold ?? ""} disabled={!admin}
                onChange={(e) => setAppr({ ...appr, dual_approval_threshold: e.target.value })} />
            </Field>
            <label className="flex items-start gap-2.5 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--accent))]" checked={auto} disabled={!admin} onChange={(e) => setAuto(e.target.checked)} />
              <span>{t.settings.autoInvestigate}</span>
            </label>
            <p className="text-xs text-ink-3">AI: <span className="font-mono">{org.ai_mode}</span></p>
          </div>
          {admin && <div className="border-t border-line p-4"><Button variant="primary" loading={busy} onClick={save}>{t.common.save}</Button></div>}
        </Panel>
      </div>
      <Panel>
        <PanelHeader title={t.settings.members} />
        <Table>
          <thead><tr><Th>Name</Th><Th>Email</Th><Th>{t.common.role}</Th></tr></thead>
          <tbody>{members?.items.map((m) => (
            <tr key={m.id}>
              <Td className="font-medium">{m.full_name}</Td>
              <Td><span className="ltr font-mono text-sm">{m.email}</span></Td>
              <Td>{admin && m.id !== me?.user.id ? (
                <Select value={m.role} onChange={(e) => changeRole(m.id, e.target.value)}>
                  {Object.keys(org.roles).map((r) => <option key={r} value={r}>{(t.roles as Record<string, string>)[r]}</option>)}
                </Select>) : (t.roles as Record<string, string>)[m.role]}</Td>
            </tr>))}</tbody>
        </Table>
      </Panel>
      <Panel>
        <PanelHeader title={t.settings.permissions} />
        <Table>
          <thead><tr><Th>Permission</Th>{Object.keys(org.roles).map((r) => <Th key={r} className="text-center">{(t.roles as Record<string, string>)[r]}</Th>)}</tr></thead>
          <tbody>{allPerms.map((p) => (
            <tr key={p}>
              <Td className="font-mono text-xs">{p}</Td>
              {Object.entries(org.roles).map(([r, perms]) => (
                <Td key={r} className="text-center">{perms.includes(p) ? <Check className="mx-auto h-4 w-4 text-ok" aria-label="yes" /> : <Minus className="mx-auto h-4 w-4 text-line-strong" aria-label="no" />}</Td>
              ))}
            </tr>))}</tbody>
        </Table>
      </Panel>
    </div>
  );
}
