"use client";

import { ChevronDown, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { Button, cx } from "./ui";

/*
  The shared anatomy of a records page (queue, inbox, suppliers, orders, runs, audit):
  a header with the page's real totals, one filter bar, the list, and a detail panel beside it.
  Pages compose these; none of them fetches data.
*/

/** Title, one line of purpose, the page's main action, and (on wide screens, beside it) its stat tiles.
 *  Without stat tiles the actions sit at the end of the title row. */
export function PageHeader({ title, sub, actions, stats, className }: {
  title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode; stats?: React.ReactNode; className?: string;
}) {
  if (!stats) return (
    <header className={cx("flex min-w-0 flex-wrap items-end justify-between gap-4 pt-1", className)}>
      <div className="min-w-0">
        <h1 className="text-[2.125rem] font-extrabold leading-tight tracking-[-0.02em] text-ink">{title}</h1>
        {sub && <p className="mt-1 max-w-[52ch] text-lg text-ink-3">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
  return (
    <header className={cx("grid min-w-0 gap-5 pt-1", stats && "xl:grid-cols-[minmax(17rem,0.75fr)_minmax(0,1.6fr)] xl:items-center", className)}>
      <div className="min-w-0">
        <h1 className="text-[2.125rem] font-extrabold leading-tight tracking-[-0.02em] text-ink">{title}</h1>
        {sub && <p className="mt-1 max-w-[46ch] text-lg text-ink-3">{sub}</p>}
        {actions && <div className="mt-4 flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {stats && <div className="grid min-w-0 grid-cols-2 gap-3 md:grid-cols-3">{stats}</div>}
    </header>
  );
}

type Tone = "neutral" | "danger" | "warn" | "ok" | "accent";
const ICON_TONE: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-3", danger: "bg-danger-soft text-danger", warn: "bg-warn-soft text-warn",
  ok: "bg-ok-soft text-ok", accent: "bg-accent-soft text-accent",
};

/** One real figure. The state colour is earned: pass ``active`` only when the value calls for attention. */
export function StatTile({ icon: Icon, label, value, note, tone = "neutral", active = true, href, className }: {
  icon: React.ElementType; label: string; value: React.ReactNode; note?: React.ReactNode;
  tone?: Tone; active?: boolean; href?: string; className?: string;
}) {
  const body = <>
    <span className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", active ? ICON_TONE[tone] : ICON_TONE.neutral)} aria-hidden>
      <Icon className="h-[18px] w-[18px]" />
    </span>
    <dl className="min-w-0">
      <dt className="text-sm font-semibold text-ink-2">{label}</dt>
      <dd className={cx("mt-0.5 text-[1.625rem] font-extrabold leading-tight tracking-[-0.01em] num", active && tone === "danger" ? "text-danger" : "text-ink")}>{value}</dd>
      {note && <dd className="mt-0.5 text-sm leading-snug text-ink-3">{note}</dd>}
    </dl>
  </>;
  const cls = cx("command-metric flex min-w-0 items-start gap-3", className);
  if (href) return <div className={cx(cls, "relative transition-shadow hover:shadow-pop")}>
    {body}<Link href={href} className="absolute inset-0 rounded-[inherit]" aria-label={label} />
  </div>;
  return <div className={cls}>{body}</div>;
}

/**
 * Search plus compact filters. On phones the filters fold behind one button so the list is reached first.
 * ``active`` counts the filters that narrow the list (not the search), for that button's badge.
 */
export function FilterBar({ search, children, active = 0, onClear, className }: {
  search?: React.ReactNode; children?: React.ReactNode; active?: number; onClear?: () => void; className?: string;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className={cx("flex flex-wrap items-center gap-2", className)}>
      {search && <div className="min-w-[12rem] flex-1 sm:max-w-xs">{search}</div>}
      {children && <Button className="md:hidden" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <SlidersHorizontal className="h-4 w-4" aria-hidden />{t.review.filters}
        {active > 0 && <bdi className="grid h-5 min-w-5 place-items-center rounded-full bg-accent-ink px-1 text-xs text-surface num">{active}</bdi>}
      </Button>}
      {children && <div id={id} className={cx("w-full flex-wrap items-center gap-2 md:flex md:w-auto", open ? "flex" : "hidden")}>{children}</div>}
      {onClear && <Button size="sm" variant="ghost" onClick={onClear}><X className="h-3.5 w-3.5" aria-hidden />{t.review.clearFilters}</Button>}
    </div>
  );
}

/** A native select drawn as a compact "Label: value" chip. The label stays the select's accessible name. */
export function FilterSelect({ label, value, onChange, children, className }: {
  label: string; value: string; onChange: (value: string) => void; children: React.ReactNode; className?: string;
}) {
  const id = useId();
  return (
    <div className={cx("relative inline-flex h-9 min-w-0 items-center rounded-[10px] border bg-surface text-sm shadow-[0_1px_2px_rgb(34_38_92/.04)] transition-colors focus-within:border-accent/70 focus-within:ring-[3px] focus-within:ring-accent/20 hover:border-line-strong/70",
      value ? "border-accent/40 bg-accent-soft/50" : "border-line", className)}>
      <label htmlFor={id} className="whitespace-nowrap ps-3 text-ink-3">{label}:</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}
        className="h-full min-w-0 max-w-[13rem] cursor-pointer appearance-none truncate [field-sizing:content] bg-transparent pe-8 ps-1.5 font-semibold text-ink focus:outline-none">
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute end-2.5 h-3.5 w-3.5 text-ink-3" aria-hidden />
    </div>
  );
}

/** A small count beside a heading. */
export function CountBadge({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cx("inline-grid h-6 min-w-6 place-items-center rounded-full bg-accent-soft px-2 text-xs font-bold text-accent-ink num", className)}>{children}</span>;
}

/**
 * The detail beside a list: what the selected row is and why, with the action that opens it.
 * It is a labelled region (not a dialog): selecting a row never moves focus or traps it.
 */
export function DetailPanel({ title, meta, onClose, closeLabel, children, footer, className }: {
  title: React.ReactNode; meta?: React.ReactNode; onClose?: () => void; closeLabel?: string;
  children: React.ReactNode; footer?: React.ReactNode; className?: string;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} aria-live="polite" className={cx("command-panel flex min-w-0 flex-col", className)}>
      <header className="flex items-start justify-between gap-3 px-5 pb-3 pt-5">
        <div className="min-w-0">
          <h2 id={id} className="text-lg font-bold leading-snug tracking-tight text-ink">{title}</h2>
          {meta && <div className="mt-2">{meta}</div>}
        </div>
        {onClose && <Button variant="ghost" size="icon" className="-me-2 -mt-1 h-8 w-8" onClick={onClose} aria-label={closeLabel}><X className="h-4 w-4" aria-hidden /></Button>}
      </header>
      <div className="min-w-0 flex-1 space-y-4 px-5 pb-5">{children}</div>
      {footer && <footer className="border-t border-line px-5 py-4">{footer}</footer>}
    </section>
  );
}

/** A labelled group inside a detail panel. */
export function DetailSection({ title, children, className }: { title: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <div className={cx("min-w-0", className)}>
    <h3 className="mb-2 text-sm font-bold text-ink-2">{title}</h3>
    {children}
  </div>;
}

/** Status segments above a list: each a toggle with its real count. Exactly one is pressed. */
export function Segments<T extends string>({ value, onChange, options, label, className }: {
  value: T; onChange: (value: T) => void; label: string; className?: string;
  options: { value: T; label: string; count?: number; icon?: React.ElementType; tone?: "neutral" | "danger" | "warn" | "ok" | "accent" }[];
}) {
  return (
    <div role="group" aria-label={label} className={cx("flex flex-wrap gap-2", className)}>
      {options.map((o) => {
        const pressed = value === o.value;
        const Icon = o.icon;
        return <button key={o.value} type="button" aria-pressed={pressed} onClick={() => onChange(o.value)}
          className={cx("inline-flex h-10 items-center gap-2 rounded-xl border px-3.5 text-sm font-semibold transition-colors",
            pressed ? "border-accent/40 bg-accent-soft text-accent-ink shadow-[0_1px_2px_rgb(34_38_92/.06)]" : "border-line bg-surface text-ink-2 hover:bg-sunken")}>
          {Icon && <Icon className={cx("h-4 w-4", !pressed && o.tone && o.count ? ICON_TONE[o.tone].split(" ")[1] : "")} aria-hidden />}
          {o.label}
          {o.count !== undefined && <bdi className={cx("grid h-5 min-w-5 place-items-center rounded-full px-1.5 text-xs num", pressed ? "bg-accent-ink text-surface" : "bg-sunken text-ink-2")}>{o.count}</bdi>}
        </button>;
      })}
    </div>
  );
}

/** True where a list and its detail panel fit side by side (1440px and wider). Elsewhere a row opens its own page. */
export function useWideLayout() {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const m = window.matchMedia("(min-width: 1440px)");
    const on = () => setWide(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return wide;
}
