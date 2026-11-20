"use client";

import { ArrowUpRight, Bot, FileWarning, ShieldCheck, User } from "lucide-react";
import Link from "next/link";
import { BarList, Lines, StatusStrip } from "@/components/charts";
import { PageHeader } from "@/components/shell";
import { Button, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { money, relative } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Dashboard = {
  kpis: { invoices_total: number; open_exceptions: number; amount_at_risk: string; total_value_ils: string;
    auto_match_rate: number | null; awaiting_approval: number; approved: number; median_processing_seconds: number | null };
  status_counts: Record<string, number>;
  discrepancy_types: { type: string; count: number }[];
  exceptions_by_supplier: { supplier: string; count: number }[];
  daily: { date: string; received: number; exceptions: number }[];
  recent_activity: { id: string; created_at: string; action: string; actor_type: string; actor_label: string | null;
    entity_type: string; entity_id: string | null }[];
};

const STATUS_ORDER: [string, string][] = [
  ["approved", "ok"], ["reconciled", "accent"], ["needs_review", "warn"], ["on_hold", "warn"], ["exception", "danger"],
  ["processing", "info"], ["failed", "danger"], ["rejected", "neutral"],
];

function Metric({ label, value, foot, href }: { label: string; value: React.ReactNode; foot?: React.ReactNode; href?: string }) {
  const inner = (
    <>
      <p className="text-sm text-ink-2">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold text-ink num">{value}</p>
      {foot && <p className="mt-1 text-xs text-ink-3">{foot}</p>}
    </>
  );
  return href ? (
    <Link href={href} className="group block px-4 py-3.5 transition-colors hover:bg-sunken/60">{inner}</Link>
  ) : (
    <div className="px-4 py-3.5">{inner}</div>
  );
}

export default function OverviewPage() {
  const { t, locale } = useI18n();
  const { data, error, mutate } = useApi<Dashboard>("/api/dashboard", { refreshInterval: 30000 });
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  const k = data?.kpis;
  const findingLabel = (ty: string) => (t.finding as Record<string, string>)[ty] ?? ty;
  return (
    <div className="space-y-5">
      <PageHeader
        title={t.overview.title}
        actions={
          <Button asChild variant="primary"><Link href="/exceptions">{t.overview.queueCta}<ArrowUpRight className="h-4 w-4 rtl:-scale-x-100" /></Link></Button>
        }
      />
      <Panel className="grid grid-cols-2 divide-line md:grid-cols-3 xl:grid-cols-6 [&>*]:border-line max-md:[&>*:nth-child(odd)]:border-e md:[&>*:not(:last-child)]:border-e max-xl:[&>*]:border-b">
        {!k ? Array.from({ length: 6 }).map((_, i) => <div key={i} className="space-y-2 px-4 py-4"><Skeleton className="w-24" /><Skeleton className="h-7 w-16" /></div>) : (
          <>
            <Metric label={t.overview.invoices} value={k.invoices_total} href="/invoices" foot={<span className="ltr">{money(k.total_value_ils, "ILS")}</span>} />
            <Metric label={t.overview.openExceptions} value={k.open_exceptions} href="/exceptions" />
            <Metric label={t.overview.atRisk} value={<span className="ltr text-danger">{money(k.amount_at_risk, "ILS")}</span>} foot={t.overview.atRiskHint} />
            <Metric label={t.overview.autoMatch} value={k.auto_match_rate === null ? "—" : `${Math.round(k.auto_match_rate * 100)}%`} />
            <Metric label={t.overview.awaitingApproval} value={k.awaiting_approval} href="/exceptions" />
            <Metric label={t.overview.medianProcessing} value={k.median_processing_seconds === null ? "—" : `${k.median_processing_seconds}${t.overview.seconds}`} />
          </>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Panel>
          <PanelHeader title={t.overview.discrepancyTypes} />
          <div className="p-4">
            {!data ? <Skeleton className="h-56 w-full" /> : data.discrepancy_types.length === 0 ? (
              <p className="py-16 text-center text-sm text-ink-3">{t.recon.allClear}</p>
            ) : (
              <BarList items={data.discrepancy_types.map((d) => ({ label: findingLabel(d.type), value: d.count }))} />
            )}
          </div>
        </Panel>
        <Panel>
          <PanelHeader title={t.overview.statusMix} />
          <div className="p-4">
            {!data ? <Skeleton className="h-24 w-full" /> : (
              <StatusStrip items={STATUS_ORDER.map(([key, tone]) => ({
                key, tone, label: (t.status as Record<string, string>)[key] ?? key, value: data.status_counts[key] ?? 0,
              }))} />
            )}
          </div>
          <div className="border-t border-line p-4">
            <h3 className="mb-2 text-sm font-semibold text-ink">{t.overview.bySupplier}</h3>
            <ul className="space-y-1.5">
              {data?.exceptions_by_supplier.map((s) => (
                <li key={s.supplier} className="flex items-center justify-between text-sm">
                  <span dir="auto" className="truncate text-ink-2">{s.supplier}</span>
                  <span className="font-medium num">{s.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Panel>
          <PanelHeader title={t.overview.volume} />
          <div className="p-4">
            {!data ? <Skeleton className="h-52 w-full" /> : (
              <Lines xKey="date" data={data.daily.map((d) => ({ ...d, date: d.date.slice(5) }))}
                series={[{ key: "received", label: t.overview.invoices }, { key: "exceptions", label: t.status.exception }]} />
            )}
          </div>
        </Panel>
        <Panel>
          <PanelHeader title={t.overview.activity} />
          <ul className="divide-y divide-line">
            {data?.recent_activity.map((a) => {
              const Icon = a.actor_type === "agent" ? Bot : a.actor_type === "system" ? ShieldCheck : a.action.includes("exception") ? FileWarning : User;
              return (
                <li key={a.id} className="flex items-center gap-3 px-4 py-2">
                  <Icon className={`h-4 w-4 shrink-0 ${a.actor_type === "agent" ? "text-ai" : "text-ink-3"}`} aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-sm">
                    <span className="font-mono text-xs text-ink-2">{a.action}</span>
                    <span className="text-ink-3"> · {a.actor_label ?? a.actor_type}</span>
                  </span>
                  <span className="shrink-0 text-xs text-ink-3">{relative(a.created_at, locale)}</span>
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
