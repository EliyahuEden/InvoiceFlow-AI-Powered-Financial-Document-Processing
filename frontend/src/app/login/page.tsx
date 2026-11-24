"use client";

import { ArrowRight, Check, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Input, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** "Try the demo": a private copy of the demo company for this visitor, signed in, deleted after a day. */
function TryDemo() {
  const { t, locale } = useI18n();
  const d = t.login.tryDemo;
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/demo", { locale });
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? d.limit : err instanceof ApiError && err.status === 403 ? d.off : d.failed);
      setBusy(false);
    }
  };
  return (
    <Panel className="p-5 sm:p-7">
      <h2 className="flex items-center gap-2 text-lg font-bold"><Sparkles className="h-5 w-5 text-accent" aria-hidden />{d.title}</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{d.body}</p>
      <ul className="mt-3 space-y-1.5 text-sm text-ink-2">
        {[d.point1, d.point2, d.point3].map((point) => <li key={point} className="flex items-start gap-2">
          <Check className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden />{point}</li>)}
      </ul>
      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
      <Button type="button" variant="secondary" size="lg" className="mt-4 w-full" loading={busy} onClick={start}>
        {d.cta}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
      </Button>
      <p className="mt-2.5 text-xs text-ink-3">{d.consent}{locale === "he" ? "" : " "}<Link href="/legal/terms" className="underline underline-offset-2 hover:text-ink">{t.legal.terms}</Link>
        {" · "}<Link href="/legal/privacy" className="underline underline-offset-2 hover:text-ink">{t.legal.privacy}</Link></p>
    </Panel>
  );
}

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
        <TryDemo />
      </div>
      <p className="text-center text-sm text-ink-2">{t.signup.newBusiness} <Link href="/signup" className="font-semibold text-ink underline-offset-4 hover:underline">{t.signup.create}</Link></p>
    </AuthShell>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
