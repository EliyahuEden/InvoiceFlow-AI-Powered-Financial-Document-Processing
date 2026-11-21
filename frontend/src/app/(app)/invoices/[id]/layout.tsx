"use client";

import { ArrowLeft, Bot, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { toast } from "sonner";
import { StatusPill } from "@/components/domain";
import { useSession } from "@/components/session";
import { Button, cx, ErrorState, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useInvoice } from "@/lib/use-invoice";

export default function InvoiceLayout({ children }: { children: React.ReactNode }) {
  const { t, locale } = useI18n();
  const { id } = useParams<{ id: string }>();
  const path = usePathname();
  const { can } = useSession();
  const { data: inv, error, mutate } = useInvoice();
  const tabs = [
    { href: `/invoices/${id}`, label: t.invoice.tabs.overview },
    { href: `/invoices/${id}/review`, label: t.invoice.tabs.review },
    { href: `/invoices/${id}/reconciliation`, label: t.invoice.tabs.reconciliation, badge: inv?.discrepancies.filter((d) => d.severity !== "info").length },
    { href: `/invoices/${id}/investigation`, label: t.invoice.tabs.investigation, ai: true },
    { href: `/invoices/${id}/history`, label: t.invoice.tabs.audit },
  ];
  if (error) return <ErrorState message={error.status === 404 ? t.invoice.notFound : t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;

  const rerun = async () => {
    try {
      const r = await api.post<{ outcome: string }>(`/api/invoices/${id}/reconcile`);
      toast.success(`${t.recon.title}: ${(t.status as Record<string, string>)[r.outcome] ?? r.outcome}`);
      mutate();
    } catch (e) { toast.error(String((e as Error).message)); }
  };
  const investigate = async () => {
    try {
      await api.post(`/api/invoices/${id}/investigate`);
      toast.success(t.invoice.investigate);
      mutate();
    } catch (e) { toast.error(String((e as Error).message)); }
  };
  const supplierLabel = inv ? (locale === "en" && inv.supplier?.name_en ? inv.supplier.name_en : inv.supplier?.name ?? inv.supplier_name_raw) : null;
  const agentBusy = inv?.agent_runs.some((r) => ["queued", "running"].includes(r.status));

  return (
    <div>
      <header className="command-hero mb-5 space-y-4">
        <div className="flex min-w-0 items-center gap-2 text-sm text-ink-2">
          <Link href="/invoices" className="inline-flex items-center gap-1 font-medium hover:text-accent"><ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />{t.nav.inbox}</Link>
          {inv && <><ChevronRight className="h-3 w-3 rtl:rotate-180" aria-hidden /><bdi className="truncate">{inv.invoice_number ?? inv.filename}</bdi></>}
        </div>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            {!inv ? <Skeleton className="h-8 w-64" /> : (
              <>
                <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
                  <bdi className="min-w-0 break-words">{path.endsWith("/review") ? t.invoice.verifyTitle : inv.invoice_number ?? inv.filename}</bdi>
                  <StatusPill status={inv.status} />
                </h1>
                <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
                  <span dir="auto" className={inv.supplier ? "" : "italic text-ink-3"}>{supplierLabel ?? t.common.unknown}</span>
                  <span className="text-line-strong" aria-hidden>|</span>
                  <span>{date(inv.invoice_date, locale)}</span>
                  <span className="text-line-strong" aria-hidden>|</span>
                  <span className="ltr font-semibold text-ink">{money(inv.total, inv.currency)}</span>
                  {inv.purchase_order && (<><span className="text-line-strong" aria-hidden>|</span>
                    <Link href={`/purchase-orders/${inv.purchase_order.id}`} className="ltr font-mono text-sm hover:text-accent">{inv.purchase_order.po_number}</Link></>)}
                </p>
              </>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {can("reconcile:run") && <Button onClick={rerun} disabled={!inv || inv.status === "processing"}><RefreshCw className="h-4 w-4" />{t.invoice.reprocess}</Button>}
            {can("agent:run") && (
              <Button variant="ai" onClick={investigate} disabled={!inv || inv.status === "processing" || agentBusy}>
                {agentBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}{t.invoice.investigate}
              </Button>
            )}
          </div>
        </div>
      <nav className="flex max-w-full flex-wrap items-center gap-1.5 border-t border-line pt-3" aria-label={t.invoice.sections}>
        {tabs.map((tab) => {
          const active = path === tab.href;
          return (
            <Link key={tab.href} href={tab.href} aria-current={active ? "page" : undefined}
              className={cx("inline-flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-sm font-medium transition-colors",
                active ? "border-line-strong bg-surface text-ink shadow-raise" : "border-transparent text-ink-2 hover:border-line hover:bg-surface")}>
              {tab.label}
              {tab.ai && <span className="rounded bg-ai-soft px-1 text-2xs font-semibold text-ai">AI</span>}
              {!!tab.badge && <span className="grid h-5 min-w-5 place-items-center rounded-full bg-danger-soft px-1 text-2xs font-semibold text-danger num">{tab.badge}</span>}
            </Link>
          );
        })}
      </nav>
      </header>
      {inv?.status === "processing" && inv.job && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-info/25 bg-info-soft px-4 py-3 text-sm text-info">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="font-medium">{t.invoice.processingNow}</span>
          <span className="text-info/80">{inv.job.message}</span>
          <span className="ms-auto num">{inv.job.progress}%</span>
        </div>
      )}
      {inv?.status === "failed" && (
        <div className="mb-4"><ErrorState message={`${t.invoice.failedTitle}: ${inv.document?.error ?? inv.job?.error ?? ""}`} /></div>
      )}
      {children}
    </div>
  );
}
