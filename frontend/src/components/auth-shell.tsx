"use client";

import { Check, Languages } from "lucide-react";
import { InvoiceStack } from "./invoice-stack";
import { LogoMark } from "./logo";
import { useI18n } from "@/lib/i18n";
import { MatchStack } from "./match-stack";
import { Button } from "./ui";

/** The product's mechanism, shown before sign-in: one invoice line checked against its order and receipt (synthetic). */
function MatchPreview() {
  const { t } = useI18n();
  const e = t.login.evidence;
  return (
    <figure className="w-full max-w-md" aria-hidden>
      <div className="rounded-2xl border border-line bg-surface shadow-pop">
        <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-2.5">
          <span className="text-sm font-medium text-ink">{e.title}</span>
          <span dir="auto" className="text-sm text-ink-3">{e.supplier}</span>
        </div>
        <div className="space-y-3 p-4">
          <p dir="auto" className="flex items-center justify-between gap-3 text-base font-medium text-ink">
            {e.item1}
            <span className="rounded-[5px] border border-danger/25 bg-danger-soft px-1.5 text-xs font-medium text-danger">{t.finding.QUANTITY_EXCEEDS_RECEIVED}</span>
          </p>
          <MatchStack invoice={{ quantity: "60", unit_price: "118" }} order={{ quantity: "60", unit_price: "118" }}
            receivedQty="50" currency="ILS" mismatch="quantity" difference="10" severity="critical" />
        </div>
      </div>
      <figcaption className="mt-3 flex items-center gap-2 text-sm text-ink-3">
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
      <section className="brand-panel relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:gap-10 lg:p-12" aria-label={t.app.name}>
        <span className="flex items-center gap-2.5 text-2xl font-extrabold tracking-tight text-ink">
          <LogoMark className="h-9 w-9" />{t.app.name}
        </span>
        <InvoiceStack label={t.review.invoiceEmblem} className="absolute end-12 top-10 hidden h-[190px] w-[168px] xl:block" />
        <div className="max-w-xl space-y-10">
          <div>
            <h2 className="text-[2.75rem] font-extrabold leading-[1.08] tracking-[-0.03em] text-ink xl:text-[3.25rem]">{t.login.heroTitle}</h2>
            <ul className="mt-6 space-y-2.5">
              {[t.login.pointRead, t.login.pointMatch, t.login.pointExplain].map((point) => (
                <li key={point} className="flex items-start gap-2.5 text-lg text-ink-2">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-accent" aria-hidden />
                  {point}
                </li>
              ))}
            </ul>
          </div>
          <MatchPreview />
        </div>
        <p className="text-sm text-ink-3">{t.login.synthetic}</p>
      </section>
      <div className="mx-auto flex w-full max-w-md flex-col justify-center gap-6 px-4 py-8 sm:px-6">
        <header className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-xl font-extrabold lg:invisible">
            <LogoMark className="h-8 w-8" />{t.app.name}
          </span>
          <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")}>
            <Languages className="h-3.5 w-3.5" aria-hidden /> {locale === "he" ? "English" : "עברית"}
          </Button>
        </header>
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">{title}</h1>
          <p className="mt-1 text-base text-ink-3 lg:hidden">{t.app.tagline}</p>
        </div>
        {children}
      </div>
    </main>
  );
}
