"use client";

import { Languages } from "lucide-react";
import Link from "next/link";
import { LegalFooter } from "./legal-footer";
import { LoginScene } from "./login-scene";
import { LogoMark } from "./logo";
import { useI18n } from "@/lib/i18n";
import { Button, cx } from "./ui";

/**
 * The entrance shared by sign-in, sign-up, password reset and invitations.
 *
 * Desktop: the form (42%) on the reading-start side and the invoice scene (58%) beside it, so Hebrew puts the form on
 * the right and English on the left. Phones: brand, a compact still scene (about a fifth of the screen), then the form,
 * so the fields and the main action are reached without scrolling. The form never waits for the scene: the scene is
 * decorative CSS that paints with the page.
 */
export function AuthShell({ title, sub, eyebrow, children, leaving = false }: {
  title: string; sub?: string; eyebrow?: string; children: React.ReactNode; leaving?: boolean;
}) {
  const { t, locale, setLocale } = useI18n();
  const enter = (i: number) => ({ className: "login-enter", style: { animationDelay: `${80 + i * 60}ms` } });
  return (
    <main className={cx("grid min-h-svh lg:grid-cols-[minmax(0,42fr)_minmax(0,58fr)]", leaving && "login-leaving")}>
      <div className="login-panel flex min-h-svh flex-col">
        <header className="flex items-center justify-between gap-4 px-5 pt-5 sm:px-8 lg:px-12 lg:pt-8">
          <Link href="/login" className="flex items-center gap-2.5 text-xl font-extrabold tracking-tight text-ink lg:text-2xl">
            <LogoMark className="h-8 w-8 lg:h-9 lg:w-9" />{t.app.name}
          </Link>
          <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")}>
            <Languages className="h-4 w-4" aria-hidden /> {locale === "he" ? "English" : "עברית"}
          </Button>
        </header>
        {/* phones and tablets: the scene, compact and still */}
        <LoginScene compact className="mx-4 mt-4 h-[clamp(9.5rem,22svh,13rem)] rounded-[22px] sm:mx-8 lg:hidden" />
        <div className="mx-auto flex w-full max-w-[440px] flex-1 flex-col justify-center px-5 py-7 sm:px-0 lg:py-10">
          {eyebrow && <p {...enter(0)}><span className="inline-flex rounded-full bg-accent-soft px-3.5 py-1 text-sm font-semibold text-accent-ink">{eyebrow}</span></p>}
          <h1 className={cx(enter(1).className, "mt-3 text-[2rem] font-extrabold leading-tight tracking-[-0.025em] text-ink sm:text-[2.6rem]")} style={enter(1).style}>{title}</h1>
          {sub && <p className={cx(enter(2).className, "mt-1.5 text-lg text-ink-3")} style={enter(2).style}>{sub}</p>}
          <div className={cx(enter(3).className, "mt-7")} style={enter(3).style}>{children}</div>
        </div>
        <LegalFooter className="w-full max-w-none px-5 pb-5 pt-2 text-xs sm:px-8 lg:px-12" />
      </div>
      <LoginScene className="sticky top-0 hidden h-svh lg:flex" />
    </main>
  );
}
