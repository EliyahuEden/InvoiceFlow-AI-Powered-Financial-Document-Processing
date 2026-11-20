"use client";

import { ChevronDown, Terminal } from "lucide-react";
import { useState } from "react";
import { BarList, Bars } from "@/components/charts";
import { Pill } from "@/components/domain";
import { Segmented } from "@/components/list";
import { PageHeader } from "@/components/shell";
import { cx, EmptyState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Results = { available: Record<string, any> };

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`);

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="px-4 py-3">
      <p className="text-sm text-ink-2">{label}</p>
      <p className="mt-1 text-xl font-semibold text-ink num">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

function Meta({ r }: { r: any }) {
  const { locale, t } = useI18n();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-2.5 text-xs text-ink-3">
      <span>{dateTime(r.generated_at, locale)}{r.git_rev && ` · ${r.git_rev}`}</span>
      <span className="inline-flex min-w-0 items-center gap-1.5"><Terminal className="h-3.5 w-3.5 shrink-0" />{t.evaluation.command}:
        <code className="truncate font-mono text-ink-2" dir="ltr">{r.command}</code></span>
    </div>
  );
}

function Notes({ notes }: { notes?: string[] }) {
  const [open, setOpen] = useState(false);
  if (!notes?.length) return null;
  return (
    <div className="border-t border-line">
      <button className="flex w-full items-center gap-1.5 px-4 py-2 text-xs font-medium text-ink-2 hover:text-ink" onClick={() => setOpen(!open)}>
        <ChevronDown className={cx("h-3.5 w-3.5 transition-transform", open && "rotate-180")} /> Methodology & limitations ({notes.length})
      </button>
      {open && <ul className="list-disc space-y-1 px-4 pb-3 ps-8 text-xs text-ink-2" dir="ltr">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    </div>
  );
}

function Extraction({ r }: { r: any }) {
  const { t } = useI18n();
  const sys = r.systems.rule_based;
  const groups = Object.entries(sys.groups as Record<string, { field_accuracy: number; n: number }>);
  const pick = (prefix: string) => groups.filter(([k]) => k.startsWith(prefix)).map(([k, v]) => ({ label: `${k.split(":")[1]} (n=${v.n})`, value: v.field_accuracy }));
  return (
    <Panel>
      <PanelHeader title={t.evaluation.extraction} sub={`${r.dataset.evaluated}/${r.dataset.documents} documents · ${r.dataset.ocr} · system: rule-based baseline`}
        actions={<Pill tone="neutral">LLM: {r.systems.llm?.skipped ? "not run" : "run"}</Pill>} />
      <div className="grid grid-cols-2 divide-line border-b border-line md:grid-cols-4 md:divide-x rtl:md:divide-x-reverse">
        <Stat label="Field accuracy" value={pct(sys.overall_field_accuracy)} />
        <Stat label="Line items F1" value={pct(sys.line_items.f1)} hint={`P ${pct(sys.line_items.precision)} · R ${pct(sys.line_items.recall)}`} />
        <Stat label="Documents fully correct" value={pct(sys.documents_fully_correct)} />
        <Stat label="Latency p50" value={`${sys.latency_ms_p50} ms`} hint="text/OCR + extraction" />
      </div>
      <div className="grid gap-6 p-4 lg:grid-cols-3">
        <div><h3 className="mb-3 text-sm font-semibold">By rendering</h3><BarList items={pick("render")} format={(v) => pct(v)} max={1} /></div>
        <div><h3 className="mb-3 text-sm font-semibold">{t.evaluation.byLanguage}</h3><BarList items={pick("language")} format={(v) => pct(v)} max={1} color="var(--series-2)" /></div>
        <div><h3 className="mb-3 text-sm font-semibold">Layout (seen vs held-out)</h3><BarList items={pick("layout")} format={(v) => pct(v)} max={1} color="var(--series-3)" /></div>
      </div>
      <Table>
        <thead><tr><Th>{t.evaluation.field}</Th><Th className="text-end">{t.evaluation.accuracy}</Th><Th className="text-end">Precision</Th>
          <Th className="text-end">Recall</Th><Th className="text-end">F1</Th><Th className="text-end">Absent → null</Th></tr></thead>
        <tbody>{Object.entries(sys.per_field as Record<string, any>).map(([f, m]) => {
          const miss = sys.missing_field_handling[f];
          return (
            <tr key={f}>
              <Td className="font-mono text-xs">{f}</Td>
              <Td className="text-end num">{pct(m.accuracy)}</Td><Td className="text-end num">{pct(m.precision)}</Td>
              <Td className="text-end num">{pct(m.recall)}</Td><Td className="text-end num">{pct(m.f1)}</Td>
              <Td className="text-end num">{miss ? `${miss.correctly_null}/${miss.absent_in_document}` : "—"}</Td>
            </tr>);
        })}</tbody>
      </Table>
      <details className="border-t border-line px-4 py-2 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-ink-2">Error examples ({sys.error_examples.length})</summary>
        <Table className="mt-2"><tbody>{sys.error_examples.map((e: any, i: number) => (
          <tr key={i}><Td className="font-mono text-2xs">{e.file.replace("docs/", "")}</Td><Td className="font-mono text-xs">{e.field}</Td>
            <Td className="text-xs" dir="auto">{e.expected ?? "∅"}</Td><Td className="text-xs text-danger" dir="auto">{e.predicted ?? "∅"}</Td></tr>))}</tbody></Table>
      </details>
      <Notes notes={r.notes} /><Meta r={r} />
    </Panel>
  );
}

function Rag({ r }: { r: any }) {
  const { t } = useI18n();
  const strategies = Array.from(new Set(r.configs.map((c: any) => c.chunking))) as string[];
  const [strategy, setStrategy] = useState<string>(strategies.includes("clause") ? "clause" : strategies[0]);
  const rows = r.configs.filter((c: any) => c.chunking === strategy);
  const cats = ["he", "en", "mixed", "cross_lingual", "multi_doc", "conflicting"];
  return (
    <Panel>
      <PanelHeader title={t.evaluation.rag}
        sub={`${r.dataset.questions} hand-written questions (${r.dataset.answerable} answerable) · ${r.dataset.documents} documents · ${r.models.embedding}${r.models.reranker ? ` + ${r.models.reranker}` : ""}`}
        actions={<Segmented value={strategy} onChange={setStrategy} options={strategies.map((s) => ({ value: s, label: s }))} />} />
      <div className="p-4">
        <Bars xKey="name" height={260} data={rows.map((c: any) => ({ name: c.name, mrr: c.mrr, r1: c["recall@1"], r5: c["recall@5"], ndcg: c["ndcg@5"] }))}
          series={[{ key: "r1", label: "Recall@1" }, { key: "r5", label: "Recall@5" }, { key: "mrr", label: "MRR" }, { key: "ndcg", label: "nDCG@5" }]}
          domain={[0, 1]} format={(v) => v.toFixed(2)} />
      </div>
      <Table>
        <thead><tr><Th>{t.evaluation.config}</Th><Th className="text-end">chunks</Th><Th className="text-end">R@1</Th><Th className="text-end">R@3</Th><Th className="text-end">R@5</Th>
          <Th className="text-end">MRR</Th><Th className="text-end">nDCG@5</Th><Th className="text-end">all@5</Th>
          {cats.map((c) => <Th key={c} className="text-end">MRR·{c}</Th>)}<Th className="text-end">p50</Th></tr></thead>
        <tbody>{r.configs.map((c: any) => (
          <tr key={c.chunking + c.name} className={c.chunking === strategy ? "" : "text-ink-3"}>
            <Td className="whitespace-nowrap font-mono text-xs">{c.chunking}/{c.name}{r.best_config.name === c.name && r.best_config.chunking === c.chunking && <Pill tone="ok" className="ms-2">best</Pill>}</Td>
            <Td className="text-end num">{c.n_chunks}</Td>
            {["recall@1", "recall@3", "recall@5", "mrr", "ndcg@5", "all@5"].map((k) => <Td key={k} className="text-end num">{c[k].toFixed(3)}</Td>)}
            {cats.map((k) => <Td key={k} className="text-end num">{c.by_category[k]?.mrr?.toFixed(2) ?? "—"}</Td>)}
            <Td className="text-end num">{c.latency_ms_p50} ms</Td>
          </tr>))}</tbody>
      </Table>
      <div className="grid gap-4 border-t border-line p-4 md:grid-cols-2">
        {Object.entries(r.answers as Record<string, any>).map(([k, a]) => (
          <div key={k} className="rounded-md border border-line p-3">
            <p className="font-mono text-xs text-ink-2">{k} · clause chunks</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-ink-3">Answer correctness</dt><dd className="text-end font-medium num">{pct(a.answer_correctness)}</dd>
              <dt className="text-ink-3">Citation accuracy</dt><dd className="text-end font-medium num">{pct(a.citation_accuracy)}</dd>
              <dt className="text-ink-3">Abstention P / R</dt><dd className="text-end font-medium num">{pct(a.abstention.precision)} / {pct(a.abstention.recall)}</dd>
              <dt className="text-ink-3">Injection parroting</dt><dd className="text-end font-medium num">{a.injection_parroting}</dd>
              <dt className="text-ink-3">Groundedness</dt><dd className="text-end text-xs">{a.groundedness}</dd>
            </dl>
          </div>
        ))}
      </div>
      <p className="border-t border-line px-4 py-2 text-xs text-ink-3">LLM answers: {r.llm_answers}</p>
      <Notes notes={r.notes} /><Meta r={r} />
    </Panel>
  );
}

function Recon({ r }: { r: any }) {
  const { t } = useI18n();
  const c = r.controlled;
  const e = r.end_to_end;
  return (
    <Panel>
      <PanelHeader title={t.evaluation.reconciliation} sub={`${c.cases} controlled cases · engine ${r.engine_version}`} />
      <div className="grid grid-cols-2 divide-line border-b border-line md:grid-cols-4 md:divide-x rtl:md:divide-x-reverse">
        <Stat label="Exact finding-set match" value={pct(c.exact_finding_set_match)} />
        <Stat label="False alarms on clean invoices" value={pct(c.clean_case_false_alarm_rate)} hint={`${c.clean_cases} clean / near-miss cases`} />
        <Stat label="End-to-end (PDF → findings)" value={e.exact_scenarios} hint={`P ${pct(e.precision)} · R ${pct(e.recall)}`} />
        <Stat label="Finding types" value={String(c.per_type.length)} />
      </div>
      <div className="grid gap-5 p-4 lg:grid-cols-2">
        <Table>
          <thead><tr><Th>Finding type</Th><Th className="text-end">TP</Th><Th className="text-end">FP</Th><Th className="text-end">FN</Th><Th className="text-end">Precision</Th><Th className="text-end">Recall</Th></tr></thead>
          <tbody>{c.per_type.map((x: any) => (
            <tr key={x.type}><Td className="font-mono text-xs">{x.type}</Td><Td className="text-end num">{x.tp}</Td><Td className="text-end num">{x.fp}</Td>
              <Td className="text-end num">{x.fn}</Td><Td className="text-end num">{pct(x.precision)}</Td><Td className="text-end num">{pct(x.recall)}</Td></tr>))}</tbody>
        </Table>
        <Table>
          <thead><tr><Th>End-to-end document</Th><Th>Expected</Th><Th>Got</Th></tr></thead>
          <tbody>{e.rows.map((x: any) => (
            <tr key={x.file} className={x.exact ? "" : "bg-danger-soft/40"}>
              <Td className="font-mono text-2xs">{x.file.replace("invoices/", "")}</Td>
              <Td className="font-mono text-2xs">{x.expected.join(", ") || "∅"}</Td>
              <Td className="font-mono text-2xs">{x.got.join(", ") || "∅"}</Td>
            </tr>))}</tbody>
        </Table>
      </div>
      <Notes notes={r.notes} /><Meta r={r} />
    </Panel>
  );
}

export default function EvaluationPage() {
  const { t } = useI18n();
  const { data } = useApi<Results>("/api/evaluation/results");
  if (!data) return <Skeleton className="h-96 w-full" />;
  const a = data.available;
  return (
    <div className="space-y-5">
      <PageHeader title={t.evaluation.title} sub={t.evaluation.subtitle} />
      {Object.keys(a).length === 0 && <Panel><EmptyState title={t.evaluation.notRun} body="python eval/run_rag_eval.py · run_extraction_eval.py · run_reconciliation_eval.py" /></Panel>}
      {a.extraction && <Extraction r={a.extraction} />}
      {a.rag && <Rag r={a.rag} />}
      {a.reconciliation && <Recon r={a.reconciliation} />}
    </div>
  );
}
