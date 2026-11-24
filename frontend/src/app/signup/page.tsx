"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Input, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { LEGAL_VERSION } from "@/lib/legal";
import { useI18n } from "@/lib/i18n";

/** Create a business: an isolated workspace and its first administrator. */
export default function SignupPage() {
  const { t, locale } = useI18n();
  const s = t.signup;
  const router = useRouter();
  const [form, setForm] = useState({ company_name: "", tax_id: "", full_name: "", email: "", password: "" });
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const taxOk = !form.tax_id || /^\d{9}$/.test(form.tax_id);
  const ready = form.company_name.trim().length >= 2 && form.full_name.trim().length >= 2 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)
    && form.password.length >= 12 && taxOk && accepted;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/signup", { ...form, tax_id: form.tax_id || null, locale, accepted_legal_version: LEGAL_VERSION });
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? s.exists
        : err instanceof ApiError && err.status === 429 ? t.login.rateLimited
        : err instanceof ApiError && err.status === 403 ? s.disabled
        : err instanceof ApiError && err.status === 400 ? s.consentRequired : s.failed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title={s.title}>
      <Panel className="p-5 sm:p-7">
        <p className="mb-5 text-sm text-ink-2">{s.sub}</p>
        <form onSubmit={submit} className="space-y-5" noValidate>
          <Field label={s.company} htmlFor="company"><Input id="company" dir="auto" autoComplete="organization" required
            value={form.company_name} onChange={set("company_name")} maxLength={200} /></Field>
          <Field label={s.taxId} htmlFor="tax" hint={taxOk ? s.taxIdHint : s.taxIdInvalid}><Input id="tax" dir="ltr" inputMode="numeric"
            value={form.tax_id} onChange={set("tax_id")} maxLength={9} aria-invalid={!taxOk} /></Field>
          <Field label={s.fullName} htmlFor="name"><Input id="name" dir="auto" autoComplete="name" required
            value={form.full_name} onChange={set("full_name")} maxLength={200} /></Field>
          <Field label={t.login.email} htmlFor="email"><Input id="email" type="email" dir="ltr" autoComplete="email" required
            value={form.email} onChange={set("email")} maxLength={320} /></Field>
          <Field label={t.login.password} htmlFor="password" hint={s.passwordHint}><Input id="password" type="password" dir="ltr"
            autoComplete="new-password" required value={form.password} onChange={set("password")} maxLength={200} /></Field>
          <label className="flex items-start gap-2.5 text-sm leading-relaxed text-ink-2">
            <input type="checkbox" required checked={accepted} onChange={(e) => setAccepted(e.target.checked)}
              className="mt-1 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]" aria-labelledby="consent-note" />
            <span id="consent-note">{s.consentBefore}<Link href="/legal/terms" target="_blank" className="font-semibold text-accent-ink underline underline-offset-4">{t.legal.terms}</Link>,{" "}
              {locale === "he" ? "ל" : "the "}<Link href="/legal/privacy" target="_blank" className="font-semibold text-accent-ink underline underline-offset-4">{t.legal.privacy}</Link>{" "}
              {s.consentAnd}<Link href="/legal/dpa" target="_blank" className="font-semibold text-accent-ink underline underline-offset-4">{t.legal.dpa}</Link>.</span>
          </label>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy} disabled={!ready}>{s.submit}</Button>
        </form>
      </Panel>
      <p className="text-center text-sm text-ink-2">{s.haveAccount} <Link href="/login" className="font-semibold text-ink underline-offset-4 hover:underline">{s.signIn}</Link></p>
    </AuthShell>
  );
}
