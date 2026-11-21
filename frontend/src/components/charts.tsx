"use client";

/*
  Chart conventions (dataviz method):
  - categorical hues in fixed slot order (--series-1..4), never cycled; colour follows the entity
  - single-series charts use one hue; status is never encoded by colour alone
  - thin bars with 4px rounded data-ends, 2px gaps, recessive grid, one y-axis
  - every chart has a hover tooltip; >=2 series always show a legend
*/
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { useI18n } from "@/lib/i18n";

export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

const axisProps = {
  stroke: "var(--chart-axis)",
  tick: { fill: "var(--chart-axis)", fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: "var(--chart-grid)" },
};

function ChartTooltip({ active, payload, label, format }: {
  active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string; format?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-pop">
      {label !== undefined && <p className="mb-1 font-medium text-ink">{label}</p>}
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 text-ink-2">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} aria-hidden />
          <span>{p.name}</span>
          <span className="ms-auto ps-3 font-medium text-ink num">{format ? format(p.value) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

export type SeriesDef = { key: string; label: string };

export function Bars({ data, xKey, series, height = 240, layout = "horizontal", format, domain, xWidth = 120 }: {
  data: Record<string, unknown>[]; xKey: string; series: SeriesDef[]; height?: number;
  layout?: "horizontal" | "vertical"; format?: (v: number) => string; domain?: [number, number]; xWidth?: number;
}) {
  const { dir } = useI18n();
  const vertical = layout === "vertical";
  return (
    <div style={{ height }} dir="ltr">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout={layout} margin={{ top: 8, right: 12, bottom: 4, left: 4 }} barGap={2} barCategoryGap="28%">
          <CartesianGrid stroke="var(--chart-grid)" vertical={vertical} horizontal={!vertical} />
          {vertical ? (
            <>
              <XAxis type="number" {...axisProps} domain={domain} tickFormatter={format} reversed={dir === "rtl"} />
              <YAxis type="category" dataKey={xKey} {...axisProps} width={xWidth} orientation={dir === "rtl" ? "right" : "left"} />
            </>
          ) : (
            <>
              <XAxis dataKey={xKey} {...axisProps} reversed={dir === "rtl"} />
              <YAxis {...axisProps} width={44} domain={domain} tickFormatter={format} orientation={dir === "rtl" ? "right" : "left"} />
            </>
          )}
          <Tooltip cursor={{ fill: "rgb(var(--sunken))" }} content={<ChartTooltip format={format} />} />
          {series.length > 1 && <Legend iconType="square" iconSize={9} wrapperStyle={{ fontSize: 12, color: "var(--chart-axis)" }} />}
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={SERIES[i % SERIES.length]} maxBarSize={vertical ? 14 : 28}
              radius={vertical ? (dir === "rtl" ? [4, 0, 0, 4] : [0, 4, 4, 0]) : [4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Lines({ data, xKey, series, height = 220 }: {
  data: Record<string, unknown>[]; xKey: string; series: SeriesDef[]; height?: number;
}) {
  const { dir } = useI18n();
  return (
    <div style={{ height }} dir="ltr">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey={xKey} {...axisProps} reversed={dir === "rtl"} />
          <YAxis {...axisProps} width={36} allowDecimals={false} orientation={dir === "rtl" ? "right" : "left"} />
          <Tooltip cursor={{ stroke: "var(--chart-axis)", strokeDasharray: "3 3" }} content={<ChartTooltip />} />
          {series.length > 1 && <Legend iconType="plainline" iconSize={12} wrapperStyle={{ fontSize: 12, color: "var(--chart-axis)" }} />}
          {series.map((s, i) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={SERIES[i]} strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, stroke: "rgb(var(--surface))", fill: SERIES[i] }} activeDot={{ r: 5 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

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
