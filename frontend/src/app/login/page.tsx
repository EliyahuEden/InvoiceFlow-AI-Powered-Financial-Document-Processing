"use client";

import { AlertCircle, ArrowRight, Eye, EyeOff, Lock, Mail, Play, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, cx, Field, Input, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** "Try the demo" as the secondary action: a private copy of the demo company, signed in, deleted after a day. */
function TryDemo({ onStart }: { onStart: () => void }) {
  const { t, locale } = useI18n();
  const d = t.login.tryDemo;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/demo", { locale });
      onStart();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? d.limit : err instanceof ApiError && err.status === 403 ? d.off : d.failed);
      setBusy(false);
    }
  };
  return (
    <div>
      <Button type="button" variant="secondary" size="lg" loading={busy} onClick={start} aria-describedby="demo-hint"
        className="h-12 w-full rounded-[14px] border-accent/30 bg-surface/70 text-accent-ink hover:border-accent/50 hover:bg-accent-soft/60">
        <Play className="h-4 w-4" aria-hidden />{d.cta}
      </Button>
      <p id="demo-hint" className="mt-2 text-center text-sm text-ink-3">{d.hint}</p>
      {error && <p role="alert" className="mt-2 text-center text-sm text-danger">{error}</p>}
      <p className="mt-1 text-center text-xs text-ink-3">{d.consent}{locale === "he" ? "" : " "}<Link href="/legal/terms" className="underline underline-offset-2 hover:text-ink">{t.legal.terms}</Link>
        {" · "}<Link href="/legal/privacy" className="underline underline-offset-2 hover:text-ink">{t.legal.privacy}</Link></p>
    </div>
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
  const [showPassword, setShowPassword] = useState(false);
  // a short fade into the app; navigation starts at once and never waits for it
  const [leaving, setLeaving] = useState(false);
  const tf = t.twoFactor;

  const done = () => {
    const next = params.get("next");
    setLeaving(true);
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
      <AuthShell title={tf.stepTitle} leaving={leaving}>
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
    <AuthShell eyebrow={t.login.welcome} title={t.login.heading} sub={t.login.workspace} leaving={leaving}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label={t.login.email} htmlFor="email">
          <div className="relative">
            <Mail className="pointer-events-none absolute start-3.5 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-3" aria-hidden />
            <Input id="email" type="email" dir="ltr" autoComplete="username" inputMode="email" required value={email}
              onChange={(e) => setEmail(e.target.value)} className="h-12 rounded-[14px] bg-surface ps-11 text-base" />
          </div>
        </Field>
        <Field label={t.login.password} htmlFor="password">
          <div className="relative">
            <Lock className="pointer-events-none absolute start-3.5 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-3" aria-hidden />
            <Input id="password" type={showPassword ? "text" : "password"} dir="ltr" autoComplete="current-password" required value={password}
              onChange={(e) => setPassword(e.target.value)} className="h-12 rounded-[14px] bg-surface pe-12 ps-11 text-base" />
            <button type="button" onClick={() => setShowPassword((v) => !v)} aria-pressed={showPassword}
              aria-label={showPassword ? t.login.hidePassword : t.login.showPassword}
              className="absolute end-1.5 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-[10px] text-ink-3 transition-colors hover:bg-accent-soft hover:text-accent-ink">
              <span className="relative h-[18px] w-[18px]">
                <Eye className={cx("absolute inset-0 h-[18px] w-[18px] transition-[opacity,transform] duration-200", showPassword ? "scale-75 opacity-0" : "opacity-100")} aria-hidden />
                <EyeOff className={cx("absolute inset-0 h-[18px] w-[18px] transition-[opacity,transform] duration-200", showPassword ? "opacity-100" : "scale-75 opacity-0")} aria-hidden />
              </span>
            </button>
          </div>
        </Field>
        <p className="text-end text-sm"><Link href="/forgot-password" className="font-semibold text-accent-ink underline-offset-4 hover:underline">{t.recover.forgotLink}</Link></p>
        {error && <p role="alert" className="flex items-start gap-2 rounded-[12px] border border-danger/25 bg-danger-soft px-3.5 py-2.5 text-sm font-medium text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{error}</p>}
        <Button type="submit" variant="primary" size="lg" className="h-12 w-full rounded-[14px] text-base transition-transform active:scale-[.985]"
          loading={busy} disabled={!email || !password}>
          {t.login.submit}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
        </Button>
      </form>
      <div className="my-5 flex items-center gap-3 text-sm text-ink-3" aria-hidden><span className="h-px flex-1 bg-ink/10" />{t.login.or}<span className="h-px flex-1 bg-ink/10" /></div>
      <TryDemo onStart={() => { setLeaving(true); router.replace("/"); }} />
      <p className="mt-6 text-center text-sm text-ink-2">{t.signup.newBusiness} <Link href="/signup" className="font-semibold text-ink underline-offset-4 hover:underline">{t.signup.create}</Link></p>
      <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-ink-3"><ShieldCheck className="h-3.5 w-3.5" aria-hidden />{t.login.secure}</p>
    </AuthShell>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
