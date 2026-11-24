"use client";

import { Check, Minus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useSession } from "@/components/session";
import { SessionsPanel } from "@/components/sessions-panel";
import { PasswordPanel, TeamPanel } from "@/components/team-panel";
import { TwoFactorPanel } from "@/components/two-factor-panel";
import { PageHeader } from "@/components/shell";
import { Button, ErrorState, Field, Input, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, downloadFile, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

type Org = { id: string; name: string; slug: string; settings: { tolerances: Record<string, string | number>;
  approval: { dual_approval_threshold?: string; procurement_cannot_decide_own_upload?: boolean; bank_change_hold_days?: number };
  auto_investigate?: boolean;
  priority?: { critical_amount?: string }; security?: { session_idle_hours?: number; session_max_days?: number; require_2fa?: boolean } };
  ai_mode: string; roles: Record<string, string[]> };

export default function SettingsPage() {
  const { t } = useI18n();
  const { can, me } = useSession();
  const admin = can("org:manage");
  const { data: org, error, mutate } = useApi<Org>("/api/org");
  const [tol, setTol] = useState<Record<string, string>>({});
  const [appr, setAppr] = useState<Org["settings"]["approval"]>({});
  const [auto, setAuto] = useState(true);
  const [critical, setCritical] = useState("5000");
  const [idleHours, setIdleHours] = useState("8");
  const [maxDays, setMaxDays] = useState("7");
  const [require2fa, setRequire2fa] = useState(false);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [eraseSlug, setEraseSlug] = useState("");
  const [erasePassword, setErasePassword] = useState("");
  const [erasing, setErasing] = useState(false);
  useEffect(() => {
    if (!org) return;
    setTol(Object.fromEntries(Object.entries(org.settings.tolerances).map(([k, v]) => [k, String(v)])));
    setAppr({ ...org.settings.approval });
    setAuto(org.settings.auto_investigate ?? true);
    setCritical(String(org.settings.priority?.critical_amount ?? "5000"));
    setIdleHours(String(org.settings.security?.session_idle_hours ?? 8));
    setMaxDays(String(org.settings.security?.session_max_days ?? 7));
    setRequire2fa(org.settings.security?.require_2fa ?? false);
  }, [org]);
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!org) return <Skeleton className="h-96 w-full" />;

  const save = async () => {
    setBusy(true);
    try { await api.patch("/api/org/settings", { tolerances: tol, approval: appr, auto_investigate: auto,
      priority: { critical_amount: critical },
      security: { session_idle_hours: Number(idleHours), session_max_days: Number(maxDays),
        ...(require2fa !== (org.settings.security?.require_2fa ?? false) && { require_2fa: require2fa }) } });
      toast.success(t.common.save); mutate(); }
    catch (e) { toast.error(e instanceof ApiError ? String(e.message) : t.common.error); } finally { setBusy(false); }
  };
  const allPerms = Array.from(new Set(Object.values(org.roles).flat())).sort();

  return (
    <div className="space-y-5">
      <PageHeader title={t.settings.title} sub={<><bdi>{org.name}</bdi>{!admin && <> · {t.settings.adminOnly}</>}</>} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel>
          <PanelHeader title={t.settings.tolerances} sub={t.ai.deterministic} />
          <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
            {Object.keys(tol).map((k) => (
              <Field key={k} label={label(t.settings, k)} htmlFor={k}>
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
            <Field label={t.banking.holdDays} hint="0–30" htmlFor="bank-hold-days">
              <Input id="bank-hold-days" dir="ltr" type="number" min={0} max={30} disabled={!admin}
                value={appr.bank_change_hold_days ?? 3} onChange={(event) => {
                  if (event.target.value !== "") setAppr({ ...appr, bank_change_hold_days: Number(event.target.value) });
                }} />
            </Field>
            <label className="flex items-start gap-2.5 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--accent))]" checked={auto} disabled={!admin} onChange={(e) => setAuto(e.target.checked)} />
              <span>{t.settings.autoInvestigate}</span>
            </label>
            <label className="flex items-start gap-2.5 text-sm">
              <input type="checkbox" checked={appr.procurement_cannot_decide_own_upload ?? false} disabled={!admin}
                onChange={(event) => setAppr({ ...appr, procurement_cannot_decide_own_upload: event.target.checked })} />
              <span>{t.settings.separateProcurementReview}</span>
            </label>
            <p className="text-xs text-ink-3">AI: <span className="font-mono">{org.ai_mode}</span></p>
          </div>
          <div className="grid grid-cols-1 gap-4 border-t border-line p-4 sm:grid-cols-3">
            <Field label={`${t.settings.criticalAmount} (${me?.organization.base_currency ?? "ILS"})`} hint={t.settings.criticalHint} htmlFor="critical">
              <Input id="critical" dir="ltr" inputMode="decimal" value={critical} disabled={!admin} onChange={(e) => setCritical(e.target.value)} />
            </Field>
            <Field label={t.settings.sessionIdleHours} hint="1–72" htmlFor="idle">
              <Input id="idle" dir="ltr" type="number" min={1} max={72} value={idleHours} disabled={!admin} onChange={(e) => setIdleHours(e.target.value)} />
            </Field>
            <Field label={t.settings.sessionMaxDays} hint="1–30" htmlFor="maxdays">
              <Input id="maxdays" dir="ltr" type="number" min={1} max={30} value={maxDays} disabled={!admin} onChange={(e) => setMaxDays(e.target.value)} />
            </Field>
          </div>
          {admin && <div className="space-y-4 border-t border-line p-4">
            <label className="flex items-start gap-2.5 text-sm">
              <input type="checkbox" checked={require2fa} disabled={!me?.two_factor && !require2fa}
                onChange={(event) => setRequire2fa(event.target.checked)} />
              <span>{t.twoFactor.enforceForTeam}{!me?.two_factor && <span className="block text-ink-3">{t.twoFactor.enforceHint}</span>}</span>
            </label>
            <Button variant="primary" loading={busy} onClick={save}>{t.common.save}</Button>
          </div>}
        </Panel>
      </div>
      <SessionsPanel />
      <TeamPanel />
      <PasswordPanel />
      <TwoFactorPanel />
      {admin && <Panel>
        <PanelHeader title={t.settings.workspaceData} sub={t.settings.workspaceArchiveHint} />
        <div className="p-4"><Button loading={exporting} onClick={async () => {
          setExporting(true);
          try { await downloadFile("/api/org/archive.zip", "invoiceflow-workspace.zip"); }
          catch (e) { toast.error(e instanceof ApiError ? e.message : t.common.error); }
          finally { setExporting(false); }
        }}>{t.settings.workspaceArchive}</Button></div>
        <details className="border-t border-line p-4" onToggle={(event) => {
          if (!event.currentTarget.open) { setEraseSlug(""); setErasePassword(""); }
        }}>
          <summary className="cursor-pointer text-sm font-medium text-bad">{t.settings.eraseWorkspace}</summary>
          <form className="mt-4 max-w-md space-y-4" onSubmit={async (event) => {
            event.preventDefault();
            if (erasing || eraseSlug !== org.slug || !erasePassword) return;
            setErasing(true);
            try {
              await api.post("/api/org/erase", { slug: eraseSlug, password: erasePassword });
              window.location.assign("/login");
            } catch {
              toast.error(t.settings.eraseFailed);
              setErasePassword("");
              setErasing(false);
            }
          }}>
            <p className="text-sm text-ink-3">{t.settings.eraseWarning}</p>
            <Field label={t.settings.eraseIdentifier} hint={org.slug} htmlFor="erase-workspace-slug">
              <Input id="erase-workspace-slug" dir="ltr" autoComplete="off" maxLength={80} value={eraseSlug}
                onChange={(event) => setEraseSlug(event.target.value)} required />
            </Field>
            <Field label={t.settings.erasePassword} htmlFor="erase-workspace-password">
              <Input id="erase-workspace-password" type="password" autoComplete="current-password" maxLength={200}
                value={erasePassword} onChange={(event) => setErasePassword(event.target.value)} required />
            </Field>
            <Button type="submit" variant="danger" disabled={eraseSlug !== org.slug || !erasePassword}
              loading={erasing}>{t.settings.eraseWorkspace}</Button>
          </form>
        </details>
      </Panel>}
      <Panel>
        <PanelHeader title={t.settings.permissions} />
        <Table>
          <thead><tr><Th>Permission</Th>{Object.keys(org.roles).map((r) => <Th key={r} className="text-center">{label(t.roles, r)}</Th>)}</tr></thead>
          <tbody>{allPerms.map((p) => (
            <tr key={p}>
              <Td className="font-mono text-xs">{p}</Td>
              {Object.entries(org.roles).map(([r, perms]) => (
                <Td key={r} className="text-center">{perms.includes(p) ? <Check className="mx-auto h-4 w-4 text-ok" aria-label={t.common.yes} /> : <Minus className="mx-auto h-4 w-4 text-line-strong" aria-label={t.common.no} />}</Td>
              ))}
            </tr>))}</tbody>
        </Table>
      </Panel>
    </div>
  );
}
