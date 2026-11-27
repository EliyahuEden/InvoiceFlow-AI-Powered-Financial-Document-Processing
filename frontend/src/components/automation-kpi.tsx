"use client";

import { Zap } from "lucide-react";
import Link from "next/link";
import { cx, Skeleton } from "@/components/ui";
import { hoursText, percent, type AutomationKpi } from "@/lib/auto-approval";
import { useI18n } from "@/lib/i18n";

/** Dashboard card: the share of invoices that skipped review under the auto-approval policy, and an estimate of the
 *  review time that saved. The estimate rests on a stated per-invoice assumption, shown beside it, never hidden. */
export function AutomationKpiCard({ kpi, enabled }: { kpi: AutomationKpi | undefined; enabled?: boolean }) {
  const { t, locale } = useI18n();
  const a = t.autoApproval;
  const rate = kpi ? percent(kpi.touchless_rate, locale) : null;
  const active = !!kpi && kpi.auto_approved > 0;
  return (
    <Link href="/settings#autoApproval" data-testid="automation-kpi"
      className={cx("command-metric group flex items-center justify-between gap-4 bg-gradient-to-l to-surface transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-pop rtl:bg-gradient-to-r",
        active ? "from-ok-soft/90" : "from-surface")}>
      <div className="min-w-0">
        <p className="text-md font-bold text-ink">{a.kpiTitle}</p>
        <div className={cx("mt-1 text-figure font-extrabold num", active ? "text-ok" : "text-ink")}>
          {!kpi ? <Skeleton className="h-8 w-16" /> : <bdi>{rate ?? "—"}</bdi>}
        </div>
        {kpi && <p className="mt-0.5 text-sm text-ink-3">
          {kpi.processed === 0 ? a.kpiNone : a.kpiSub.replace("{auto}", String(kpi.auto_approved)).replace("{processed}", String(kpi.processed)).replace("{n}", String(kpi.window_days))}
        </p>}
        {kpi && kpi.auto_approved > 0 && <p className="mt-1 text-sm font-semibold text-ink-2">
          {a.hoursSaved.replace("{h}", hoursText(kpi.hours_saved, locale))}
          <span className="block text-xs font-normal text-ink-3">{a.assumption.replace("{m}", String(kpi.minutes_per_invoice))}</span>
        </p>}
        {kpi && enabled === false && kpi.auto_approved === 0 && <p className="mt-1 text-xs text-ink-3">{a.kpiOff} {a.kpiSetUp}</p>}
      </div>
      <span className={cx("grid h-12 w-12 shrink-0 place-items-center rounded-full shadow-[inset_0_1px_0_rgb(255_255_255/.9)]", active ? "bg-surface/80 text-ok" : "bg-sunken text-ink-3")}>
        <Zap className="h-5 w-5" aria-hidden />
      </span>
    </Link>
  );
}
