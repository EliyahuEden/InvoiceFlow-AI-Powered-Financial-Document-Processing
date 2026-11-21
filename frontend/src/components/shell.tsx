"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import {
  Activity, ArrowLeft, BookOpenText, Bot, Building2, ClipboardCheck, FileStack, FlaskConical, Gauge, Inbox, Languages,
  LayoutGrid, LogOut, Moon, ScrollText, Settings, ShoppingCart, Sun, Upload, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useLiveEvents } from "@/lib/events";
import { ReviewNextButton } from "./review-next";
import { SessionProvider, useSession } from "./session";
import { Button, cx } from "./ui";

type NavItem = { href: string; label: string; icon: React.ElementType; perm?: string };
type NavGroup = { group: string; items: NavItem[] };

function useNav(): NavGroup[] {
  const { t } = useI18n();
  const { can } = useSession();
  const groups: NavGroup[] = [
    { group: t.nav.work, items: [
      { href: "/", label: t.nav.overview, icon: Gauge },
      { href: "/exceptions", label: t.nav.exceptions, icon: ClipboardCheck },
      { href: "/invoices", label: t.nav.inbox, icon: Inbox },
      { href: "/invoices/upload", label: t.nav.upload, icon: Upload, perm: "invoice:upload" },
      { href: "/investigations", label: t.nav.investigations, icon: Bot },
    ]},
    { group: t.nav.records, items: [
      { href: "/suppliers", label: t.nav.suppliers, icon: Building2 },
      { href: "/purchase-orders", label: t.nav.purchaseOrders, icon: ShoppingCart },
      { href: "/knowledge", label: t.nav.knowledge, icon: BookOpenText },
    ]},
    { group: t.nav.quality, items: [
      { href: "/evaluation", label: t.nav.evaluation, icon: FlaskConical },
      { href: "/observability", label: t.nav.observability, icon: Activity },
      { href: "/audit", label: t.nav.audit, icon: ScrollText, perm: "audit:read" },
    ]},
    { group: t.nav.admin, items: [{ href: "/settings", label: t.nav.settings, icon: Settings }] },
  ];
  return groups.map((g) => ({ ...g, items: g.items.filter((i) => !i.perm || can(i.perm)) })).filter((g) => g.items.length);
}

function isActive(path: string, href: string) {
  if (href === "/") return path === "/";
  if (href === "/invoices") return path === "/invoices" || (path.startsWith("/invoices/") && !path.startsWith("/invoices/upload"));
  return path === href || path.startsWith(href + "/");
}

/** Narrow icon rail for wide screens. Every icon has an accessible name and a tooltip;
 *  "All destinations" opens the labelled drawer, so no page is hidden behind an icon. */
function Rail({ onOpenAll }: { onOpenAll: () => void }) {
  const nav = useNav();
  const path = usePathname();
  const { t, dir } = useI18n();
  const side = dir === "rtl" ? "left" : "right";
  return (
    <nav aria-label={t.nav.navigation} className="flex h-full flex-col items-center gap-1 py-5">
      <Link href="/" aria-label={t.app.name} className="mb-4 grid h-11 w-11 place-items-center rounded-2xl bg-primary text-primary-ink shadow-raise">
        <FileStack className="h-5 w-5" aria-hidden />
      </Link>
      <div className="flex flex-1 flex-col items-center gap-1 overflow-y-auto px-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {nav.map((g, gi) => (
          <div key={g.group} className={cx("flex flex-col items-center gap-1", gi > 0 && "mt-2 border-t border-rail-line pt-3")}>
            {g.items.map((item) => {
              const active = isActive(path, item.href);
              const Icon = item.icon;
              return (
                <Tooltip.Root key={item.href} delayDuration={250}>
                  <Tooltip.Trigger asChild>
                    <Link href={item.href} aria-label={item.label} aria-current={active ? "page" : undefined}
                      className={cx("command-nav-link grid h-11 w-11 place-items-center rounded-2xl",
                        active ? "bg-rail-active text-rail-ink shadow-raise" : "text-rail-ink-2 hover:bg-rail-active/70 hover:text-rail-ink")}>
                      <Icon className="h-5 w-5" aria-hidden />
                    </Link>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content side={side} sideOffset={10}
                      className="z-50 rounded-xl bg-primary px-3 py-1.5 text-sm font-medium text-primary-ink shadow-pop">
                      {item.label}
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              );
            })}
          </div>
        ))}
      </div>
      <button type="button" onClick={onOpenAll} aria-label={t.nav.allDestinations} title={t.nav.allDestinations}
        className="command-nav-link mt-2 grid h-11 w-11 place-items-center rounded-2xl text-rail-ink-2 hover:bg-rail-active/70 hover:text-rail-ink">
        <LayoutGrid className="h-5 w-5" aria-hidden />
      </button>
    </nav>
  );
}

/** Labelled, grouped navigation: the full map of the product (desktop on demand, mobile menu). */
function NavDrawer({ onClose }: { onClose: () => void }) {
  const nav = useNav();
  const path = usePathname();
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => previous?.focus?.();
  }, []);
  return (
    <div className="fixed inset-0 z-40" onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div className="absolute inset-0 bg-ink/25 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-label={t.nav.allDestinations}
        onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}
        className="absolute inset-y-3 start-3 flex w-[min(20rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-pop">
        <div className="flex items-center justify-between gap-2 border-b border-line px-5 py-4">
          <span className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-ink"><FileStack className="h-[18px] w-[18px]" aria-hidden /></span>
            <span className="leading-tight">
              <span className="block text-md font-semibold text-ink">{t.app.name}</span>
              <span className="block text-xs text-ink-3">{t.app.tagline}</span>
            </span>
          </span>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t.common.close}><X className="h-5 w-5" /></Button>
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
          {nav.map((g) => (
            <div key={g.group}>
              <p className="px-3 pb-1.5 text-xs font-semibold text-ink-3">{g.group}</p>
              <ul className="space-y-0.5">
                {g.items.map((item) => {
                  const active = isActive(path, item.href);
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link href={item.href} onClick={onClose} aria-current={active ? "page" : undefined}
                        className={cx("command-nav-link flex h-10 items-center gap-3 rounded-2xl px-3 text-base",
                          active ? "bg-sunken font-semibold text-ink" : "text-ink-2 hover:bg-sunken/70 hover:text-ink")}>
                        <Icon className={cx("h-[18px] w-[18px] shrink-0", active ? "text-ink" : "text-ink-3")} aria-hidden />
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AiModeBadge() {
  const { me } = useSession();
  const { t } = useI18n();
  if (!me) return null;
  const offline = me.ai_mode.startsWith("offline");
  return (
    <span title={offline ? t.ai.offlineHint : undefined}
      className={cx("inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset sm:max-w-none",
        offline ? "bg-warn-soft text-warn ring-warn/25" : "bg-ai-soft text-ai ring-ai-line")}>
      <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", offline ? "bg-warn" : "bg-ai")} aria-hidden />
      {offline ? <><span className="sm:hidden">{t.ai.offlineShort}</span><span className="hidden sm:inline">{t.ai.offlineMode}</span></>
        : <span className="truncate">{`${t.ai.liveMode}: ${me.ai_mode.replace("llm:", "")}`}</span>}
    </span>
  );
}

function useCurrentLabel(): string | null {
  const nav = useNav();
  const path = usePathname();
  const items = nav.flatMap((g) => g.items).filter((i) => isActive(path, i.href));
  return items.sort((a, b) => b.href.length - a.href.length)[0]?.label ?? null;
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const { me, can } = useSession();
  const { t, locale, setLocale } = useI18n();
  const current = useCurrentLabel();
  const path = usePathname();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    let saved: "light" | "dark" = "light";
    try { saved = (localStorage.getItem("if_theme") as "light" | "dark") ?? "light"; } catch { /* storage unavailable */ }
    setTheme(saved);
    document.documentElement.dataset.theme = saved;
  }, []);
  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("if_theme", next); } catch { /* storage unavailable */ }
  };
  const logout = async () => {
    await api.post("/api/auth/logout");
    window.location.href = "/login";
  };
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-2 bg-bg/70 px-4 backdrop-blur-md sm:gap-3 lg:px-8">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu} aria-label={t.nav.allDestinations}>
        <LayoutGrid className="h-5 w-5" />
      </Button>
      <div className="flex min-w-0 flex-1 items-baseline gap-2 truncate">
        <span className="hidden text-lg font-semibold tracking-tight text-ink sm:inline">{t.app.name}</span>
        {current && <><span className="hidden text-ink-3 sm:inline" aria-hidden>/</span>
          <span className="truncate text-base text-ink-2">{current}</span></>}
      </div>
      <AiModeBadge />
      {/* the dashboard and the workspace carry their own primary review action */}
      {me && can("exception:decide") && path !== "/" && !path.startsWith("/exceptions") &&
        <ReviewNextButton size="sm" className="hidden md:inline-flex" />}
      <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")} aria-label={t.common.language}>
        <Languages className="h-4 w-4" aria-hidden /> {locale === "he" ? "EN" : "עב"}
      </Button>
      <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={t.common.theme}>
        {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
      </Button>
      {me && (
        <div className="hidden items-center gap-2 ps-1 xl:flex">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-surface text-xs font-semibold text-ink shadow-raise" aria-hidden>
            {me.user.full_name.split(" ").map((p) => p[0]).join("").slice(0, 2)}
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold text-ink">{me.user.full_name}</span>
            <span className="block text-2xs text-ink-3">{(t.roles as Record<string, string>)[me.role]}</span>
          </span>
        </div>
      )}
      <Button variant="ghost" size="icon" onClick={logout} aria-label={t.common.logout} title={t.common.logout}>
        <LogOut className="h-4 w-4" />
      </Button>
    </header>
  );
}

function LiveEvents() {
  useLiveEvents();
  return null;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const path = usePathname();
  useEffect(() => setOpen(false), [path]);
  return (
    <SessionProvider>
      <Tooltip.Provider>
        <LiveEvents />
        <a href="#main" className="command-skip">{t.nav.skipContent}</a>
        <div className="flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-[84px] shrink-0 lg:block">
            <Rail onOpenAll={() => setOpen(true)} />
          </aside>
          {open && <NavDrawer onClose={() => setOpen(false)} />}
          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar onMenu={() => setOpen(true)} />
            <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1560px] flex-1 px-4 pb-10 pt-2 focus:outline-none sm:px-6 lg:px-8">{children}</main>
          </div>
        </div>
      </Tooltip.Provider>
    </SessionProvider>
  );
}

export function PageHeader({ title, sub, actions, back }: {
  title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode; back?: { href: string; label: string };
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {back && (
          <Link href={back.href} className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 hover:text-ink">
            <ArrowLeft className="h-4 w-4 ltr:rotate-180" aria-hidden /> {back.label}
          </Link>
        )}
        <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{title}</h1>
        {sub && <p className="mt-1.5 text-md text-ink-2">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
