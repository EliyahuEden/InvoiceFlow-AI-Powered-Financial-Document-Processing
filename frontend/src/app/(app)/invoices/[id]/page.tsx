"use client";

import { Check, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { DocumentViewer } from "@/components/document-viewer";
import { ActionLabel, FindingTag, SecurityNotice, StatusPill, VerifiedTag, WarningList } from "@/components/domain";
import { fieldHighlights, FieldList } from "@/components/invoice-fields";
import { useSession } from "@/components/session";
import { Button, Panel, PanelHeader, Skeleton, Table, Td, Textarea, Th } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dateTime, money, num } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useInvoice } from "@/lib/use-invoice";

export default function InvoiceOverview() {
  const { t, locale } = useI18n();
  const { can } = useSession();
  const { data: inv, mutate } = useInvoice();
  const [hover, setHover] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  if (!inv) return <div className="grid grid-cols-1 gap-5 xl:grid-cols-2"><Skeleton className="h-[640px] w-full" /><Skeleton className="h-[640px] w-full" /></div>;

  const security = inv.validation_warnings.filter((w) => w.code === "SUSPICIOUS_INSTRUCTIONS");
  const otherWarnings = inv.validation_warnings.filter((w) => w.code !== "SUSPICIOUS_INSTRUCTIONS");
  const pending = inv.approvals.find((a) => a.status === "pending");

  const decide = async (decision: "approve" | "reject") => {
    setBusy(true);
    try {
      await api.post(`/api/invoices/${inv.id}/approvals`, { decision, comment: comment || null });
      toast.success(decision === "approve" ? t.invoice.approve : t.invoice.reject);
      setComment("");
      mutate();
    } catch (e) {
      toast.error(e instanceof ApiError ? String(e.message) : t.common.error);
    } finally { setBusy(false); }
  };

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      {inv.document && (
        <DocumentViewer className="h-[calc(100vh-14rem)] min-h-[560px] xl:sticky xl:top-20" documentId={inv.document.id}
          pageCount={inv.document.page_count ?? 1} filename={inv.document.filename} highlights={fieldHighlights(inv)} activeId={hover} />
      )}
      <div className="space-y-5">
        <SecurityNotice items={security} />
        {inv.exception && (
          <Link href={`/exceptions/${inv.exception.id}`} className="flex items-center justify-between gap-3 rounded-lg border border-danger/25 bg-danger-soft/60 px-4 py-3 transition-colors hover:bg-danger-soft">
            <span className="min-w-0">
              <span className="block truncate text-base font-medium text-ink">{(t.finding as Record<string, string>)[inv.discrepancies.find((d) => d.severity !== "info")?.type ?? ""] ?? inv.exception.title}</span>
              <span className="text-sm text-ink-2">{t.exceptions.proposed}: <ActionLabel action={inv.exception.proposed_action} /></span>
            </span>
            <StatusPill status={inv.exception.status} />
          </Link>
        )}
        <Panel>
          <PanelHeader title={t.invoice.fields}
            sub={<span className="flex flex-wrap items-center gap-2">{t.invoice.hoverHint}</span>}
            actions={<span className="text-xs text-ink-3">{t.invoice.method}: <span className="font-mono">{inv.extraction_method ?? "—"}</span></span>} />
          <FieldList inv={inv} onHover={setHover} />
          {inv.missing_fields.length > 0 && (
            <p className="border-t border-line px-4 py-2 text-sm text-warn">{t.invoice.missing}: {inv.missing_fields.join(", ")}</p>
          )}
        </Panel>

        <Panel>
          <PanelHeader title={t.invoice.lineItems} actions={<VerifiedTag label={t.invoice.verifiedInDoc} />} />
          <Table>
            <thead><tr><Th>#</Th><Th>{t.invoice.sku}</Th><Th>{t.invoice.description}</Th><Th className="text-end">{t.invoice.qty}</Th>
              <Th className="text-end">{t.invoice.unitPrice}</Th><Th className="text-end">{t.invoice.lineTotal}</Th></tr></thead>
            <tbody>
              {inv.lines.map((ln) => {
                const flagged = inv.discrepancies.filter((d) => d.evidence?.invoice_line_no === ln.line_no && d.severity !== "info");
                return (
                  <tr key={ln.id} onMouseEnter={() => setHover(`l:${ln.line_no}`)} onMouseLeave={() => setHover(null)}
                    className={flagged.length ? "bg-danger-soft/40" : "hover:bg-hl/10"}>
                    <Td className="text-ink-3 num">{ln.line_no}</Td>
                    <Td><span className="ltr font-mono text-xs">{ln.sku ?? "—"}</span></Td>
                    <Td className="max-w-[18rem]">
                      <span dir="auto" className="block truncate">{ln.description}</span>
                      {flagged.map((d) => <span key={d.id} className="me-1 mt-1 inline-block"><FindingTag type={d.type} severity={d.severity} /></span>)}
                    </Td>
                    <Td className="text-end num">{num(ln.quantity)}</Td>
                    <Td className="text-end"><span className="ltr">{money(ln.unit_price)}</span></Td>
                    <Td className="text-end font-medium"><span className="ltr">{money(ln.line_total)}</span></Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Panel>

        {otherWarnings.length > 0 && (
          <Panel><PanelHeader title={t.invoice.warnings} /><div className="p-4"><WarningList items={otherWarnings} /></div></Panel>
        )}

        <Panel>
          <PanelHeader title={t.invoice.approvals} />
          {inv.approvals.length === 0 ? <p className="px-4 py-4 text-sm text-ink-3">{t.invoice.noApprovals}</p> : (
            <ul className="divide-y divide-line">
              {inv.approvals.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <span>{t.invoice.step} {a.step} · {(t.roles as Record<string, string>)[a.required_role]}</span>
                  <span className="flex items-center gap-2">
                    {a.decided_at && <span className="text-xs text-ink-3">{dateTime(a.decided_at, locale)}</span>}
                    <StatusPill status={a.status} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          {pending && inv.status === "reconciled" && can("approval:decide") && (
            <div className="space-y-2 border-t border-line p-4">
              <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t.exceptions.notePlaceholder} className="min-h-14" />
              <div className="flex gap-2">
                <Button variant="primary" loading={busy} onClick={() => decide("approve")}><Check className="h-4 w-4" />{t.invoice.approve}</Button>
                <Button variant="danger" disabled={busy} onClick={() => decide("reject")}><X className="h-4 w-4" />{t.invoice.reject}</Button>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
