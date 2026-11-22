"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Input, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

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

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/login", { email, password });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? t.login.rateLimited : t.login.failed);
    } finally {
      setBusy(false);
    }
  };

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
          </form>
        </Panel>
        <Panel className="p-5 sm:p-7">
          <h2 className="text-lg font-semibold">{t.login.demoTitle}</h2>
          <p className="mt-1 text-sm text-ink-2">{t.login.demoHint}</p>
          <ul className="mt-3 divide-y divide-line">
            {DEMO.map((d) => <li key={d.email}>
              <button type="button" onClick={() => { setEmail(d.email); document.getElementById("password")?.focus(); }}
                className="flex w-full items-center justify-between gap-3 rounded-md px-1 py-2.5 text-start hover:bg-sunken">
                <span className="min-w-0"><span className="block text-sm font-medium">{(t.roles as Record<string, string>)[d.role]}</span>
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
