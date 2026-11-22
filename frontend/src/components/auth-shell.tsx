"use client";

import { Check, FileStack, Languages } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Button } from "./ui";

/** The product's signature on paper: a slice of a supplier invoice whose total is boxed and traced to its source. */
function EvidenceCard() {
  const { t } = useI18n();
  const e = t.login.evidence;
  const row = "flex items-baseline justify-between gap-6 py-1.5";
  return (
    <figure className="max-w-md" aria-hidden>
      <div className="rounded-xl border border-line bg-surface p-5 shadow-panel">
        <div className="flex items-baseline justify-between gap-4 border-b border-line pb-3">
          <span className="text-sm font-semibold text-ink">{e.title}</span>
          <span dir="auto" className="text-sm text-ink-3">{e.supplier}</span>
        </div>
        <div className="py-2 text-sm text-ink-2">
          <div className={row}><span dir="auto">{e.item1}</span><span className="num" dir="ltr">60 × 118.00</span><span className="num" dir="ltr">7,080.00</span></div>
          <div className={row}><span dir="auto">{e.item2}</span><span className="num" dir="ltr">4 × 210.00</span><span className="num" dir="ltr">840.00</span></div>
        </div>
        <div className="border-t border-line pt-2 text-sm text-ink-2">
          <div className={row}><span>{e.subtotal}</span><span className="num" dir="ltr">7,920.00</span></div>
          <div className={row}><span>{e.vat}</span><span className="num" dir="ltr">1,425.60</span></div>
          {/* the evidence box: the same thin navy outline the review workspace draws around a value it read */}
          <div className="-mx-2 mt-1 flex items-baseline justify-between gap-6 rounded-md px-2 py-1.5 ring-[1.5px] ring-accent">
            <span className="font-semibold text-ink">{e.total}</span>
            <span className="num text-base font-semibold text-ink" dir="ltr">₪9,345.60</span>
          </div>
        </div>
      </div>
      <figcaption className="mt-2.5 flex items-center gap-2 text-sm text-ink-3">
        <span className="h-px w-5 bg-accent" />
        <bdi>{e.tag}</bdi>
      </figcaption>
    </figure>
  );
}

/** Split screen shared by sign-in and sign-up: the brand panel on wide screens, the form beside it. */
export function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  const { t, locale, setLocale } = useI18n();
  return (
    <main className="grid min-h-svh lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section className="brand-panel relative hidden lg:flex lg:flex-col lg:justify-between lg:gap-10 lg:p-12" aria-label={t.app.name}>
        <span className="flex items-center gap-3 text-xl font-semibold text-ink">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary text-primary-ink"><FileStack className="h-5 w-5" aria-hidden /></span>
          {t.app.name}
        </span>
        <div className="max-w-xl space-y-10">
          <div>
            <h2 className="text-4xl font-semibold leading-tight tracking-tight text-ink xl:text-5xl">{t.login.heroTitle}</h2>
            <ul className="mt-6 space-y-3">
              {[t.login.pointRead, t.login.pointMatch, t.login.pointExplain].map((point) => (
                <li key={point} className="flex items-start gap-2.5 text-base text-ink-2">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-ink-3" aria-hidden />
                  {point}
                </li>
              ))}
            </ul>
          </div>
          <EvidenceCard />
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
