"use client";

import dynamic from "next/dynamic";
import { confirmDraftNavigation } from "@/lib/use-unsaved-work";

import * as Tooltip from "@radix-ui/react-tooltip";
import { ArrowLeft, Languages, LayoutGrid, LogOut, MessageSquareText, Moon, Search, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useLiveEvents } from "@/lib/events";
import { isActive, isTyping, useNav } from "@/lib/nav";
import { setTheme as applyTheme, type Theme } from "@/lib/theme";
import { Kbd } from "./kbd";
import { CopilotPanel } from "./copilot";
import { ReviewNextButton } from "./review-next";
import { SessionProvider, useSession } from "./session";
import { Button, cx } from "./ui";
import { LogoMark } from "./logo";
import { label } from "@/lib/i18n/label";

// The command palette (cmdk) and the shortcuts dialog load only when opened; the shell owns the hotkeys.
const CommandPalette = dynamic(() => import("./command-palette").then((m) => m.CommandPalette), { ssr: false });
const ShortcutsDialog = dynamic(() => import("./shortcuts").then((m) => m.ShortcutsDialog), { ssr: false });

/** Labelled sidebar for wide screens: the business, every permitted destination by group, and the signed-in user. */
function Sidebar() {
  const nav = useNav();
  const path = usePathname();
  const { t } = useI18n();
  const { me } = useSession();
  const logout = async () => {
    await api.post("/api/auth/logout");
    window.location.href = "/login";
  };
  return (
    <div className="shell-glass flex h-full flex-col border-e border-line">
      <Link href="/" className="flex h-16 items-center gap-2.5 px-5 text-xl font-extrabold tracking-tight text-rail-ink" aria-label={t.app.name}>
        <LogoMark className="h-8 w-8 shrink-0" />{t.app.name}
      </Link>
      <div className="mx-3 mb-2 flex h-10 items-center rounded-xl border border-line bg-surface/70 px-2">
        {me && (me.organizations?.length ?? 0) > 1 ? (
          <select aria-label={t.common.organization} value={me.organization.id} dir="auto"
            onChange={async (e) => {
              await api.post("/api/auth/switch-organization", { organization_id: e.target.value });
              window.location.assign("/");  // a full reload: no data or drafts carry over between businesses
            }}
            className="h-8 min-w-0 flex-1 truncate rounded-lg border border-transparent bg-transparent px-1.5 text-base font-semibold text-rail-ink focus:border-accent/70 focus:outline-none">
            {me.organizations.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        ) : (
          <span className="min-w-0 truncate px-1.5 text-base font-semibold text-rail-ink" dir="auto">{me?.organization.name ?? t.app.name}</span>
        )}
      </div>
      <nav aria-label={t.nav.navigation} className="flex-1 overflow-y-auto px-3 pb-3 pt-2">
        {nav.map((g, gi) => (
          <div key={g.group} className={cx(gi > 0 && "mt-5")}>
            <p className="px-3 pb-1.5 text-xs font-semibold text-rail-ink-2">{g.group}</p>
            <ul className="space-y-0.5">
              {g.items.map((item) => {
                const active = isActive(path, item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link href={item.href} aria-current={active ? "page" : undefined}
                      className={cx("command-nav-link group flex h-11 items-center gap-3 rounded-xl px-3 text-md",
                        active ? "bg-rail-active font-bold text-accent-ink shadow-[inset_0_1px_0_rgb(255_255_255/.6)]" : "font-semibold text-rail-ink-2 hover:bg-rail-active/55 hover:text-rail-ink")}>
                      <Icon className={cx("h-[18px] w-[18px] shrink-0", active ? "text-accent" : "text-rail-ink-2 group-hover:text-rail-ink")} aria-hidden />
                      <span className="truncate">{item.label}</span>
                      {item.key && <kbd className="ms-auto hidden font-mono text-2xs font-normal text-rail-ink-2/70 group-hover:inline" aria-hidden>G {item.key.toUpperCase()}</kbd>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      {me && (
        <div className="m-3 flex items-center gap-2.5 rounded-xl border border-line bg-surface/70 px-3 py-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-bold text-accent-ink" aria-hidden>
            {me.user.full_name.split(" ").map((p) => p[0]).join("").slice(0, 2)}
          </span>
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block truncate text-base font-bold text-rail-ink">{me.user.full_name}</span>
            <span className="block truncate text-2xs text-rail-ink-2">{label(t.roles, me.role)}</span>
          </span>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={logout} aria-label={t.common.logout} title={t.common.logout}>
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
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
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-label={t.nav.allDestinations}
        onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}
        className="absolute inset-y-2 start-2 flex w-[min(19rem,calc(100vw-1rem))] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-pop animate-rise">
        <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
          <span className="flex items-center gap-2.5">
            <LogoMark className="h-8 w-8" />
            <span className="leading-tight">
              <span className="block text-base font-medium text-ink">{t.app.name}</span>
              <span className="block text-xs text-ink-3">{t.app.tagline}</span>
            </span>
          </span>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t.common.close}><X className="h-5 w-5" /></Button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-2 py-3">
          {nav.map((g) => (
            <div key={g.group}>
              <p className="px-2 pb-1 text-2xs font-medium text-ink-3">{g.group}</p>
              <ul className="space-y-0.5">
                {g.items.map((item) => {
                  const active = isActive(path, item.href);
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link href={item.href} onClick={onClose} aria-current={active ? "page" : undefined}
                        className={cx("command-nav-link flex h-9 items-center gap-2.5 rounded-md px-2 text-base",
                          active ? "bg-rail-active font-medium text-ink" : "text-ink-2 hover:bg-rail-active/60 hover:text-ink")}>
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
        {/* on phones the top bar has no room for sign-out, so it lives here */}
        <div className="border-t border-line p-2 sm:hidden">
          <button type="button" onClick={async () => { await api.post("/api/auth/logout"); window.location.href = "/login"; }}
            className="command-nav-link flex h-10 w-full items-center gap-2.5 rounded-md px-2 text-base text-ink-2 hover:bg-rail-active/60 hover:text-ink">
            <LogOut className="h-4 w-4 shrink-0 text-ink-3 rtl:-scale-x-100" aria-hidden />{t.common.logout}
          </button>
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
      className={cx("inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-xs font-semibold",
        offline ? "border-warn/25 bg-warn-soft text-warn" : "border-line bg-surface/80 text-ink-2")}>
      <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", offline ? "bg-warn" : "bg-ok shadow-[0_0_0_3px_rgb(var(--ok)/.18)]")} aria-hidden />
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

function TopBar({ onMenu, onSearch, onCopilot }: { onMenu: () => void; onSearch: () => void; onCopilot: () => void }) {
  const { me, can } = useSession();
  const { t, locale, setLocale } = useI18n();
  const current = useCurrentLabel();
  const path = usePathname();
  const [theme, setTheme] = useState<Theme>("light");
  const [mod, setMod] = useState("Ctrl");
  useEffect(() => {
    let saved: Theme = "light";
    try { saved = (localStorage.getItem("if_theme") as Theme) ?? "light"; } catch { /* storage unavailable */ }
    setTheme(saved);
    document.documentElement.dataset.theme = saved;
    if (/Mac|iPhone|iPad/.test(navigator.platform)) setMod("⌘");
    const onTheme = (e: Event) => setTheme((e as CustomEvent<Theme>).detail);
    window.addEventListener("if:theme", onTheme);
    return () => window.removeEventListener("if:theme", onTheme);
  }, []);
  const toggleTheme = () => applyTheme(theme === "light" ? "dark" : "light");
  const logout = async () => {
    await api.post("/api/auth/logout");
    window.location.href = "/login";
  };
  return (
    <header className="sticky top-0 z-20 flex h-16 bg-bg/95 backdrop-blur-xl items-center gap-2 border-b border-line px-3 sm:gap-2.5 lg:px-8">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu} aria-label={t.nav.allDestinations}>
        <LayoutGrid className="h-5 w-5" />
      </Button>
      <div className="flex min-w-0 flex-1 items-baseline gap-2 truncate">
        <span className="hidden text-base text-ink-3 sm:inline lg:hidden">{t.app.name}</span>
        {current && <><span className="hidden text-ink-3 sm:inline lg:hidden" aria-hidden>/</span>
          <span className="truncate text-base font-medium text-ink">{current}</span></>}
      </div>
      {/* named by its visible text (including the shortcut), so speech control can activate what it shows */}
      <button type="button" onClick={onSearch}
        className="shell-glass hidden h-10 min-w-[18rem] items-center gap-2.5 rounded-full border border-line pe-2 ps-4 text-base text-ink-3 shadow-[0_1px_2px_rgb(34_38_92/.05)] transition-colors hover:border-line-strong/60 hover:text-ink-2 lg:flex">
        <Search className="h-4 w-4" aria-hidden />
        <span className="flex-1 text-start">{t.palette.trigger}</span>
        <span className="flex gap-1" dir="ltr"><Kbd>{mod}</Kbd><Kbd>K</Kbd></span>
      </button>
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onSearch} aria-label={t.palette.trigger}><Search className="h-4 w-4" /></Button>
      <Button variant="ai" size="sm" onClick={onCopilot} aria-label={t.copilot.open} className="gap-1.5">
        <MessageSquareText className="h-4 w-4" aria-hidden /><span className="hidden sm:inline">{t.copilot.open}</span>
      </Button>
      <AiModeBadge />
      {/* the dashboard and the workspace carry their own primary review action; elsewhere it stays secondary so the page keeps one dark primary */}
      {me && can("exception:decide") && path !== "/" && !path.startsWith("/exceptions") &&
        <ReviewNextButton size="sm" variant="secondary" className="hidden xl:inline-flex" />}
      <Button variant="ghost" size="sm" onClick={() => setLocale(locale === "he" ? "en" : "he")}>
        <Languages className="h-4 w-4" aria-hidden /><span className="sr-only">{t.common.language}: </span>
        <span lang={locale === "he" ? "en" : "he"}>{locale === "he" ? "EN" : "עב"}</span>
      </Button>
      <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={t.common.theme}>
        {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
      </Button>
      <Button variant="ghost" size="icon" className="hidden sm:inline-flex lg:hidden" onClick={logout} aria-label={t.common.logout} title={t.common.logout}>
        <LogOut className="h-4 w-4" />
      </Button>
    </header>
  );
}

function LiveEvents() {
  useLiveEvents();
  return null;
}

/** Global keys: Ctrl/⌘+K palette, "?" help, "g" + letter to navigate. Ignored while typing;
 *  no financial decision is ever bound to a key here. */
function useGlobalKeys(nav: ReturnType<typeof useNav>, openPalette: () => void, openHelp: () => void,
                       openCopilot: () => void = () => {}) {
  const router = useRouter();
  useEffect(() => {
    let pendingG = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
      if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      if (e.key === "?") { e.preventDefault(); openHelp(); return; }
      if (e.key === "/") { e.preventDefault(); openCopilot(); return; }
      if (pendingG) {
        pendingG = false;
        const item = nav.flatMap((g) => g.items).find((i) => i.key === e.key.toLowerCase());
        if (item) { e.preventDefault(); if (confirmDraftNavigation()) router.push(item.href); }
        return;
      }
      if (e.key.toLowerCase() === "g") { pendingG = true; clearTimeout(timer); timer = setTimeout(() => { pendingG = false; }, 1200); }
    };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); clearTimeout(timer); };
  }, [nav, openPalette, openHelp, openCopilot, router]);
}

function KeyedShell({ children, open, setOpen }: { children: React.ReactNode; open: boolean; setOpen: (v: boolean) => void }) {
  const nav = useNav();
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [copilot, setCopilot] = useState(false);
  useGlobalKeys(nav, () => setPalette(true), () => setHelp(true), () => setCopilot(true));
  // fetch the on-demand dialogs once the page is idle, so the first Ctrl+K opens without a delay
  useEffect(() => {
    const warm = () => { void import("./command-palette"); void import("./shortcuts"); };
    if (typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(warm, { timeout: 4000 });
      return () => window.cancelIdleCallback(id);
    }
    const t = setTimeout(warm, 2000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-[256px] shrink-0 lg:block">
        <Sidebar />
      </aside>
      {open && <NavDrawer onClose={() => setOpen(false)} />}
      {palette && <CommandPalette open onOpenChange={setPalette} onAskCopilot={() => setCopilot(true)} />}
      <CopilotPanel open={copilot} onOpenChange={setCopilot} />
      {help && <ShortcutsDialog open onOpenChange={setHelp} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setOpen(true)} onSearch={() => setPalette(true)} onCopilot={() => setCopilot(true)} />
        {children}
      </div>
    </div>
  );
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
        <KeyedShell open={open} setOpen={setOpen}>
          <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1520px] flex-1 px-4 pb-14 pt-2 focus:outline-none sm:px-6 lg:px-8">{children}</main>
        </KeyedShell>
      </Tooltip.Provider>
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
          <Link href={back.href} className="mb-2 inline-flex items-center gap-1 text-sm text-ink-3 hover:text-ink">
            <ArrowLeft className="h-3.5 w-3.5 ltr:rotate-180" aria-hidden /> {back.label}
          </Link>
        )}
        <h1 className="text-3xl font-extrabold tracking-tight text-ink">{title}</h1>
        {sub && <p className="mt-1 text-md text-ink-3">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
