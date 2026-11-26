"use client";

import { ArrowLeftRight, CheckCircle2, CircleX, Cpu } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { FindingTag, Pill, SeverityDot, StatusPill } from "@/components/domain";
import { useSession } from "@/components/session";
import { Button, cx, EmptyState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, money, num, unitPrice } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useInvoice } from "@/lib/use-invoice";
import { findingMessage } from "@/lib/findings";
import { label } from "@/lib/i18n/label";

export default function ReconciliationPage() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const { data: inv, mutate } = useInvoice();
  const [busy, setBusy] = useState<string | null>(null);
  if (!inv) return <Skeleton className="h-[500px] w-full" />;
  const run = inv.reconciliation;
  const poLines = new Map(inv.purchase_order?.lines.map((l) => [l.id, l]) ?? []);
  const findings = inv.discrepancies;
  const rerun = async (mode: string) => {
    setBusy(mode);
    try { await api.post(`/api/invoices/${inv.id}/reconcile?mode=${mode}`); mutate(); toast.success(t.recon.rerun); }
    catch (e) { toast.error(String((e as Error).message)); } finally { setBusy(null); }
  };

  return (
    <div className="space-y-5">
      <Panel className="command-panel">
        <PanelHeader title={<span className="inline-flex items-center gap-2"><Cpu className="h-5 w-5 text-accent-ink" />{t.ai.deterministic}</span>}
          actions={can("reconcile:run") && <>
            <Button size="sm" disabled={!!busy || inv.status === "processing"} loading={busy === "two_way"} onClick={() => rerun("two_way")}>{t.recon.two_way}</Button>
            <Button size="sm" variant="primary" disabled={!!busy || inv.status === "processing"} loading={busy === "three_way"} onClick={() => rerun("three_way")}>{t.recon.three_way}</Button>
          </>} />
        {run ? (
          <dl className="grid grid-cols-2 gap-4 p-4 text-sm sm:grid-cols-4 sm:p-5">
            <div><dt className="mb-1 text-xs text-ink-3">{t.recon.outcome}</dt><dd><StatusPill status={run.outcome} /></dd></div>
            <div><dt className="mb-1 text-xs text-ink-3">{t.recon.mode}</dt><dd className="font-medium">{(t.recon as Record<string, unknown>)[run.mode] as string}</dd></div>
            <div><dt className="mb-1 text-xs text-ink-3">{t.recon.engine}</dt><dd><bdi className="font-mono">{run.engine_version}</bdi></dd></div>
            <div><dt className="mb-1 text-xs text-ink-3">{t.common.created}</dt><dd>{dateTime(run.created_at, locale)} · <bdi>{run.triggered_by}</bdi></dd></div>
          </dl>
        ) : <p className="p-4 text-sm text-ink-3">{t.evaluation.notRun}</p>}
      </Panel>

      <div className="command-layout grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1.75fr)_minmax(0,1fr)]">
        <Panel className="command-panel min-w-0">
          <PanelHeader title={<span className="inline-flex items-center gap-2"><ArrowLeftRight className="h-4 w-4 text-ink-3" />{t.recon.invoice} ↔ {t.recon.po}</span>}
            sub={inv.purchase_order ? <Link href={`/purchase-orders/${inv.purchase_order.id}`} className="ltr font-mono hover:text-accent">{inv.purchase_order.po_number} · {inv.purchase_order.currency}</Link> : t.recon.noPo} />
          <Table>
            <thead>
              <tr>
                <Th colSpan={3} className="border-e border-line">{t.recon.invoice}</Th>
                <Th>{t.recon.match}</Th>
                <Th colSpan={4} className="border-s border-line">{t.recon.po}</Th>
              </tr>
              <tr>
                <Th>{t.invoice.description}</Th><Th className="text-end">{t.invoice.qty}</Th><Th className="border-e border-line text-end">{t.invoice.unitPrice}</Th>
                <Th />
                <Th className="border-s border-line">{t.invoice.description}</Th><Th className="text-end">{t.pos.ordered}</Th>
                <Th className="text-end">{t.recon.received}</Th><Th className="text-end">{t.invoice.unitPrice}</Th>
              </tr>
            </thead>
            <tbody>
              {inv.lines.map((ln) => {
                const m = run?.line_matches.find((x) => x.invoice_line_no === ln.line_no);
                const pl = m?.po_line_id ? poLines.get(m.po_line_id) : undefined;
                const lineFindings = findings.filter((f) => f.evidence?.invoice_line_no === ln.line_no && f.severity !== "info");
                const qtyBad = lineFindings.some((f) => f.type.startsWith("QUANTITY"));
                const priceBad = lineFindings.some((f) => f.type === "PRICE_MISMATCH");
                return (
                  <tr key={ln.id} className={lineFindings.length ? "bg-danger-soft/30" : ""}>
                    <Td className="max-w-[14rem]">
                      <span dir="auto" className="block min-w-24">{ln.description}</span>
                      <span className="ltr font-mono text-2xs text-ink-3">{ln.sku}</span>
                    </Td>
                    <Td className={cx("text-end num", qtyBad && "font-semibold text-danger")}>{num(ln.quantity)}</Td>
                    <Td className={cx("border-e border-line text-end", priceBad && "font-semibold text-danger")}><span className="ltr">{unitPrice(ln.unit_price)}</span></Td>
                    <Td className="text-center">
                      {m ? <Pill tone={m.method === "sku" ? "ok" : m.method === "description" ? "accent" : m.method === "ambiguous" ? "warn" : "danger"}>
                        {label(t.recon.lineMatch, m.method)}{m.method === "description" && ` ${Math.round(m.score * 100)}%`}
                      </Pill> : "—"}
                    </Td>
                    {pl ? (
                      <>
                        <Td className="max-w-[14rem] border-s border-line"><span dir="auto" className="block min-w-24">{pl.description}</span>
                          <span className="ltr font-mono text-2xs text-ink-3">{pl.sku}</span></Td>
                        <Td className="text-end num">{num(pl.quantity)}</Td>
                        <Td className={cx("text-end num", qtyBad && "font-semibold text-ok")}>{num(pl.received)}</Td>
                        <Td className={cx("text-end", priceBad && "font-semibold text-ok")}><span className="ltr">{unitPrice(pl.unit_price)}</span></Td>
                      </>
                    ) : (
                      <Td colSpan={4} className="border-s border-line text-sm text-ink-3">
                        {m?.method === "ambiguous" ? (
                          <span className="space-y-0.5">{m.candidates.slice(0, 2).map((c) => (
                            <span key={c.po_line_id} dir="auto" className="block">{c.description} · <span className="ltr">{unitPrice(c.unit_price)}</span> · {Math.round(c.score * 100)}%</span>
                          ))}</span>
                        ) : t.recon.lineMatch.none}
                      </Td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </Table>
          {run && (
            <div className="border-t border-line px-4 py-3">
              <p className="mb-2 text-sm font-semibold text-ink-3">{t.recon.tolerances}</p>
              <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
                {Object.entries(run.tolerances).map(([k, v]) => (
                  <div key={k} className="flex gap-1"><dt>{label(t.settings, k)}:</dt><dd className="font-medium text-ink num">{String(v)}</dd></div>
                ))}
              </dl>
            </div>
          )}
        </Panel>

        <div className="min-w-0 space-y-4">
          <Panel className="command-aside">
            <PanelHeader title={t.recon.findings} />
            {findings.length === 0 ? <EmptyState icon={run ? <CheckCircle2 className="h-7 w-7 text-ok" /> : undefined} title={run ? t.recon.allClear : t.evaluation.notRun} /> : (
              <ul className="divide-y divide-line">
                {findings.map((f) => (
                  <li key={f.id} className="px-4 py-3">
                    <div className="flex items-center gap-2"><SeverityDot severity={f.severity} /><FindingTag type={f.type} severity={f.severity} /></div>
                    <p className="mt-1.5 text-sm text-ink" dir="auto">{findingMessage(t, f)}</p>
                    {(f.expected || f.actual) && f.type !== "DUPLICATE_INVOICE" && f.type !== "POSSIBLE_DUPLICATE" && (
                      <dl className="mt-2 grid grid-cols-3 gap-2 rounded-md bg-sunken px-3 py-2 text-xs">
                        <div><dt className="text-ink-3">{t.recon.expected}</dt><dd className="font-medium num ltr">{f.expected ?? "—"}</dd></div>
                        <div><dt className="text-ink-3">{t.recon.actual}</dt><dd className="font-medium num ltr">{f.actual ?? "—"}</dd></div>
                        <div><dt className="text-ink-3">{f.evidence?.amount_at_risk ? t.recon.atRisk : t.recon.difference}</dt>
                          <dd className="font-medium text-danger num ltr">{f.evidence?.amount_at_risk ? money(f.evidence.amount_at_risk, inv.currency) : f.difference ?? "—"}</dd></div>
                      </dl>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          {run && (
            <Panel>
              <PanelHeader title={t.recon.checks} actions={<span className="text-sm text-ink-2 num">{run.checks.filter((c) => c.passed).length} / {run.checks.length}</span>} />
              <ul className="divide-y divide-line">
                {run.checks.map((c) => (
                  <li key={c.check} className="flex items-center gap-2 px-4 py-2 text-sm">
                    {c.passed ? <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" aria-label={t.status.succeeded} /> : <CircleX className="h-4 w-4 shrink-0 text-danger" aria-label={t.status.failed} />}
                    <span className="font-mono text-xs text-ink-2">{c.check}</span>
                    {c.detail && <span className="ms-auto text-xs text-ink-3">{c.detail}</span>}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
