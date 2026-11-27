"use client";

import { Check, Database, Lock, Mail, Minus, Plug, Scale, ShieldCheck, Users, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { AutoApprovalPanel } from "@/components/auto-approval-panel";
import { EmailInboxPanel } from "@/components/email-inbox";
import { ApiKeysPanel, WebhooksPanel } from "@/components/integrations-panel";
import { useSession } from "@/components/session";
import { SessionsPanel } from "@/components/sessions-panel";
import { PasswordPanel, TeamPanel } from "@/components/team-panel";
import { TwoFactorPanel } from "@/components/two-factor-panel";
import { PageHeader } from "@/components/page-kit";
import { Button, cx, ErrorState, Field, Input, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api, ApiError, downloadFile, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

type Org = { id: string; name: string; slug: string; settings: { tolerances: Record<string, string | number>;
  approval: { dual_approval_threshold?: string; procurement_cannot_decide_own_upload?: boolean; bank_change_hold_days?: number };
  auto_investigate?: boolean;
  priority?: { critical_amount?: string }; security?: { session_idle_hours?: number; session_max_days?: number; require_2fa?: boolean } };
  ai_mode: string; roles: Record<string, string[]> };
type Form = { tol: Record<string, string>; appr: Org["settings"]["approval"]; auto: boolean; critical: string; idleHours: string; maxDays: string; require2fa: boolean };
type Section = "matching" | "approval" | "autoApproval" | "security" | "team" | "inbox" | "integrations" | "data";

// how the matching tolerances are grouped on screen, and the unit each one is measured in
const TOLERANCE_GROUPS: { title: "groupPrice" | "groupQuantity" | "groupTotals" | "groupText" | "groupDuplicates"; keys: [string, "unitPerUnit" | "unitPct" | "unitUnits" | "unitDays" | "unitScore" | null][] }[] = [
  { title: "groupPrice", keys: [["price_abs", "unitPerUnit"], ["price_pct", "unitPct"]] },
  { title: "groupQuantity", keys: [["quantity_abs", "unitUnits"]] },
  { title: "groupTotals", keys: [["total_abs", null], ["line_total_abs", null]] },
  { title: "groupText", keys: [["description_match_min", "unitScore"], ["description_ambiguity_margin", "unitScore"]] },
  { title: "groupDuplicates", keys: [["duplicate_window_days", "unitDays"]] },
];

function formFrom(org: Org): Form {
  return {
    tol: Object.fromEntries(Object.entries(org.settings.tolerances).map(([k, v]) => [k, String(v)])),
    appr: { ...org.settings.approval }, auto: org.settings.auto_investigate ?? true,
    critical: String(org.settings.priority?.critical_amount ?? "5000"),
    idleHours: String(org.settings.security?.session_idle_hours ?? 8), maxDays: String(org.settings.security?.session_max_days ?? 7),
    require2fa: org.settings.security?.require_2fa ?? false,
  };
}

/** A number field with its unit inside the field, so "1.0" is never read without "%". */
function UnitInput({ id, unit, ...p }: React.InputHTMLAttributes<HTMLInputElement> & { id: string; unit?: string | null }) {
  return <div className="relative">
    {/* the field is always left-to-right, so the unit sits on its physical right in both languages */}
    <Input id={id} dir="ltr" className={cx("tabular-nums", unit && "!pr-16")} {...p} />
    {unit && <span aria-hidden dir="ltr" className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm text-ink-3">{unit}</span>}
  </div>;
}

function Check2({ checked, disabled, onChange, children }: { checked: boolean; disabled?: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return <label className={cx("flex items-start gap-3 rounded-xl border border-line px-4 py-3 text-sm", !disabled && "cursor-pointer hover:bg-sunken")}>
    <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
    <span className="text-ink">{children}</span>
  </label>;
}

export default function SettingsPage() {
  const { t } = useI18n();
  const { can, me } = useSession();
  const admin = can("org:manage");
  const { data: org, error, mutate } = useApi<Org>("/api/org");
  const initial = useMemo(() => (org ? formFrom(org) : null), [org]);
  const [form, setForm] = useState<Form | null>(null);
  const [section, setSection] = useState<Section>("matching");
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [eraseSlug, setEraseSlug] = useState("");
  const [erasePassword, setErasePassword] = useState("");
  const [erasing, setErasing] = useState(false);
  useEffect(() => { if (initial) setForm(initial); }, [initial]);
  const dirty = !!form && !!initial && JSON.stringify(form) !== JSON.stringify(initial);
  // a direct link (#security) opens its section; leaving with unsaved policy changes asks first
  useEffect(() => {
    const fromHash = () => { const m = window.location.hash.match(/^#(matching|approval|autoApproval|security|team|inbox|integrations|data)$/); if (m) setSection(m[1] as Section); };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = t.settings.leaveWarning; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, t.settings.leaveWarning]);
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!org || !form) return <Skeleton className="h-96 w-full" />;

  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });
  const go = (s: Section) => { setSection(s); window.history.replaceState(null, "", `#${s}`); };
  const save = async () => {
    setBusy(true);
    try {
      await api.patch("/api/org/settings", { tolerances: form.tol, approval: form.appr, auto_investigate: form.auto,
        priority: { critical_amount: form.critical },
        security: { session_idle_hours: Number(form.idleHours), session_max_days: Number(form.maxDays),
          ...(form.require2fa !== (org.settings.security?.require_2fa ?? false) && { require_2fa: form.require2fa }) } });
      toast.success(t.settings.saved); await mutate();
    } catch (e) { toast.error(e instanceof ApiError ? String(e.message) : t.common.error); } finally { setBusy(false); }
  };
  const currency = me?.organization.base_currency ?? "ILS";
  const allPerms = Array.from(new Set(Object.values(org.roles).flat())).sort();
  const mapped = new Set(TOLERANCE_GROUPS.flatMap((g) => g.keys.map(([k]) => k)));
  const otherKeys = Object.keys(form.tol).filter((k) => !mapped.has(k));
  const sections: { key: Section; label: string; icon: React.ElementType }[] = [
    { key: "matching", label: t.settings.navMatching, icon: Scale },
    { key: "approval", label: t.settings.approval, icon: ShieldCheck },
    { key: "autoApproval", label: t.autoApproval.nav, icon: Zap },
    { key: "security", label: t.settings.navSecurity, icon: Lock },
    { key: "team", label: t.settings.navTeam, icon: Users },
    ...(admin ? [{ key: "inbox" as Section, label: t.emailInbox.nav, icon: Mail },
      { key: "integrations" as Section, label: t.settings.navIntegrations, icon: Plug },
      { key: "data" as Section, label: t.settings.workspaceData, icon: Database }] : []),
  ];
  const tolField = (k: string, unit: string | null) => <Field key={k} label={label(t.settings, k)} hint={label(t.tolHelp, k, "")} htmlFor={`tol-${k}`}>
    <UnitInput id={`tol-${k}`} unit={unit} inputMode="decimal" value={form.tol[k] ?? ""} disabled={!admin} onChange={(e) => set({ tol: { ...form.tol, [k]: e.target.value } })} />
  </Field>;

  return (
    <div className="min-w-0 space-y-5 pb-20">
      <PageHeader title={t.settings.title} sub={<><bdi>{org.name}</bdi> · {t.settings.subtitle}</>} />
      {!admin && <p className="flex items-center gap-2.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2"><Lock className="h-4 w-4 shrink-0 text-ink-3" aria-hidden />{t.settings.adminOnly}</p>}

      <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[14rem_minmax(0,1fr)]">
        {/* the categories: a list beside the content on wide screens, a scrolling row on phones */}
        <nav aria-label={t.settings.title} className="min-w-0 lg:sticky lg:top-20">
          <ul className="flex gap-1.5 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0">
            {sections.map(({ key, label: text, icon: Icon }) => <li key={key} className="shrink-0">
              <button type="button" aria-current={section === key ? "page" : undefined} onClick={() => go(key)}
                className={cx("flex w-full items-center gap-2.5 whitespace-nowrap rounded-xl px-3.5 py-2.5 text-start text-sm font-semibold transition-colors",
                  section === key ? "bg-rail-active text-accent-ink" : "text-ink-2 hover:bg-sunken hover:text-ink")}>
                <Icon className="h-4 w-4 shrink-0" aria-hidden />{text}
              </button></li>)}
          </ul>
        </nav>

        <div className="min-w-0 space-y-5">
          {section === "matching" && <Panel>
            <PanelHeader title={t.settings.navMatching} sub={t.settings.matchingHelp} />
            <div className="divide-y divide-line">
              {TOLERANCE_GROUPS.map((g) => <fieldset key={g.title} className="grid gap-4 px-5 py-5 md:grid-cols-[10rem_minmax(0,1fr)]">
                <legend className="sr-only">{t.settings[g.title]}</legend>
                <p aria-hidden className="text-sm font-bold text-ink">{t.settings[g.title]}</p>
                <div className="grid gap-4 sm:grid-cols-2">{g.keys.filter(([k]) => k in form.tol).map(([k, unit]) => tolField(k, unit ? t.settings[unit] : null))}</div>
              </fieldset>)}
              {otherKeys.length > 0 && <div className="grid gap-4 px-5 py-5 sm:grid-cols-2">{otherKeys.map((k) => tolField(k, null))}</div>}
            </div>
          </Panel>}

          {section === "approval" && <Panel>
            <PanelHeader title={t.settings.approval} sub={t.settings.approvalHelp} />
            <div className="grid gap-4 px-5 py-5 sm:grid-cols-2">
              <Field label={t.settings.dual_approval_threshold} htmlFor="dual">
                <UnitInput id="dual" unit={currency} inputMode="decimal" value={form.appr.dual_approval_threshold ?? ""} disabled={!admin}
                  onChange={(e) => set({ appr: { ...form.appr, dual_approval_threshold: e.target.value } })} />
              </Field>
              <Field label={t.settings.criticalAmount} hint={t.settings.criticalHint} htmlFor="critical">
                <UnitInput id="critical" unit={currency} inputMode="decimal" value={form.critical} disabled={!admin} onChange={(e) => set({ critical: e.target.value })} />
              </Field>
              <Field label={t.banking.holdDays} hint="0–30" htmlFor="bank-hold-days">
                <UnitInput id="bank-hold-days" unit={t.settings.unitDays} type="number" min={0} max={30} disabled={!admin} value={form.appr.bank_change_hold_days ?? 3}
                  onChange={(e) => { if (e.target.value !== "") set({ appr: { ...form.appr, bank_change_hold_days: Number(e.target.value) } }); }} />
              </Field>
            </div>
            <div className="space-y-2.5 border-t border-line px-5 py-5">
              <Check2 checked={form.auto} disabled={!admin} onChange={(v) => set({ auto: v })}>{t.settings.autoInvestigate}</Check2>
              <Check2 checked={form.appr.procurement_cannot_decide_own_upload ?? false} disabled={!admin}
                onChange={(v) => set({ appr: { ...form.appr, procurement_cannot_decide_own_upload: v } })}>{t.settings.separateProcurementReview}</Check2>
              <p className="pt-1 text-xs text-ink-3">AI: <bdi className="font-mono" dir="ltr">{org.ai_mode}</bdi></p>
            </div>
          </Panel>}

          {section === "autoApproval" && <AutoApprovalPanel admin={admin} currency={currency} />}

          {section === "security" && <>
            <Panel>
              <PanelHeader title={t.settings.navSecurity} sub={t.settings.securityHelp} />
              <div className="grid gap-4 px-5 py-5 sm:grid-cols-2">
                <Field label={t.settings.sessionIdleHours} hint="1–72" htmlFor="idle">
                  <UnitInput id="idle" type="number" min={1} max={72} value={form.idleHours} disabled={!admin} onChange={(e) => set({ idleHours: e.target.value })} />
                </Field>
                <Field label={t.settings.sessionMaxDays} hint="1–30" htmlFor="maxdays">
                  <UnitInput id="maxdays" type="number" min={1} max={30} value={form.maxDays} disabled={!admin} onChange={(e) => set({ maxDays: e.target.value })} />
                </Field>
              </div>
              {admin && <div className="border-t border-line px-5 py-5">
                <Check2 checked={form.require2fa} disabled={!me?.two_factor && !form.require2fa} onChange={(v) => set({ require2fa: v })}>
                  {t.twoFactor.enforceForTeam}{!me?.two_factor && <span className="mt-0.5 block text-ink-3">{t.twoFactor.enforceHint}</span>}
                </Check2>
              </div>}
            </Panel>
            <SessionsPanel />
            <PasswordPanel />
            <TwoFactorPanel />
          </>}

          {section === "team" && <>
            <TeamPanel />
            <Panel>
              <PanelHeader title={t.settings.permissions} />
              <Table>
                <thead><tr><Th>{t.settings.permission}</Th>{Object.keys(org.roles).map((r) => <Th key={r} className="text-center">{label(t.roles, r)}</Th>)}</tr></thead>
                <tbody>{allPerms.map((p) => (
                  <tr key={p}>
                    <Td><span className="block text-sm text-ink">{label(t.perms, p)}</span><bdi className="font-mono text-xs text-ink-3" dir="ltr">{p}</bdi></Td>
                    {Object.entries(org.roles).map(([r, perms]) => (
                      <Td key={r} className="text-center">{perms.includes(p) ? <Check className="mx-auto h-4 w-4 text-ok" aria-label={t.common.yes} /> : <Minus className="mx-auto h-4 w-4 text-line-strong" aria-label={t.common.no} />}</Td>
                    ))}
                  </tr>))}</tbody>
              </Table>
            </Panel>
          </>}

          {section === "inbox" && admin && <EmailInboxPanel />}
          {section === "integrations" && admin && <>
            <ApiKeysPanel />
            <WebhooksPanel />
          </>}

          {section === "data" && admin && <Panel>
            <PanelHeader title={t.settings.workspaceData} sub={t.settings.workspaceArchiveHint} />
            <div className="px-5 py-5"><Button loading={exporting} onClick={async () => {
              setExporting(true);
              try { await downloadFile("/api/org/archive.zip", "invoiceflow-workspace.zip"); }
              catch (e) { toast.error(e instanceof ApiError ? e.message : t.common.error); }
              finally { setExporting(false); }
            }}>{t.settings.workspaceArchive}</Button></div>
            <details className="border-t border-line px-5 py-5" onToggle={(event) => {
              if (!event.currentTarget.open) { setEraseSlug(""); setErasePassword(""); }
            }}>
              <summary className="cursor-pointer text-sm font-semibold text-danger">{t.settings.eraseWorkspace}</summary>
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
        </div>
      </div>

      {/* the policy is saved as one change; the bar appears only when something differs from what is saved */}
      {admin && dirty && <div role="region" aria-label={t.settings.unsaved}
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 px-4 py-3 shadow-pop backdrop-blur lg:start-[256px]">
        <div className="mx-auto flex max-w-[1456px] flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-semibold text-ink">{t.settings.unsaved}</p>
          <div className="flex gap-2">
            <Button onClick={() => initial && setForm(initial)} disabled={busy}>{t.settings.discard}</Button>
            <Button variant="primary" loading={busy} onClick={save}>{t.settings.saveChanges}</Button>
          </div>
        </div>
      </div>}
    </div>
  );
}
