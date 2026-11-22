"use client";

// Plain HTML/CSS charts, kept apart from charts.tsx so pages that only need them do not load Recharts.

/**
 * Single-series magnitude by category as an HTML bar list: native RTL, direct labels,
 * thin bars with rounded data-ends, value in text ink. Hover shows the exact value.
 */
export function BarList({ items, format, max, color = "var(--series-1)" }: {
  items: { label: string; value: number; hint?: string }[]; format?: (v: number) => string; max?: number; color?: string;
}) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.label} className="group grid grid-cols-[minmax(0,1fr)_minmax(0,1.65fr)_3.5rem] items-center gap-3" title={i.hint ?? `${i.label}: ${format ? format(i.value) : i.value}`}>
          <span dir="auto" className="break-words text-sm text-ink-2 [overflow-wrap:anywhere]">{i.label}</span>
          <span className="relative h-3 overflow-hidden rounded-full bg-sunken">
            <span className="absolute inset-y-0 start-0 rounded-full transition-[filter] group-hover:brightness-110"
              style={{ width: `${Math.max(0, Math.min(100, (i.value / top) * 100))}%`, background: color }} />
          </span>
          <span className="text-end text-sm font-medium text-ink num">{format ? format(i.value) : i.value}</span>
        </li>
      ))}
    </ul>
  );
}

/** Proportional strip for a status mix; each segment is labelled (never colour alone). */
export function StatusStrip({ items }: { items: { key: string; label: string; value: number; tone: string }[] }) {
  const total = items.reduce((a, b) => a + b.value, 0) || 1;
  const toneBg: Record<string, string> = {
    ok: "bg-ok", accent: "bg-accent", warn: "bg-warn", danger: "bg-danger", info: "bg-info", neutral: "bg-line-strong",
  };
  return (
    <div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded-full" role="img"
        aria-label={items.map((i) => `${i.label}: ${i.value}`).join(", ")}>
        {items.filter((i) => i.value > 0).map((i) => (
          <div key={i.key} className={toneBg[i.tone] ?? "bg-line-strong"} style={{ width: `${(i.value / total) * 100}%` }}
            title={`${i.label}: ${i.value}`} />
        ))}
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
        {items.map((i) => (
          <li key={i.key} className="flex items-center gap-2 text-sm">
            <span className={`h-2.5 w-2.5 rounded-sm ${toneBg[i.tone] ?? "bg-line-strong"}`} aria-hidden />
            <span className="truncate text-ink-2">{i.label}</span>
            <span className="ms-auto font-medium text-ink num">{i.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
