"use client";

import { Check, FileStack, Languages } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Button } from "./ui";

/** Split screen shared by sign-in and sign-up: the brand panel on wide screens, the form beside it. */
export function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  const { t, locale, setLocale } = useI18n();
  return (
    <main className="grid min-h-svh lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section className="aurora relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-12" aria-label={t.app.name}>
        <span className="flex items-center gap-3 text-xl font-semibold text-ink">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-primary text-primary-ink shadow-raise"><FileStack className="h-5 w-5" aria-hidden /></span>
          {t.app.name}
        </span>
        <div className="max-w-xl">
          <h2 className="text-5xl font-semibold leading-[1.05] tracking-tight text-ink">{t.login.heroTitle}</h2>
          <ul className="mt-8 space-y-4">
            {[t.login.pointRead, t.login.pointMatch, t.login.pointExplain].map((point) => (
              <li key={point} className="flex items-start gap-3 text-lg text-ink-2">
                <span className="mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface/80 text-ok shadow-raise"><Check className="h-3.5 w-3.5" aria-hidden /></span>
                {point}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-ink-3">{t.login.synthetic}</p>
      </section>
      <div className="mx-auto flex w-full max-w-xl flex-col justify-center gap-6 px-4 py-8 sm:px-8">
        <header className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-2.5 text-lg font-semibold lg:invisible">
            <FileStack className="h-6 w-6" aria-hidden />{t.app.name}
          </span>
          <Button variant="secondary" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")}>
            <Languages className="h-4 w-4" aria-hidden /> {locale === "he" ? "English" : "עברית"}
          </Button>
        </header>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
          <p className="mt-1.5 text-base text-ink-2 lg:hidden">{t.app.tagline}</p>
        </div>
        {children}
      </div>
    </main>
  );
}
