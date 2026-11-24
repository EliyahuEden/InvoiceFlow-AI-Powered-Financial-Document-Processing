"use client";

import { Languages } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LegalFooter } from "@/components/legal-footer";
import { LogoMark } from "@/components/logo";
import { Button, cx } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

/** Public frame for the legal pages: reachable without signing in (see middleware.ts). */
export default function LegalLayout({ children }: { children: React.ReactNode }) {
  const { t, locale, setLocale } = useI18n();
  const path = usePathname();
  const pages = [
    { href: "/legal/terms", label: t.legal.terms },
    { href: "/legal/privacy", label: t.legal.privacy },
    { href: "/legal/dpa", label: t.legal.dpa },
    { href: "/legal/accessibility", label: t.legal.accessibility },
    { href: "/legal", label: t.legal.contact },
  ];
  return (
    <div className="min-h-svh">
      <a href="#main" className="command-skip">{t.nav.skipContent}</a>
      <header className="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-3 px-4">
          <Link href="/" className="flex items-center gap-2 text-xl font-extrabold text-ink"><LogoMark className="h-8 w-8" />{t.app.name}</Link>
          <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")}>
            <Languages className="h-4 w-4" aria-hidden /> {locale === "he" ? "English" : "עברית"}
          </Button>
        </div>
        <nav aria-label={t.legal.title} className="mx-auto flex max-w-5xl gap-1 overflow-x-auto px-4 pb-2">
          {pages.map((p) => <Link key={p.href} href={p.href} aria-current={path === p.href ? "page" : undefined}
            className={cx("whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-semibold transition-colors",
              path === p.href ? "bg-rail-active text-accent-ink" : "text-ink-2 hover:bg-ink/[.04] hover:text-ink")}>{p.label}</Link>)}
        </nav>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto max-w-5xl px-4 py-8">{children}</main>
      <LegalFooter />
    </div>
  );
}
