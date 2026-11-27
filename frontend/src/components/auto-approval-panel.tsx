"use client";

import { Lock, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button, cx, ErrorState, Field, Input, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { formFromPolicy, policyIssue, sameForm, toPayload, type PolicyForm, type PolicyView } from "@/lib/auto-approval";
import { useI18n } from "@/lib/i18n";

type SupplierRow = { id: string; name: string; name_en: string | null };
type Suppliers = { items: SupplierRow[]; total: number };
const SUPPLIER_LIMIT = 100;

/** The organization's auto-approval policy. It has its own Save button because it is its own API resource: the policy
 *  version and audit entry belong to this form alone, not to the matching and approval settings beside it. */
export function AutoApprovalPanel({ admin, currency }: { admin: boolean; currency: string }) {
  const { t, locale } = useI18n();
  const a = t.autoApproval;
  const { data, error, mutate } = useApi<PolicyView>("/api/org/auto-approval");
  const { data: suppliers } = useApi<Suppliers>(`/api/suppliers?page_size=${SUPPLIER_LIMIT}`);
  const saved = useMemo(() => (data ? formFromPolicy(data.policy) : null), [data]);
  const [form, setForm] = useState<PolicyForm | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (saved) setForm(saved); }, [saved]);
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!data || !form || !saved) return <Skeleton className="h-72 w-full" />;

  const issue = policyIssue(form);
  const dirty = !sameForm(form, saved);
  const set = (patch: Partial<PolicyForm>) => setForm({ ...form, ...patch });
  const toggle = (id: string) => set({ supplierIds: form.supplierIds.includes(id) ? form.supplierIds.filter((x) => x !== id) : [...form.supplierIds, id] });
  const save = async () => {
    setBusy(true);
    try {
      await api.put("/api/org/auto-approval", toPayload(form));
      toast.success(a.saved);
      await mutate();
    } catch (e) { toast.error(e instanceof ApiError ? String(e.message) : t.common.error); } finally { setBusy(false); }
  };
  const supplierName = (s: SupplierRow) => (locale === "en" && s.name_en) || s.name;

  return <Panel>
    <PanelHeader title={a.title} sub={a.help}
      actions={<span className="text-xs text-ink-3">{data.policy.version > 0 ? a.version.replace("{n}", String(data.policy.version)) : a.never}</span>} />
    <div className="space-y-5 px-5 py-5">
      <label className={cx("flex items-start gap-3 rounded-xl border border-line px-4 py-3 text-sm", admin && "cursor-pointer hover:bg-sunken")}>
        <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]" checked={form.enabled} disabled={!admin}
          onChange={(e) => set({ enabled: e.target.checked })} />
        <span className="text-ink"><span className="block font-semibold">{a.enable}</span><span className="block text-ink-3">{a.enableHint}</span></span>
      </label>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label={a.maxAmount} hint={issue === "amount" ? undefined : a.maxHint} htmlFor="auto-max">
          <div className="relative">
            <Input id="auto-max" dir="ltr" inputMode="decimal" className="tabular-nums !pr-16" value={form.maxAmount} disabled={!admin}
              aria-invalid={issue === "amount"} aria-describedby={issue === "amount" ? "auto-max-error" : undefined}
              onChange={(e) => set({ maxAmount: e.target.value })} />
            <span aria-hidden dir="ltr" className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm text-ink-3">{currency}</span>
          </div>
          {issue === "amount" && <p id="auto-max-error" role="alert" className="text-xs font-medium text-danger">{a.invalidAmount}</p>}
        </Field>

        <fieldset className="space-y-2">
          <legend className="block text-sm font-medium text-ink-2">{a.scope}</legend>
          {(["all", "selected"] as const).map((v) => <label key={v} className={cx("flex items-center gap-2.5 rounded-xl border border-line px-3.5 py-2.5 text-sm", admin && "cursor-pointer hover:bg-sunken")}>
            <input type="radio" name="auto-scope" className="h-4 w-4 accent-[rgb(var(--accent))]" checked={form.scope === v} disabled={!admin} onChange={() => set({ scope: v })} />
            <span className="text-ink">{v === "all" ? a.scopeAll : a.scopeSelected}</span>
          </label>)}
        </fieldset>
      </div>

      {form.scope === "selected" && <fieldset>
        <legend className="mb-2 flex w-full items-baseline justify-between text-sm font-medium text-ink-2">
          <span>{a.pick}</span><span className="text-xs text-ink-3">{a.chosen.replace("{n}", String(form.supplierIds.length))}</span>
        </legend>
        {!suppliers ? <Skeleton className="h-24 w-full" /> : <ul className="grid max-h-64 gap-1.5 overflow-y-auto sm:grid-cols-2">
          {suppliers.items.map((s) => <li key={s.id}>
            <label className={cx("flex items-center gap-2.5 rounded-xl border border-line px-3.5 py-2 text-sm", admin && "cursor-pointer hover:bg-sunken")}>
              <input type="checkbox" className="h-4 w-4 shrink-0 accent-[rgb(var(--accent))]" checked={form.supplierIds.includes(s.id)} disabled={!admin} onChange={() => toggle(s.id)} />
              <bdi className="min-w-0 truncate text-ink">{supplierName(s)}</bdi>
            </label>
          </li>)}
        </ul>}
        {suppliers && suppliers.total > suppliers.items.length && <p className="mt-2 text-xs text-ink-3">{a.firstOnly.replace("{n}", String(suppliers.items.length))}</p>}
        {issue === "noSuppliers" && <p role="alert" className="mt-2 text-xs font-medium text-danger">{a.noneChosen}</p>}
      </fieldset>}

      <div className="rounded-xl bg-sunken px-4 py-3">
        <p className="flex items-center gap-2 text-sm font-bold text-ink"><Lock className="h-4 w-4 text-ink-3" aria-hidden />{a.rulesTitle}</p>
        <ul className="mt-2 space-y-1 text-sm text-ink-2">
          {data.fixed_rules.map((r) => <li key={r} className="flex items-start gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden />
            <span>{(a.rules as Record<string, string>)[r] ?? r}</span></li>)}
        </ul>
        <p className="mt-2 text-xs text-ink-3">{a.approvalUnchanged}</p>
      </div>

      {admin && <div className="flex justify-end">
        <Button variant="primary" loading={busy} disabled={!dirty || issue !== null} onClick={save}>{a.save}</Button>
      </div>}
    </div>
  </Panel>;
}
