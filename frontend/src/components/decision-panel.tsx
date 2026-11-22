"use client";

import { Check, GitBranch, HelpCircle, ShieldAlert, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { ActionLabel } from "./domain";
import { Button, Field, Panel, PanelHeader, Select, Textarea } from "./ui";
import { label } from "@/lib/i18n/label";

export type Decision = "approve" | "reject" | "request_info" | "escalate";

export function DecisionPanel({ proposedAction, detail, allowedActions, note, override, target, onNote, onOverride,
  onTarget, onDecide, busy, canDecide, canRequestInfo, restricted }: {
  proposedAction: string | null; detail?: string | null; allowedActions: string[];
  note: string; override: string; target: string; onNote: (value: string) => void; onOverride: (value: string) => void;
  onTarget: (value: string) => void; onDecide: (decision: Decision) => void; busy: string | null;
  canDecide: boolean; canRequestInfo: boolean; restricted: boolean;
}) {
  // approving with a different action than proposed is an override: it needs a written justification
  const overriding = !!override && override !== proposedAction;
  const { t } = useI18n();
  return <Panel data-testid="decision-panel" className="command-panel min-w-0">
    <PanelHeader title={t.agent.decision} />
    <div className="space-y-4 p-4">
      <div className="rounded-md bg-sunken px-3 py-2.5">
        <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-ink-2"><GitBranch className="h-3.5 w-3.5" aria-hidden />{t.exceptions.proposed} · {t.ai.deterministic}</p>
        <p className="mt-1 font-semibold leading-snug"><ActionLabel action={override || proposedAction} /></p>
        {detail && !override && <p className="mt-1 break-words text-sm leading-snug text-ink-2" dir="auto">{detail}</p>}
      </div>
      {restricted && <p className="rounded-md bg-warn-soft p-3 text-sm text-warn">{t.review.escalationRestricted}</p>}
      {!restricted && (canDecide || canRequestInfo) && <>
        <Field label={t.exceptions.note} htmlFor="note">
          <Textarea id="note" dir="auto" value={note} onChange={(ev) => onNote(ev.target.value)} maxLength={4000}
            placeholder={t.exceptions.notePlaceholder} disabled={!!busy} />
        </Field>
        {canDecide && <Field label={t.exceptions.changeAction} htmlFor="override">
          <Select id="override" className="w-full" value={override} onChange={(ev) => onOverride(ev.target.value)} disabled={!!busy}>
            <option value="">—</option>
            {allowedActions.map((action) => <option key={action} value={action}>{label(t.action, action)}</option>)}
          </Select>
        </Field>}
        {canRequestInfo && <Field label={t.review.target} htmlFor="request-target">
          <Select id="request-target" className="w-full" value={target} onChange={(ev) => onTarget(ev.target.value)} disabled={!!busy}>
            <option value="">—</option>
            <option value="procurement">{t.review.procurement}</option>
            <option value="supplier">{t.review.supplier}</option>
          </Select>
        </Field>}
        {overriding && !note.trim() && <p className="text-xs text-warn">{t.exceptions.overrideNeedsNote}</p>}
        <div className="grid gap-2 border-t border-line pt-3 sm:grid-cols-2 xl:grid-cols-1">
          {canDecide && <>
            <Button variant="primary" className="h-auto min-h-10 justify-start whitespace-normal text-start" loading={busy === "approve"} disabled={!!busy || (overriding && !note.trim())} onClick={() => onDecide("approve")}>
              <Check className="h-4 w-4 shrink-0" aria-hidden />{t.exceptions.approve}
            </Button>
            <Button variant="danger" className="h-auto min-h-10 justify-start whitespace-normal text-start" loading={busy === "reject"} disabled={!!busy || !note.trim()} onClick={() => onDecide("reject")}>
              <X className="h-4 w-4 shrink-0" aria-hidden />{t.exceptions.reject}
            </Button>
          </>}
          {canRequestInfo && <Button className="h-auto min-h-10 justify-start whitespace-normal text-start" loading={busy === "request_info"} disabled={!!busy || !note.trim() || !target}
            onClick={() => onDecide("request_info")}><HelpCircle className="h-4 w-4 shrink-0" aria-hidden />{t.exceptions.requestInfo}</Button>}
          {canDecide && <Button className="h-auto min-h-10 justify-start whitespace-normal text-start" loading={busy === "escalate"} disabled={!!busy || !note.trim()}
            onClick={() => onDecide("escalate")}><ShieldAlert className="h-4 w-4 shrink-0" aria-hidden />{t.review.escalate}</Button>}
        </div>
      </>}
    </div>
  </Panel>;
}
