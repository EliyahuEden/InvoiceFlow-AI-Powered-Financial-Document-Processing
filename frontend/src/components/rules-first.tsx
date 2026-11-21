"use client";

import { BarList } from "@/components/charts";
import { Panel, PanelHeader } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

/* eslint-disable @typescript-eslint/no-explicit-any */
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="px-4 py-3">
      <p className="text-sm text-ink-2">{label}</p>
      <p className="mt-1 text-xl font-semibold text-ink num" dir="ltr">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

/** Rules-first extraction from the extraction benchmark: how many invoices the free rules
 *  handed to a model, whether those were the ones the rules got wrong, and (only when a model
 *  run exists) the measured accuracy and token use. Nothing is shown that the report lacks. */
export function RulesFirstReport({ r }: { r: any }) {
  const { t, locale } = useI18n();
  const rt = t.evaluation.rulesFirst;
  const router = r?.systems?.rule_based?.rules_first_router;
  if (!router) return null;
  const rf = r.systems.rules_first;
  const measured = rf && !rf.skipped && typeof rf.overall_field_accuracy === "number";
  const num = new Intl.NumberFormat(locale === "he" ? "he-IL" : "en-US");
  const gaps = Object.entries(router.gap_counts as Record<string, number>).map(([label, value]) => ({ label, value }));
  const model = r.llm ? [r.llm.model, r.llm.endpoint].filter(Boolean).join(" · ") : "";
  return (
    <Panel id="report-rules-first" className="scroll-mt-24">
      <PanelHeader title={rt.title} sub={rt.sub} />
      <div className="grid grid-cols-2 divide-line border-b border-line md:grid-cols-4 md:divide-x rtl:md:divide-x-reverse">
        <Stat label={rt.sent} value={`${router.sent_to_llm} / ${router.documents}`}
          hint={rt.sentHint.replace("{share}", pct(router.share_sent_to_llm))} />
        <Stat label={rt.wrong} value={`${router.errors_sent} / ${router.sent_to_llm}`}
          hint={rt.wrongHint.replace("{n}", String(router.with_errors))} />
        <Stat label={rt.accuracy}
          value={measured ? `${pct(r.systems.rule_based.overall_field_accuracy)} → ${pct(rf.overall_field_accuracy)}` : "—"}
          hint={measured ? rt.accuracyHint : rt.pending} />
        {measured && rf.tokens?.per_call
          ? <Stat label={rt.tokens} value={num.format(rf.tokens.per_call)}
              hint={[model, rf.llm_errors ? rt.failed.replace("{n}", String(rf.llm_errors)) : ""].filter(Boolean).join(" · ")} />
          : <Stat label={rt.tokens} value="—" />}
      </div>
      {gaps.length > 0 && (
        <div className="p-4">
          <h3 className="mb-3 text-sm font-semibold">{rt.why}</h3>
          <BarList items={gaps} max={router.sent_to_llm} color="var(--series-4)" />
        </div>
      )}
    </Panel>
  );
}
