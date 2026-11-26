"use client";

import { Check, FileSearch, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { DocumentViewer } from "@/components/document-viewer";
import { ActionLabel, FindingTag, SecurityNotice, StatusPill, VerifiedTag, WarningList } from "@/components/domain";
import { fieldHighlights, FieldList, SourceTags } from "@/components/invoice-fields";
import { InvoicePayment } from "@/components/invoice-payment";
import { InvoiceLifecycle } from "@/components/invoice-lifecycle";
import { useSession } from "@/components/session";
import { Button, EmptyState, Panel, PanelHeader, Skeleton, Table, Td, Textarea, Th } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dateTime, money, num, unitPrice } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useInvoice } from "@/lib/use-invoice";
import { useUnsavedWork } from "@/lib/use-unsaved-work";
import { label } from "@/lib/i18n/label";

export default function InvoiceOverview() {
  const { t, locale } = useI18n();
  const { can, me } = useSession();
  const { data: inv, mutate } = useInvoice();
  const [hover, setHover] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  useUnsavedWork(!!comment.trim(), t.review.unsavedChanges);
  if (!inv) return <div className="grid grid-cols-1 gap-5 xl:grid-cols-2"><Skeleton className="h-[640px] w-full" /><Skeleton className="h-[640px] w-full" /></div>;

  const security = inv.validation_warnings.filter((w) => w.code === "SUSPICIOUS_INSTRUCTIONS");
  const otherWarnings = inv.validation_warnings.filter((w) => w.code !== "SUSPICIOUS_INSTRUCTIONS");
  const pending = inv.approvals.find((a) => a.status === "pending");
  const canDecide = pending && inv.status === "reconciled" && can(pending.step > 1 ? "approval:final" : "approval:decide")
    && !inv.approvals.some((a) => a.status === "approved" && a.decided_by === me?.user.id);

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
    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      {inv.document ? (
        <DocumentViewer className="h-[56svh] min-h-80 lg:sticky lg:top-20 lg:h-[calc(100svh-7rem)]" documentId={inv.document.id}
          pageCount={inv.document.page_count ?? 1} filename={inv.document.filename} highlights={fieldHighlights(inv)} activeId={hover} />
      ) : <Panel><EmptyState icon={<FileSearch className="h-7 w-7" />} title={t.review.noDocument} /></Panel>}
      <div className="min-w-0 space-y-4">
        <SecurityNotice items={security} />
        {inv.exception && (
          <Link href={`/exceptions/${inv.exception.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-warn/30 bg-warn-soft px-5 py-4 transition-colors hover:border-warn">
            <span className="min-w-0">
              <span className="block truncate text-base font-medium text-ink">{label(t.finding, inv.discrepancies.find((d) => d.severity !== "info")?.type ?? "", inv.exception.title)}</span>
              <span className="text-sm text-ink-2">{t.exceptions.proposed}: <ActionLabel action={inv.exception.proposed_action} /></span>
            </span>
            <StatusPill status={inv.exception.status} />
          </Link>
        )}
        <Panel className="command-panel">
          <PanelHeader title={t.invoice.fields}
            sub={<span className="flex flex-wrap items-center gap-2">{t.invoice.hoverHint}</span>}
            actions={<span className="text-xs text-ink-3">{t.invoice.method}: <span>{!inv.extraction_method ? "—" : inv.extraction_method.startsWith("rules+llm") ? `${t.inbox.methodRulesAi} (${inv.extraction_method.split(":")[1] ?? ""})` : inv.extraction_method === "rule_based" ? t.inbox.methodRules : inv.extraction_method}</span></span>} />
          <FieldList inv={inv} onHover={setHover} />
          {inv.missing_fields.length > 0 && (
            <p className="border-t border-line px-4 py-2 text-sm text-warn">{t.invoice.missing}: {inv.missing_fields.join(", ")}</p>
          )}
        </Panel>

        <Panel className="command-panel">
          <PanelHeader title={t.invoice.lineItems} actions={inv.lines.length > 0 && inv.lines.every((line) => line.source?.verified && !line.source.corrected_by) && <VerifiedTag label={t.invoice.verifiedInDoc} />} />
          <Table>
            <thead><tr><Th>#</Th><Th>{t.invoice.sku}</Th><Th>{t.invoice.description}</Th><Th className="text-end">{t.invoice.qty}</Th>
              <Th className="text-end">{t.invoice.unitPrice}</Th><Th className="text-end">{t.invoice.lineTotal}</Th></tr></thead>
            <tbody>
              {inv.lines.map((ln) => {
                const flagged = inv.discrepancies.filter((d) => d.evidence?.invoice_line_no === ln.line_no && d.severity !== "info");
                return (
                  <tr key={ln.id} tabIndex={ln.source?.bbox ? 0 : undefined}
                    onFocus={() => setHover(`l:${ln.line_no}`)} onBlur={() => setHover(null)}
                    onMouseEnter={() => setHover(`l:${ln.line_no}`)} onMouseLeave={() => setHover(null)}
                    className={flagged.length ? "bg-danger-soft/40" : "hover:bg-hl/10"}>
                    <Td className="text-ink-3 num">{ln.line_no}</Td>
                    <Td><span className="ltr whitespace-nowrap font-mono text-xs">{ln.sku ?? "—"}</span></Td>
                    <Td className="max-w-[18rem]">
                      <span className="block min-w-28"><bdi>{ln.description}</bdi></span>
                      {ln.source?.corrected_by && <SourceTags source={ln.source} corrected />}
                      {flagged.map((d) => <span key={d.id} className="me-1 mt-1 inline-block"><FindingTag type={d.type} severity={d.severity} /></span>)}
                    </Td>
                    <Td className="text-end num">{num(ln.quantity)}</Td>
                    <Td className="text-end"><span className="ltr">{unitPrice(ln.unit_price)}</span></Td>
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

        <Panel className="command-panel">
          <PanelHeader title={<span className="inline-flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-ink-2" />{t.invoice.approvals}</span>} />
          {inv.approvals.length === 0 ? <p className="px-4 py-4 text-sm text-ink-3">{t.invoice.noApprovals}</p> : (
            <ul className="divide-y divide-line">
              {inv.approvals.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <span>{t.invoice.step} {a.step} · {label(t.roles, a.required_role)}</span>
                  <span className="flex items-center gap-2">
                    {a.decided_at && <span className="text-xs text-ink-3">{dateTime(a.decided_at, locale)}</span>}
                    <StatusPill status={a.status} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          {canDecide && (
            <div className="space-y-2 border-t border-line p-4">
              <Textarea value={comment} aria-label={t.exceptions.note} onChange={(e) => setComment(e.target.value)} placeholder={t.exceptions.notePlaceholder} className="min-h-14" />
              <div className="flex gap-2">
                <Button variant="primary" loading={busy} onClick={() => decide("approve")}><Check className="h-4 w-4" />{t.invoice.approve}</Button>
                <Button variant="danger" disabled={busy} onClick={() => decide("reject")}><X className="h-4 w-4" />{t.invoice.reject}</Button>
              </div>
            </div>
          )}
        </Panel>
        <InvoicePayment invoice={inv} onUpdated={() => void mutate()} />
        <InvoiceLifecycle invoice={inv} onUpdated={() => void mutate()} />
      </div>
    </div>
  );
}
