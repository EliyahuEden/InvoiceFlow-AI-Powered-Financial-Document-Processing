"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { AlertTriangle, ArrowLeftRight, ArrowRight, CalendarClock, CheckCheck, FileText, Layers, TrendingUp } from "lucide-react";
import { ReviewQueue } from "@/components/review-queue";
import { ExportMenu } from "@/components/export-menu";
import { PaymentReminders } from "@/components/invoice-payment";
import { ReviewNextButton } from "@/components/review-next";
import { useSession } from "@/components/session";
import { Button, cx, ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { label } from "@/lib/i18n/label";
import type { ReviewSummary } from "@/lib/types";

const Bars = dynamic(() => import("@/components/charts").then((m) => m.Bars), {
  ssr: false, loading: () => <Skeleton className="h-[170px] w-full" />,
});

/** A ranked list with thin proportional bars: the share of each row at a glance, the exact count beside it. */
function RankedList({ rows, unit }: { rows: { key: string; label: React.ReactNode; count: number }[]; unit: string }) {
  const top = Math.max(1, ...rows.map((r) => r.count));
  return <ol className="space-y-3 px-5 py-4">
    {rows.map((r) => <li key={r.key}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate text-base font-medium text-ink">{r.label}</span>
        <span className="shrink-0 text-sm text-ink-3"><bdi className="text-base font-extrabold text-ink num">{r.count}</bdi> {unit}</span>
      </div>
      <div className="mt-1.5 h-1 rounded-full bg-sunken" aria-hidden>
        <div className="h-full rounded-full bg-accent/55" style={{ width: `${Math.max(4, (r.count / top) * 100)}%` }} />
      </div>
    </li>)}
  </ol>;
}

type Insights = {
  kpis: { open_exceptions: number };
  daily: { date: string; received: number; exceptions: number }[];
  discrepancy_types: { type: string; count: number }[];
  exceptions_by_supplier: { supplier: string; count: number }[];
};

type DayPart = "morning" | "afternoon" | "evening";
function greetingKey(): DayPart {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}
/** The visitor's local part of day, known only after mount: the server's clock (UTC in the container) must not decide
 *  it, or the first client render would not match the server HTML. */
function useDayPart(): DayPart | null {
  const [part, setPart] = useState<DayPart | null>(null);
  useEffect(() => setPart(greetingKey()), []);
  return part;
}

/** A KPI card: label, the figure, what it breaks down into, and its icon. The state colour turns on only when the count
 *  is above zero (``active``): a zero overdue count is good news, not an alarm. */
function Kpi({ href, label, value, sub, tone, active, icon: Icon }: {
  href: string; label: string; value: React.ReactNode; sub?: React.ReactNode;
  tone: "danger" | "accent" | "ok"; active: boolean; icon: React.ElementType;
}) {
  const tint = active ? { danger: "from-danger-soft/90", accent: "from-accent-soft/90", ok: "from-ok-soft/90" }[tone] : "from-surface";
  const ink = active ? { danger: "text-danger", accent: "text-accent", ok: "text-ok" }[tone] : "text-ink";
  return (
    <Link href={href} className={cx("command-metric group flex items-center justify-between gap-4 bg-gradient-to-l to-surface transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-pop rtl:bg-gradient-to-r", tint)}>
      <div className="min-w-0">
        <p className="text-md font-bold text-ink">{label}</p>
        <div className={cx("mt-1 text-figure font-extrabold num", ink)}>{value}</div>
        {sub && <p className="mt-0.5 text-sm text-ink-3">{sub}</p>}
      </div>
      <span className={cx("grid h-12 w-12 shrink-0 place-items-center rounded-full shadow-[inset_0_1px_0_rgb(255_255_255/.9)]", active ? cx("bg-surface/80", ink) : "bg-sunken text-ink-3")}>
        <Icon className="h-5 w-5" aria-hidden />
      </span>
    </Link>
  );
}

export default function OverviewPage() {
  const { t, locale } = useI18n();
  const { can, me } = useSession();
  const { data, error, mutate } = useApi<ReviewSummary>("/api/review/summary", { refreshInterval: 30_000 });
  const { data: insights } = useApi<Insights>("/api/dashboard");
  const dayPart = useDayPart();
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;

  const firstName = me?.user.full_name.split(" ")[0];
  const n = (v: number | undefined, cls = "h-8 w-12") => (v === undefined ? <Skeleton className={cls} /> : <bdi>{v}</bdi>);
  const dayFmt = new Intl.DateTimeFormat(locale === "he" ? "he-IL" : "en-GB", { day: "numeric", month: "short" });
  // a day with no invoices shown as 0 (the API lists only days that had invoices). The window is 30 days, or 14 when
  // all activity falls in the last two weeks: then 30 slots would be mostly empty and the bars too thin to read
  const byDay = new Map((insights?.daily ?? []).map((d) => [d.date, d]));
  const twoWeeksAgo = new Date();
  twoWeeksAgo.setDate(twoWeeksAgo.getDate() - 13);
  const windowDays = (insights?.daily ?? []).every((d) => d.date >= twoWeeksAgo.toISOString().slice(0, 10)) ? 14 : 30;
  const trend = Array.from({ length: windowDays }, (_, i) => {
    const day = new Date();
    day.setDate(day.getDate() - (windowDays - 1 - i));
    const key = day.toISOString().slice(0, 10);
    const row = byDay.get(key);
    return { date: key, label: dayFmt.format(day), received: row?.received ?? 0, exceptions: row?.exceptions ?? 0 };
  });
  const anyTrend = trend.some((d) => d.received + d.exceptions > 0);
  const totals = trend.reduce((s, d) => ({ received: s.received + d.received, exceptions: s.exceptions + d.exceptions }), { received: 0, exceptions: 0 });
  const busiest = trend.reduce<(typeof trend)[number] | undefined>((best, d) => (!best || d.received > best.received ? d : best), undefined);
  const urgent = data ? [
    { label: t.review.critical, value: data.by_level.critical, href: "/exceptions?level=critical", tone: "bg-danger-soft text-danger" },
    { label: t.review.high, value: data.by_level.high, href: "/exceptions?level=high", tone: "bg-warn-soft text-warn" },
    { label: t.review.overdue, value: data.overdue, href: "/exceptions?due=overdue", tone: "bg-warn-soft text-warn" },
  ] : [];

  return <div className="min-w-0 space-y-5">
    <header className="flex flex-wrap items-end justify-between gap-4 pt-2">
      <div className="min-w-0">
        <h1 className="text-4xl font-extrabold tracking-tight text-ink">
          <span className={dayPart ? undefined : "invisible"}>{t.review.greeting[dayPart ?? "morning"]}</span>{firstName ? <>, <bdi>{firstName}</bdi></> : null}
        </h1>
        <p className="mt-1 text-xl text-ink-3">{t.review.attentionToday}</p>
      </div>
      {can("invoice:read") && <ExportMenu report="insights" />}
    </header>

    {/* hero: what needs review and how much is at risk | what is urgent | the real 30-day trend */}
    <section className="command-hero grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] xl:grid-cols-[minmax(15rem,0.9fr)_minmax(13rem,0.8fr)_minmax(0,1.5fr)]" aria-label={t.review.dashboardTitle}>
      <div className="flex min-w-0 flex-col justify-between gap-4">
        <div>
          <p className="flex items-center gap-2 text-md font-bold text-ink"><FileText className="h-5 w-5 text-ink-3" aria-hidden />{t.review.needsReview}</p>
          <Link href="/exceptions" aria-label={data ? undefined : t.review.needsReview} className="mt-2 block text-display font-extrabold leading-none text-ink num hover:text-accent">{n(data?.needs_review, "h-14 w-20")}</Link>
          {data && <p className="mt-3 inline-flex items-center gap-1.5 rounded-xl bg-danger-soft px-3 py-1.5 text-lg font-extrabold text-danger num">
            <bdi className="ltr">{money(data.amount_at_risk, data.currency)}</bdi><span className="text-md font-bold">{t.review.atRisk}</span>
          </p>}
        </div>
        {can("exception:decide") && <ReviewNextButton size="lg" />}
      </div>

      <div className="min-w-0 border-line lg:border-s lg:ps-6">
        <p className="flex items-center gap-2 text-md font-bold text-ink"><AlertTriangle className="h-5 w-5 text-danger" aria-hidden />{t.review.urgentNow}</p>
        <ul className="mt-3 space-y-1">
          {data ? urgent.map((u) => <li key={u.href}>
            <Link href={u.href} className="flex h-10 items-center justify-between gap-3 rounded-xl px-2 transition-colors hover:bg-accent/[.06]">
              <span className="text-base font-semibold text-ink-2">{u.label}</span>
              <span className={cx("grid h-7 min-w-7 place-items-center rounded-lg px-2 text-sm font-extrabold num", u.tone)}>{u.value}</span>
            </Link>
          </li>) : <Skeleton className="h-28 w-full" />}
        </ul>
      </div>

      <div className="min-w-0 border-line lg:col-span-2 xl:col-span-1 xl:border-s xl:ps-6">
        <p className="flex items-center gap-2 text-md font-bold text-ink"><TrendingUp className="h-5 w-5 text-accent" aria-hidden />{t.review.trendTitleDays.replace("{n}", String(windowDays))}</p>
        <div className="mt-2">
          {!insights ? <Skeleton className="h-[200px] w-full" /> : !anyTrend
            ? <p className="grid h-[200px] place-items-center text-sm text-ink-3">{t.review.noTrend}</p>
            : <>
              <p className="mb-1 flex flex-wrap items-baseline gap-x-3 text-sm text-ink-3">
                <span><bdi className="text-xl font-extrabold text-ink num">{totals.received}</bdi> {t.review.receivedSeries}</span>
                <span><bdi className="text-xl font-extrabold text-ink num">{totals.exceptions}</bdi> {t.review.exceptionsSeries}</span>
                <span>{t.review.inPeriodDays.replace("{n}", String(windowDays))}</span>
                {busiest && busiest.received > 0 && <span className="ms-auto">{t.review.busiestDay}: <bdi className="font-semibold text-ink-2">{busiest.label}</bdi></span>}
              </p>
              <Bars data={trend} xKey="label" height={170} categoryGap={windowDays === 14 ? "28%" : "12%"}
                series={[{ key: "received", label: t.review.receivedSeries }, { key: "exceptions", label: t.review.exceptionsSeries }]} />
            </>}
        </div>
      </div>
    </section>

    <div className="grid gap-4 md:grid-cols-3">
      <Kpi href="/exceptions?due=overdue" label={t.review.overdue} value={n(data?.overdue)} tone="danger" active={(data?.overdue ?? 0) > 0} icon={CalendarClock}
        sub={data && <>{data.due_soon} {t.review.dueSoon}</>} />
      <Kpi href="/exceptions" label={t.review.openExceptions} value={n(insights?.kpis.open_exceptions)} tone="accent" active={(insights?.kpis.open_exceptions ?? 0) > 0} icon={ArrowLeftRight}
        sub={data && <>{data.awaiting_info} {t.review.awaitingInfo} · {data.escalated} {t.review.escalated}</>} />
      <Kpi href="/invoices?status=reconciled" label={t.review.readyForApproval} value={n(data?.ready_for_approval)} tone="ok" active={(data?.ready_for_approval ?? 0) > 0} icon={CheckCheck}
        sub={data && <>{data.processing} {t.review.processing}</>} />
    </div>

    <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <Panel className="min-w-0">
        <PanelHeader title={<span className="inline-flex items-center gap-2"><Layers className="h-5 w-5 text-ink-3" aria-hidden />{t.review.queue}</span>} sub={t.review.highestFirst}
          actions={<Button size="sm" asChild><Link href="/exceptions">{t.review.openQueue}<ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden /></Link></Button>} />
        {data ? <ReviewQueue items={data.top.slice(0, 6)} compact /> : <div className="p-4"><Skeleton className="h-64 w-full" /></div>}
      </Panel>
      <aside className="command-aside min-w-0 space-y-4">
        <PaymentReminders />
        {data && (data.totals_by_currency?.length ?? 0) > 1 && (
          <Panel>
            <PanelHeader title={t.review.exposure} sub={t.review.amountNote} />
            <ul className="divide-y divide-line">
              {[{ currency: data.currency, value_under_review: data.value_under_review, amount_at_risk: data.amount_at_risk },
                ...(data.totals_by_currency ?? []).filter((e) => e.currency !== data.currency)].map((e) => (
                <li key={e.currency ?? "unknown"} className="flex items-center justify-between gap-3 px-5 py-3">
                  <span className="font-bold text-ink"><bdi>{e.currency ?? t.review.currencyUnknown}</bdi></span>
                  <span className="text-end">
                    <span className="block"><bdi className="ltr font-extrabold text-danger num">{money(e.amount_at_risk, e.currency)}</bdi> <span className="text-xs text-ink-3">{t.review.atRiskLabel}</span></span>
                    <span className="block text-sm text-ink-3"><bdi className="ltr num">{money(e.value_under_review, e.currency)}</bdi> <span className="text-xs">{t.review.underReviewLabel}</span></span>
                  </span>
                </li>))}
            </ul>
          </Panel>
        )}
      </aside>
    </div>

    {/* insights: the real drivers behind the queue, from the same dashboard data */}
    {insights && (insights.discrepancy_types.length > 0 || insights.exceptions_by_supplier.length > 0) && (
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel>
          <PanelHeader title={t.review.driversTitle} sub={t.review.driversSub} />
          {insights.discrepancy_types.length
            ? <RankedList unit={t.review.findingsCount} rows={insights.discrepancy_types.slice(0, 6).map((d) => ({ key: d.type, label: label(t.finding, d.type), count: d.count }))} />
            : <p className="px-5 py-6 text-sm text-ink-3">{t.review.noInsights}</p>}
        </Panel>
        <Panel>
          <PanelHeader title={t.review.suppliersTitle} sub={t.review.suppliersSub} />
          {insights.exceptions_by_supplier.length
            ? <RankedList unit={t.review.exceptionsCount} rows={insights.exceptions_by_supplier.map((s) => ({ key: s.supplier, label: <bdi dir="auto">{s.supplier}</bdi>, count: s.count }))} />
            : <p className="px-5 py-6 text-sm text-ink-3">{t.review.noInsights}</p>}
        </Panel>
      </div>
    )}
  </div>;
}
