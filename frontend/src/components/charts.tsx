"use client";

/*
  Chart conventions (dataviz method):
  - categorical hues in fixed slot order (--series-1..4), never cycled; colour follows the entity
  - single-series charts use one hue; status is never encoded by colour alone
  - thin bars with 4px rounded data-ends, 2px gaps, recessive grid, one y-axis
  - every chart has a hover tooltip; >=2 series always show a legend
*/
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { useI18n } from "@/lib/i18n";

export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

/** Recharts animates its marks regardless of the visitor's setting; honour reduced motion ourselves. */
function animate(): boolean {
  return typeof window === "undefined" || !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

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

export function Bars({ data, xKey, series, height = 240, layout = "horizontal", format, domain, xWidth = 120, categoryGap = "28%" }: {
  data: Record<string, unknown>[]; xKey: string; series: SeriesDef[]; height?: number;
  layout?: "horizontal" | "vertical"; format?: (v: number) => string; domain?: [number, number]; xWidth?: number;
  categoryGap?: string;
}) {
  const { dir } = useI18n();
  const vertical = layout === "vertical";
  return (
    <div style={{ height }} dir="ltr">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout={layout} margin={{ top: 8, right: 12, bottom: 4, left: 4 }} barGap={1} barCategoryGap={categoryGap}>
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
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={SERIES[i % SERIES.length]} isAnimationActive={animate()} maxBarSize={vertical ? 14 : 28}
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
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} isAnimationActive={animate()} stroke={SERIES[i]} strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, stroke: "rgb(var(--surface))", fill: SERIES[i] }} activeDot={{ r: 5 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** The first series as a soft filled area, the rest as lines over it (e.g. invoices received vs exceptions per day). */
export function Areas({ data, xKey, series, height = 200 }: {
  data: Record<string, unknown>[]; xKey: string; series: SeriesDef[]; height?: number;
}) {
  const { dir } = useI18n();
  const [first, ...rest] = series;
  return (
    <div style={{ height }} dir="ltr">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="area-fill-1" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.32} />
              <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey={xKey} {...axisProps} reversed={dir === "rtl"} minTickGap={24} />
          <YAxis {...axisProps} width={30} allowDecimals={false} orientation={dir === "rtl" ? "right" : "left"} />
          <Tooltip cursor={{ stroke: "var(--chart-axis)", strokeDasharray: "3 3" }} content={<ChartTooltip />} />
          {series.length > 1 && <Legend iconType="plainline" iconSize={12} wrapperStyle={{ fontSize: 12, color: "var(--chart-axis)" }} />}
          {first && <Area type="monotone" dataKey={first.key} name={first.label} isAnimationActive={animate()} stroke="var(--series-1)" strokeWidth={2.25}
            fill="url(#area-fill-1)" activeDot={{ r: 5, strokeWidth: 2, stroke: "rgb(var(--surface))" }} />}
          {rest.map((s, i) => (
            <Area key={s.key} type="monotone" dataKey={s.key} name={s.label} isAnimationActive={animate()} stroke={SERIES[i + 1]} strokeWidth={2}
              fill="transparent" activeDot={{ r: 4 }} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
