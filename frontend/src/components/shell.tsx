"use client";

import {
  Activity, ArrowLeft, BookOpenText, Bot, Building2, ClipboardCheck, FileStack, FlaskConical, Gauge, Inbox, Languages,
  LogOut, Menu, Moon, ScrollText, Settings, ShoppingCart, Sun, Upload, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useLiveEvents } from "@/lib/events";
import { SessionProvider, useSession } from "./session";
import { Button, cx } from "./ui";

type NavItem = { href: string; label: string; icon: React.ElementType; perm?: string };

function useNav(): { group: string; items: NavItem[] }[] {
  const { t } = useI18n();
  return [
    { group: t.nav.work, items: [
      { href: "/", label: t.nav.overview, icon: Gauge },
      { href: "/invoices", label: t.nav.inbox, icon: Inbox },
      { href: "/invoices/upload", label: t.nav.upload, icon: Upload, perm: "invoice:upload" },
      { href: "/exceptions", label: t.nav.exceptions, icon: ClipboardCheck },
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
}

function isActive(path: string, href: string) {
  if (href === "/") return path === "/";
  if (href === "/invoices") return path === "/invoices" || (path.startsWith("/invoices/") && !path.startsWith("/invoices/upload"));
  return path === href || path.startsWith(href + "/");
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const nav = useNav();
  const path = usePathname();
  const { can } = useSession();
  const { t } = useI18n();
  return (
    <nav aria-label="Main" className="flex h-full flex-col">
      <Link href="/" className="flex items-center gap-2.5 px-4 pb-4 pt-5" onClick={onNavigate}>
        <span className="grid h-8 w-8 place-items-center rounded-md bg-accent text-white">
          <FileStack className="h-4.5 w-4.5" aria-hidden />
        </span>
        <span className="leading-tight">
          <span className="block text-md font-semibold text-ink">{t.app.name}</span>
          <span className="block text-2xs text-ink-3">{t.app.tagline}</span>
        </span>
      </Link>
      <div className="flex-1 space-y-5 overflow-y-auto px-2.5 pb-4">
        {nav.map((g) => (
          <div key={g.group}>
            <p className="px-2 pb-1 text-2xs font-semibold uppercase tracking-wider text-ink-3">{g.group}</p>
            <ul className="space-y-0.5">
              {g.items.filter((i) => !i.perm || can(i.perm)).map((item) => {
                const active = isActive(path, item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cx(
                        "flex h-8 items-center gap-2.5 rounded-md px-2 text-base transition-colors",
                        active ? "bg-surface font-medium text-ink shadow-raise" : "text-ink-2 hover:bg-surface/60 hover:text-ink",
                      )}
                    >
                      <Icon className={cx("h-4 w-4 shrink-0", active ? "text-accent" : "text-ink-3")} aria-hidden />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}

function AiModeBadge() {
  const { me } = useSession();
  const { t } = useI18n();
  if (!me) return null;
  const offline = me.ai_mode.startsWith("offline");
  return (
    <span
      title={offline ? t.ai.offlineHint : undefined}
      className={cx(
        "hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset sm:inline-flex",
        offline ? "bg-warn-soft text-warn ring-warn/25" : "bg-ai-soft text-ai ring-ai-line",
      )}
    >
      <span className={cx("h-1.5 w-1.5 rounded-full", offline ? "bg-warn" : "bg-ai")} aria-hidden />
      {offline ? t.ai.offlineMode : `${t.ai.liveMode}: ${me.ai_mode.replace("llm:", "")}`}
    </span>
  );
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const { me } = useSession();
  const { t, locale, setLocale } = useI18n();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const saved = (localStorage.getItem("if_theme") as "light" | "dark") ?? "light";
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
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-bg/90 px-4 backdrop-blur-sm lg:px-6">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu} aria-label="Menu">
        <Menu className="h-5 w-5" />
      </Button>
      <div className="min-w-0 flex-1 truncate text-sm text-ink-2">
        {me && <span className="font-medium text-ink">{locale === "en" && me.organization.name_en ? me.organization.name_en : me.organization.name}</span>}
      </div>
      <AiModeBadge />
      <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")} aria-label={t.common.language}>
        <Languages className="h-4 w-4" aria-hidden /> {locale === "he" ? "EN" : "עב"}
      </Button>
      <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={t.common.theme}>
        {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
      </Button>
      {me && (
        <div className="hidden items-center gap-2 border-s border-line ps-3 md:flex">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink" aria-hidden>
            {me.user.full_name.split(" ").map((p) => p[0]).join("").slice(0, 2)}
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-medium text-ink">{me.user.full_name}</span>
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
  const [open, setOpen] = useState(false);
  const path = usePathname();
  useEffect(() => setOpen(false), [path]);
  return (
    <SessionProvider>
      <LiveEvents />
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-e border-line bg-rail lg:block">
          <Sidebar />
        </aside>
        {open && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
            <div className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} />
            <aside className="absolute inset-y-0 start-0 w-64 bg-rail shadow-pop">
              <Button variant="ghost" size="icon" className="absolute end-2 top-4" onClick={() => setOpen(false)} aria-label="Close">
                <X className="h-5 w-5" />
              </Button>
              <Sidebar onNavigate={() => setOpen(false)} />
            </aside>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onMenu={() => setOpen(true)} />
          <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-6 lg:px-6">{children}</main>
        </div>
      </div>
    </SessionProvider>
  );
}

export function PageHeader({ title, sub, actions, back }: {
  title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode; back?: { href: string; label: string };
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {back && (
          <Link href={back.href} className="mb-1 inline-flex items-center gap-1 text-sm text-ink-3 hover:text-accent">
            <ArrowLeft className="h-3.5 w-3.5 rtl:rotate-180" aria-hidden /> {back.label}
          </Link>
        )}
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {sub && <p className="mt-1 text-base text-ink-2">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
