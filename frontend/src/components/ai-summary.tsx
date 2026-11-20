"use client";

import { Lightbulb } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { findingMessage } from "@/lib/findings";
import { money } from "@/lib/format";
import type { AiSummary } from "@/lib/types";
import { ActionLabel, AiBlock, AiText, Citation, FindingTag, SecurityNotice } from "./domain";

/** Renders an investigation report: deterministic findings (solid) + AI explanation & citations (violet). */
export function AiSummaryView({ s, currency }: { s: AiSummary; currency?: string | null }) {
  const { t } = useI18n();
  let n = 0;
  return (
    <div className="space-y-4">
      <SecurityNotice items={s.security_notes ?? []} />
      <AiBlock mode={s.mode} title={t.exceptions.summary}>
        <h3 className="text-md font-semibold text-ink"><AiText value={s.headline} /></h3>
        <p className="mt-1 text-base leading-relaxed text-ink-2"><AiText value={s.summary} /></p>
        <div className="mt-4 space-y-4">
          {s.findings.map((f) => (
            <div key={f.type} className="rounded-md border border-line bg-surface p-3">
              <div className="flex flex-wrap items-center gap-2">
                <FindingTag type={f.type} severity={f.severity} />
                {f.amount_at_risk && <span className="text-xs text-ink-3">{t.recon.atRisk}: <b className="ltr text-danger">{money(f.amount_at_risk, currency)}</b></span>}
              </div>
              {/* the deterministic message is a verified result, the explanation is AI text */}
              <p className="mt-2 text-sm text-ink" dir="auto">{findingMessage(t, f)}</p>
              {Object.keys(f.explanation ?? {}).length > 0 && (
                <p className="mt-1.5 text-sm text-ai/90" dir="auto"><AiText value={f.explanation} /></p>
              )}
              <div className="mt-2.5 space-y-2">
                {f.citations?.length ? f.citations.map((c, i) => <Citation key={`${c.chunk_id}-${i}`} c={c} index={++n} />) :
                  <p className="text-xs text-ink-3">{t.ai.noCitation}</p>}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex gap-2 rounded-md bg-surface/70 p-3 text-sm">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-ai" />
          <div>
            <p className="font-medium text-ink"><ActionLabel action={s.ai_recommended_action ?? s.deterministic_action} /></p>
            <p className="text-ink-2"><AiText value={s.recommendation} /></p>
            <p className="mt-1 text-xs text-ink-3">{t.ai.confidence}: {s.confidence} · {s.evidence_count} {t.ai.sources.toLowerCase()} · {s.prompt_version}</p>
          </div>
        </div>
        {!!s.open_questions?.length && (
          <ul className="mt-3 list-disc space-y-1 ps-5 text-sm text-ink-2">{s.open_questions.map((q) => <li key={q} dir="auto">{q}</li>)}</ul>
        )}
      </AiBlock>
    </div>
  );
}
