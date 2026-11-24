"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { cx } from "./ui";

/** Links to the legal pages, shown on the public pages and at the foot of the app. */
export function LegalFooter({ className }: { className?: string }) {
  const { t } = useI18n();
  const links = [
    { href: "/legal/terms", label: t.legal.terms }, { href: "/legal/privacy", label: t.legal.privacy },
    { href: "/legal/dpa", label: t.legal.dpa }, { href: "/legal/accessibility", label: t.legal.accessibility },
    { href: "/legal", label: t.legal.contact },
  ];
  return (
    <footer className={cx("mx-auto max-w-5xl px-4 py-6 text-sm text-ink-3", className)}>
      <nav aria-label={t.legal.title} className="flex flex-wrap items-center gap-x-4 gap-y-0.5">
        <span>© {new Date().getFullYear()} {t.app.name}</span>
        {/* at least 24px tall targets (WCAG 2.2, 2.5.8) */}
        {links.map((l) => <Link key={l.href} href={l.href} className="inline-flex min-h-6 items-center underline-offset-4 hover:text-ink hover:underline">{l.label}</Link>)}
      </nav>
    </footer>
  );
}
