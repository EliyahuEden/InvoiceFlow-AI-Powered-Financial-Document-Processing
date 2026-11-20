"use client";

import { FileStack, Languages } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, Field, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const DEMO = [
  { email: "finance@kinneret.example", role: "finance_reviewer" },
  { email: "procurement@kinneret.example", role: "procurement_manager" },
  { email: "admin@kinneret.example", role: "admin" },
  { email: "viewer@kinneret.example", role: "read_only" },
];

function LoginForm() {
  const { t, locale, setLocale } = useI18n();
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
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="flex flex-col justify-between px-6 py-8 sm:px-12">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-md bg-accent text-white"><FileStack className="h-4 w-4" /></span>
            <span className="text-md font-semibold">{t.app.name}</span>
          </span>
          <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")}>
            <Languages className="h-4 w-4" /> {locale === "he" ? "English" : "עברית"}
          </Button>
        </div>
        <form onSubmit={submit} className="mx-auto w-full max-w-sm space-y-5 py-10" noValidate>
          <div>
            <h1 className="text-2xl font-semibold">{t.login.title}</h1>
            <p className="mt-1 text-base text-ink-2">{t.app.tagline}</p>
          </div>
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
          <div className="rounded-lg border border-line bg-surface p-3">
            <p className="text-sm font-medium text-ink">{t.login.demoTitle}</p>
            <p className="mt-0.5 text-xs text-ink-3">{t.login.demoHint}</p>
            <ul className="mt-2 divide-y divide-line">
              {DEMO.map((d) => (
                <li key={d.email}>
                  <button type="button" onClick={() => setEmail(d.email)}
                    className="flex w-full items-center justify-between gap-2 py-1.5 text-start text-sm hover:text-accent">
                    <span className="ltr font-mono text-xs">{d.email}</span>
                    <span className="text-xs text-ink-3">{(t.roles as Record<string, string>)[d.role]}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </form>
        <p className="text-xs text-ink-3">Synthetic demo data · no real financial records</p>
      </div>
      <div className="relative hidden overflow-hidden border-s border-line bg-rail lg:block" aria-hidden>
        <LedgerIllustration />
      </div>
    </div>
  );
}

/** A geometric depiction of the pipeline: document → extracted fields → matched PO line. */
function LedgerIllustration() {
  return (
    <div className="flex h-full items-center justify-center p-12">
      <div className="w-full max-w-lg space-y-3">
        {[
          ["חשבונית מס HC-8841", "₪10,903.20", "ok"],
          ["HC-ESP-1KG · 60 × 118.00", "7,080.00", "warn"],
          ["GR-5002 · received 50", "Δ 10 × 118.00", "danger"],
          ["הסכם חרמון §2 · billing on delivered qty", "cited", "ai"],
        ].map(([a, b, tone], i) => (
          <div key={i} className="flex items-center justify-between rounded-lg border border-line bg-surface px-4 py-3 shadow-raise"
            style={{ marginInlineStart: `${i * 18}px` }}>
            <span dir="auto" className="text-sm text-ink">{a}</span>
            <span className={`ltr font-mono text-xs ${tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : tone === "danger" ? "text-danger" : "text-ai"}`}>{b}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
