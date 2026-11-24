"use client";

import { Fragment } from "react";
import { useI18n } from "@/lib/i18n";
import { isPlaceholder, LEGAL_UPDATED, OPERATOR } from "@/lib/legal";
import type { LegalDoc } from "./types";

/** A filled-in operator value, or a highlighted placeholder that still has to be completed before going live. */
function Value({ v }: { v: string }) {
  return isPlaceholder(v)
    ? <mark className="rounded bg-warn-soft px-1 font-semibold text-warn">{v}</mark>
    : <bdi>{v}</bdi>;
}

/** Text with {tokens} replaced by the operator's details. */
function Filled({ text }: { text: string }) {
  const { locale } = useI18n();
  const L = locale === "he" ? "he" : "en";
  const values: Record<string, string> = {
    name: OPERATOR.name[L], reg: OPERATOR.registrationNumber, address: OPERATOR.address[L], email: OPERATOR.email,
    privacyEmail: OPERATOR.privacyEmail, hosting: OPERATOR.hosting[L], a11yName: OPERATOR.accessibility.name[L],
    // the phone carries its own label, so the whole phrase disappears when there is no phone
    a11yPhone: OPERATOR.accessibility.phone ? `${L === "he" ? "טלפון" : "phone"} ${OPERATOR.accessibility.phone}, ` : "",
    a11yEmail: OPERATOR.accessibility.email, updated: LEGAL_UPDATED[L],
  };
  // an empty value is left out together with the ", " that introduced it ("{name}, {reg}, {address}")
  const out: React.ReactNode[] = [];
  text.split(/(\{[a-zA-Z0-9]+\})/).forEach((part, i) => {
    const key = part.match(/^\{([a-zA-Z0-9]+)\}$/)?.[1];
    if (!key || !(key in values)) { out.push(part); return; }
    const v = values[key]!;
    if (!v) {
      if (key === "a11yPhone") return; // carries its own separator
      const last = out[out.length - 1];
      if (typeof last === "string" && last.endsWith(", ")) out[out.length - 1] = last.slice(0, -2);
      return;
    }
    out.push(key === "a11yPhone" ? v : <Value key={i} v={v} />);
  });
  return <>{out.map((node, i) => <Fragment key={i}>{node}</Fragment>)}</>;
}

/** One legal document in the reader's language, with a section index. */
export function LegalDocument({ doc }: { doc: LegalDoc }) {
  const { locale, t } = useI18n();
  const d = locale === "he" ? doc.he : doc.en;
  return (
    <article className="command-panel px-5 py-7 sm:px-10 sm:py-10">
      <h1 className="text-3xl font-extrabold tracking-tight text-ink sm:text-4xl">{d.title}</h1>
      <p className="mt-2 text-sm text-ink-3">{t.legal.updated} <Filled text="{updated}" /></p>
      <p className="mt-5 max-w-[70ch] text-md leading-relaxed text-ink-2"><Filled text={d.intro} /></p>
      <nav aria-label={t.legal.contents} className="mt-6 rounded-2xl border border-line bg-sunken/60 p-4">
        <p className="mb-2 text-sm font-bold text-ink">{t.legal.contents}</p>
        <ol className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          {d.sections.map((s, i) => <li key={s.h}><a href={`#s${i + 1}`} className="text-accent-ink underline-offset-4 hover:underline">{i + 1}. {s.h}</a></li>)}
        </ol>
      </nav>
      <div className="mt-8 space-y-8">
        {d.sections.map((s, i) => (
          <section key={s.h} id={`s${i + 1}`} className="max-w-[72ch] scroll-mt-24">
            <h2 className="text-xl font-bold text-ink">{i + 1}. {s.h}</h2>
            {s.p?.map((para) => <p key={para} className="mt-3 text-base leading-relaxed text-ink-2"><Filled text={para} /></p>)}
            {s.li && <ul className="mt-3 list-disc space-y-1.5 ps-5 text-base leading-relaxed text-ink-2">
              {s.li.map((item) => <li key={item}><Filled text={item} /></li>)}
            </ul>}
          </section>
        ))}
      </div>
    </article>
  );
}

export { Filled, Value };
