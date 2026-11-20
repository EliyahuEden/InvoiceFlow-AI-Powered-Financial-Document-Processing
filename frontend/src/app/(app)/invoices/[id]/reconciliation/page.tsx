"use client";

import { ArrowLeftRight, CheckCircle2, CircleX, Cpu } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { FindingTag, Pill, SeverityDot, StatusPill } from "@/components/domain";
import { useSession } from "@/components/session";
import { Button, cx, EmptyState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, money, num } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useInvoice } from "@/lib/use-invoice";
import { findingMessage } from "@/lib/findings";

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
      <Panel className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <span className="inline-flex items-center gap-2 text-sm text-ink-2"><Cpu className="h-4 w-4 text-ink-3" />{t.ai.deterministic}</span>
        {run ? (
          <>
            <span className="text-sm">{t.recon.outcome}: <StatusPill status={run.outcome} /></span>
            <span className="text-sm text-ink-2">{t.recon.mode}: <b className="font-medium text-ink">{(t.recon as Record<string, unknown>)[run.mode] as string}</b></span>
            <span className="text-sm text-ink-2">{t.recon.engine}: <span className="font-mono text-xs">{run.engine_version}</span></span>
            <span className="text-xs text-ink-3">{dateTime(run.created_at, locale)} · {run.triggered_by}</span>
          </>
        ) : <span className="text-sm text-ink-3">—</span>}
        {can("reconcile:run") && (
          <div className="ms-auto flex gap-2">
            <Button size="sm" loading={busy === "two_way"} onClick={() => rerun("two_way")}>{t.recon.two_way}</Button>
            <Button size="sm" variant="primary" loading={busy === "three_way"} onClick={() => rerun("three_way")}>{t.recon.three_way}</Button>
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Panel>
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
                      <span dir="auto" className="block truncate">{ln.description}</span>
                      <span className="ltr font-mono text-2xs text-ink-3">{ln.sku}</span>
                    </Td>
                    <Td className={cx("text-end num", qtyBad && "font-semibold text-danger")}>{num(ln.quantity)}</Td>
                    <Td className={cx("border-e border-line text-end", priceBad && "font-semibold text-danger")}><span className="ltr">{money(ln.unit_price)}</span></Td>
                    <Td className="text-center">
                      {m ? <Pill tone={m.method === "sku" ? "ok" : m.method === "description" ? "accent" : m.method === "ambiguous" ? "warn" : "danger"}>
                        {(t.recon.lineMatch as Record<string, string>)[m.method]}{m.method === "description" && ` ${Math.round(m.score * 100)}%`}
                      </Pill> : "—"}
                    </Td>
                    {pl ? (
                      <>
                        <Td className="max-w-[14rem] border-s border-line"><span dir="auto" className="block truncate">{pl.description}</span>
                          <span className="ltr font-mono text-2xs text-ink-3">{pl.sku}</span></Td>
                        <Td className="text-end num">{num(pl.quantity)}</Td>
                        <Td className={cx("text-end num", qtyBad && "font-semibold text-ok")}>{num(pl.received)}</Td>
                        <Td className={cx("text-end", priceBad && "font-semibold text-ok")}><span className="ltr">{money(pl.unit_price)}</span></Td>
                      </>
                    ) : (
                      <Td colSpan={4} className="border-s border-line text-sm text-ink-3">
                        {m?.method === "ambiguous" ? (
                          <span className="space-y-0.5">{m.candidates.slice(0, 2).map((c) => (
                            <span key={c.po_line_id} dir="auto" className="block">{c.description} · <span className="ltr">{money(c.unit_price)}</span> · {Math.round(c.score * 100)}%</span>
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
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">{t.recon.tolerances}</p>
              <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
                {Object.entries(run.tolerances).map(([k, v]) => (
                  <div key={k} className="flex gap-1"><dt>{(t.settings as Record<string, string>)[k] ?? k}:</dt><dd className="font-medium text-ink num">{String(v)}</dd></div>
                ))}
              </dl>
            </div>
          )}
        </Panel>

        <div className="space-y-5">
          <Panel>
            <PanelHeader title={t.recon.findings} />
            {findings.length === 0 ? <EmptyState icon={<CheckCircle2 className="h-7 w-7 text-ok" />} title={t.recon.allClear} /> : (
              <ul className="divide-y divide-line">
                {findings.map((f) => (
                  <li key={f.id} className="px-4 py-3">
                    <div className="flex items-center gap-2"><SeverityDot severity={f.severity} /><FindingTag type={f.type} severity={f.severity} /></div>
                    <p className="mt-1.5 text-sm text-ink" dir="auto">{findingMessage(t, f)}</p>
                    {(f.expected || f.actual) && (
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
              <PanelHeader title={t.recon.checks} />
              <ul className="divide-y divide-line">
                {run.checks.map((c) => (
                  <li key={c.check} className="flex items-center gap-2 px-4 py-2 text-sm">
                    {c.passed ? <CheckCircle2 className="h-4 w-4 text-ok" aria-label="passed" /> : <CircleX className="h-4 w-4 text-danger" aria-label="failed" />}
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
