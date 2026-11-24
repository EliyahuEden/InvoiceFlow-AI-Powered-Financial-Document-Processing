"use client";

import { Accessibility, FileText, Handshake, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { OPERATOR } from "@/lib/legal";
import { Value } from "./_content/render";

/** Legal index: who runs the service and how to reach them (business identification), plus every policy. */
export default function LegalIndex() {
  const { t, locale } = useI18n();
  const L = locale === "he" ? "he" : "en";
  const docs = [
    { href: "/legal/terms", label: t.legal.terms, sub: t.legal.termsSub, icon: FileText },
    { href: "/legal/privacy", label: t.legal.privacy, sub: t.legal.privacySub, icon: ShieldCheck },
    { href: "/legal/dpa", label: t.legal.dpa, sub: t.legal.dpaSub, icon: Handshake },
    { href: "/legal/accessibility", label: t.legal.accessibility, sub: t.legal.accessibilitySub, icon: Accessibility },
  ];
  const rows = ([
    [t.legal.operator, OPERATOR.name[L]], [t.legal.registration, OPERATOR.registrationNumber],
    [t.legal.address, OPERATOR.address[L]], [t.legal.email, OPERATOR.email], [t.legal.privacyContact, OPERATOR.privacyEmail],
  ] as [string, string][]).filter(([, v]) => v); // details not yet registered are left out
  return (
    <div className="space-y-6">
      <section className="command-panel px-5 py-7 sm:px-10">
        <h1 className="text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">{t.legal.title}</h1>
        <p className="mt-2 max-w-[65ch] text-md text-ink-2">{t.legal.indexSub}</p>
        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
          {docs.map(({ href, label, sub, icon: Icon }) => (
            <li key={href}>
              <Link href={href} className="flex h-full items-start gap-3 rounded-2xl border border-line bg-surface p-4 transition-colors hover:border-accent/30 hover:bg-accent-soft/40">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><Icon className="h-5 w-5" aria-hidden /></span>
                <span><span className="block text-base font-bold text-ink">{label}</span><span className="block text-sm text-ink-3">{sub}</span></span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
      <section className="command-panel px-5 py-7 sm:px-10" aria-labelledby="contact-h">
        <h2 id="contact-h" className="flex items-center gap-2 text-xl font-bold text-ink"><Mail className="h-5 w-5 text-ink-3" aria-hidden />{t.legal.contact}</h2>
        <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-[max-content_1fr]">
          {rows.map(([k, v]) => <div key={k} className="contents">
            <dt className="text-sm font-semibold text-ink-3">{k}</dt>
            <dd className="text-base text-ink"><Value v={v} /></dd>
          </div>)}
        </dl>
      </section>
    </div>
  );
}
