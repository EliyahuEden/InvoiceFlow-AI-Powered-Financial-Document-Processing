"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Input, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";

const DEMO = [
  { email: "finance@kinneret.example", role: "finance_reviewer" },
  { email: "procurement@kinneret.example", role: "procurement_manager" },
  { email: "admin@kinneret.example", role: "admin" },
  { email: "viewer@kinneret.example", role: "read_only" },
];

function LoginForm() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // second step, when the account has two-factor sign-in
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const tf = t.twoFactor;

  const done = () => {
    const next = params.get("next");
    router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ mfa_required?: boolean; mfa_token?: string }>("/api/auth/login", { email, password });
      if (r.mfa_required && r.mfa_token) {
        setChallenge(r.mfa_token);
        setPassword("");
      } else {
        done();
      }
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? t.login.rateLimited : t.login.failed);
    } finally {
      setBusy(false);
    }
  };
  const verify = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/login/verify", { mfa_token: challenge, ...(useRecovery ? { recovery_code: code } : { code }) });
      done();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401 && /expired/i.test(err.message)) {
        setChallenge(null);
        setCode("");
        setError(tf.expired);
      } else {
        setError(err instanceof ApiError && err.status === 429 ? t.login.rateLimited : tf.wrong);
      }
    } finally {
      setBusy(false);
    }
  };

  if (challenge) {
    return (
      <AuthShell title={tf.stepTitle}>
        <Panel className="p-5 sm:p-7">
          <form onSubmit={verify} className="space-y-5" noValidate>
            <p className="text-sm text-ink-2">{tf.stepSub}</p>
            <Field label={useRecovery ? tf.recovery : tf.code} htmlFor="code">
              <Input id="code" dir="ltr" autoFocus autoComplete="one-time-code" inputMode={useRecovery ? "text" : "numeric"}
                maxLength={useRecovery ? 20 : 6} className="font-mono text-lg tracking-widest" value={code}
                onChange={(e) => setCode(e.target.value)} />
            </Field>
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy}
              disabled={useRecovery ? code.trim().length < 8 : code.length !== 6}>{tf.verify}</Button>
            <div className="flex flex-wrap justify-between gap-2 text-sm">
              <button type="button" className="text-ink-2 underline-offset-4 hover:text-ink hover:underline"
                onClick={() => { setUseRecovery((v) => !v); setCode(""); setError(null); }}>
                {useRecovery ? tf.useCode : tf.useRecovery}
              </button>
              <button type="button" className="text-ink-2 underline-offset-4 hover:text-ink hover:underline"
                onClick={() => { setChallenge(null); setCode(""); setError(null); }}>{tf.back}</button>
            </div>
          </form>
        </Panel>
      </AuthShell>
    );
  }

  return (
    <AuthShell title={t.login.title}>
      <div className="grid items-start gap-4">
        <Panel className="p-5 sm:p-7">
          <form onSubmit={submit} className="space-y-5" noValidate>
          <Field label={t.login.email} htmlFor="email">
            <Input id="email" type="email" dir="ltr" autoComplete="username" required value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label={t.login.password} htmlFor="password">
            <Input id="password" type="password" dir="ltr" autoComplete="current-password" required value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy} disabled={!email || !password}>
            {t.login.submit}
          </Button>
          <p className="text-center text-sm"><Link href="/forgot-password" className="text-ink-2 underline-offset-4 hover:text-ink hover:underline">{t.recover.forgotLink}</Link></p>
          </form>
        </Panel>
        <Panel className="p-5 sm:p-7">
          <h2 className="text-lg font-semibold">{t.login.demoTitle}</h2>
          <p className="mt-1 text-sm text-ink-2">{t.login.demoHint}</p>
          <ul className="mt-3 divide-y divide-line">
            {DEMO.map((d) => <li key={d.email}>
              <button type="button" onClick={() => { setEmail(d.email); document.getElementById("password")?.focus(); }}
                className="flex w-full items-center justify-between gap-3 rounded-md px-1 py-2.5 text-start hover:bg-sunken">
                <span className="min-w-0"><span className="block text-sm font-medium">{label(t.roles, d.role)}</span>
                  <bdi className="break-all text-sm text-ink-2">{d.email}</bdi></span>
                <ArrowRight className="h-4 w-4 shrink-0 text-ink-3 rtl:rotate-180" aria-hidden />
              </button>
            </li>)}
          </ul>
        </Panel>
      </div>
      <p className="text-center text-sm text-ink-2">{t.signup.newBusiness} <Link href="/signup" className="font-semibold text-ink underline-offset-4 hover:underline">{t.signup.create}</Link></p>
    </AuthShell>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
