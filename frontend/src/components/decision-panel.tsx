"use client";

import { Check, HelpCircle, ShieldAlert, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { ActionLabel } from "./domain";
import { Button, Field, Panel, PanelHeader, Select, Textarea } from "./ui";

export type Decision = "approve" | "reject" | "request_info" | "escalate";

export function DecisionPanel({ proposedAction, detail, allowedActions, note, override, target, onNote, onOverride,
  onTarget, onDecide, busy, canDecide, canRequestInfo, restricted }: {
  proposedAction: string | null; detail?: string | null; allowedActions: string[];
  note: string; override: string; target: string; onNote: (value: string) => void; onOverride: (value: string) => void;
  onTarget: (value: string) => void; onDecide: (decision: Decision) => void; busy: string | null;
  canDecide: boolean; canRequestInfo: boolean; restricted: boolean;
}) {
  const { t } = useI18n();
  return <Panel id="review-decision" data-testid="decision-panel" className="scroll-mt-20">
    <PanelHeader title={t.exceptions.decide} />
    <div className="space-y-4 p-4">
      <div className="border-b border-line pb-3">
        <p className="text-xs text-ink-3">{t.exceptions.proposed} · {t.ai.deterministic}</p>
        <p className="mt-1 font-medium"><ActionLabel action={override || proposedAction} /></p>
        {detail && !override && <p className="mt-1 text-sm text-ink-2">{detail}</p>}
      </div>
      {restricted && <p className="text-sm text-warn">{t.review.escalationRestricted}</p>}
      {!restricted && (canDecide || canRequestInfo) && <>
        {canDecide && !restricted && <Field label={t.exceptions.changeAction} htmlFor="override">
          <Select id="override" className="w-full" value={override} onChange={(ev) => onOverride(ev.target.value)} disabled={!!busy}>
            <option value="">—</option>
            {allowedActions.map((action) => <option key={action} value={action}>{(t.action as Record<string, string>)[action] ?? action}</option>)}
          </Select>
        </Field>}
        <Field label={t.exceptions.note} htmlFor="note">
          <Textarea id="note" value={note} onChange={(ev) => onNote(ev.target.value)} maxLength={4000}
            placeholder={t.exceptions.notePlaceholder} disabled={!!busy} />
        </Field>
        {canRequestInfo && <Field label={t.review.target} htmlFor="request-target">
          <Select id="request-target" className="w-full" value={target} onChange={(ev) => onTarget(ev.target.value)} disabled={!!busy}>
            <option value="">—</option>
            <option value="procurement">{t.review.procurement}</option>
            <option value="supplier">{t.review.supplier}</option>
          </Select>
        </Field>}
        <div className="flex flex-wrap gap-2">
          {canDecide && !restricted && <>
            <Button variant="primary" loading={busy === "approve"} disabled={!!busy} onClick={() => onDecide("approve")}>
              <Check className="h-4 w-4" aria-hidden />{t.exceptions.approve}
            </Button>
            <Button variant="danger" loading={busy === "reject"} disabled={!!busy || !note.trim()} onClick={() => onDecide("reject")}>
              <X className="h-4 w-4" aria-hidden />{t.exceptions.reject}
            </Button>
          </>}
          {canRequestInfo && <Button loading={busy === "request_info"} disabled={!!busy || !note.trim() || !target}
            onClick={() => onDecide("request_info")}><HelpCircle className="h-4 w-4" aria-hidden />{t.exceptions.requestInfo}</Button>}
          {canDecide && !restricted && <Button loading={busy === "escalate"} disabled={!!busy || !note.trim()}
            onClick={() => onDecide("escalate")}><ShieldAlert className="h-4 w-4" aria-hidden />{t.review.escalate}</Button>}
        </div>
      </>}
    </div>
  </Panel>;
}
