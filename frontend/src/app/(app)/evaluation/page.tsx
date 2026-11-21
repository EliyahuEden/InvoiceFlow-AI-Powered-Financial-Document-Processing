"use client";

import { ArrowDown, BookOpenCheck, ChevronDown, FileCheck2, FlaskConical, ListOrdered, Search, Terminal, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { BarList } from "@/components/charts";
import { Pill } from "@/components/domain";
import { RulesFirstReport } from "@/components/rules-first";
import { Segmented } from "@/components/list";
import { PageHeader } from "@/components/shell";
import { cx, EmptyState, ErrorState, Panel, PanelHeader, Skeleton, Table, Td, Th } from "@/components/ui";
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
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!notes?.length) return null;
  return (
    <div className="border-t border-line">
      <button className="flex w-full items-center gap-1.5 px-4 py-2 text-xs font-medium text-ink-2 hover:text-ink" aria-expanded={open} onClick={() => setOpen(!open)}>
        <ChevronDown className={cx("h-3.5 w-3.5 transition-transform", open && "rotate-180")} /> {t.evaluation.methodology} ({notes.length})
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
    <Panel id="report-extraction" className="scroll-mt-24">
      <PanelHeader title={t.evaluation.extraction} sub={`${r.dataset.evaluated}/${r.dataset.documents} documents · ${r.dataset.ocr} · system: rule-based baseline`}
        actions={<Pill tone="neutral">LLM (every invoice): {r.systems.llm?.skipped ? "not run" : "run"}</Pill>} />
      <div className="grid grid-cols-2 divide-line border-b border-line md:grid-cols-4 md:divide-x rtl:md:divide-x-reverse">
        <Stat label={t.evaluation.evaluatedDocs} value={String(r.dataset.evaluated)} hint={r.dataset.ocr} />
        <Stat label="Line items F1" value={pct(sys.line_items.f1)} hint={`P ${pct(sys.line_items.precision)} · R ${pct(sys.line_items.recall)}`} />
        <Stat label="Documents fully correct" value={pct(sys.documents_fully_correct)} />
        <Stat label="Latency p50" value={`${sys.latency_ms_p50} ms`} hint="text/OCR + extraction" />
      </div>
      <div className="grid grid-cols-1 gap-6 p-4 lg:grid-cols-2">
        <div><h3 className="mb-3 text-sm font-semibold">{t.evaluation.byLanguage}</h3><BarList items={pick("language")} format={(v) => pct(v)} max={1} color="var(--series-2)" /></div>
        <div><h3 className="mb-3 text-sm font-semibold">{t.evaluation.byLayout}</h3><BarList items={pick("layout")} format={(v) => pct(v)} max={1} color="var(--series-3)" /></div>
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
    <Panel id="report-rag" className="scroll-mt-24">
      <PanelHeader title={t.evaluation.rag}
        sub={`${r.dataset.questions} hand-written questions (${r.dataset.answerable} answerable) · ${r.dataset.documents} documents · ${r.models.embedding}${r.models.reranker ? ` + ${r.models.reranker}` : ""}`}
        actions={<Segmented value={strategy} onChange={setStrategy} options={strategies.map((s) => ({ value: s, label: s }))} />} />
      <Table>
        <thead><tr><Th>{t.evaluation.config}</Th><Th className="text-end">chunks</Th><Th className="text-end">R@1</Th><Th className="text-end">R@3</Th><Th className="text-end">R@5</Th>
          <Th className="text-end">MRR</Th><Th className="text-end">nDCG@5</Th><Th className="text-end">all@5</Th>
          {cats.map((c) => <Th key={c} className="text-end">MRR·{c}</Th>)}<Th className="text-end">p50</Th></tr></thead>
        <tbody>{rows.map((c: any) => (
          <tr key={c.chunking + c.name}>
            <Td className="whitespace-nowrap font-mono text-xs">{c.chunking}/{c.name}{r.best_config.name === c.name && r.best_config.chunking === c.chunking && <Pill tone="ok" className="ms-2">best</Pill>}</Td>
            <Td className="text-end num">{c.n_chunks}</Td>
            {["recall@1", "recall@3", "recall@5", "mrr", "ndcg@5", "all@5"].map((k) => <Td key={k} className="text-end num">{c[k].toFixed(3)}</Td>)}
            {cats.map((k) => <Td key={k} className="text-end num">{c.by_category[k]?.mrr?.toFixed(2) ?? "—"}</Td>)}
            <Td className="text-end num">{c.latency_ms_p50} ms</Td>
          </tr>))}</tbody>
      </Table>
      <div className="grid grid-cols-1 gap-4 border-t border-line p-4 md:grid-cols-2">
        {Object.entries(r.answers as Record<string, any>).map(([k, a]) => (
          <div key={k} className="rounded-md border border-line p-3">
            <p className="font-mono text-xs text-ink-2">{k} · clause chunks</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-ink-3">Answer correctness</dt><dd className="text-end font-medium num">{pct(a.answer_correctness)}</dd>
              <dt className="text-ink-3">Citation accuracy</dt><dd className="text-end font-medium num">{pct(a.citation_accuracy)}</dd>
              <dt className="text-ink-3">Abstention P / R</dt><dd className="text-end font-medium num"><span dir="ltr">{pct(a.abstention.precision)} / {pct(a.abstention.recall)}</span></dd>
              <dt className="text-ink-3">Injection parroting</dt><dd className="text-end font-medium num">{a.injection_parroting}</dd>
              <dt className="text-ink-3">Groundedness</dt><dd className="text-end text-xs">{a.groundedness}</dd>
            </dl>
          </div>
        ))}
      </div>
      {r.held_out && (
        <div className="border-t border-line p-4">
          <p className="text-sm font-semibold text-ink">Held-out questions</p>
          <p className="mt-0.5 text-xs text-ink-3">
            {r.held_out.dataset.questions} questions ({r.held_out.dataset.answerable} answerable), written before any held-out scoring and never used for tuning ·
            abstention threshold {r.held_out.abstain_logit} calibrated on the set above
          </p>
          <div className="mt-3 overflow-x-auto">
            <Table>
              <thead><tr><Th>{t.evaluation.config}</Th><Th className="text-end">R@1</Th><Th className="text-end">R@5</Th><Th className="text-end">MRR</Th><Th className="text-end">nDCG@5</Th></tr></thead>
              <tbody>{r.held_out.retrieval.map((c: any) => (
                <tr key={c.name}>
                  <Td className="whitespace-nowrap font-mono text-xs">{c.chunking}/{c.name}</Td>
                  {["recall@1", "recall@5", "mrr", "ndcg@5"].map((k) => <Td key={k} className="text-end num">{c[k].toFixed(3)}</Td>)}
                </tr>))}</tbody>
            </Table>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
            {Object.entries(r.held_out.answers as Record<string, any>).map(([k, a]) => (
              <dl key={k} className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-md border border-line p-3 text-sm">
                <dt className="col-span-2 font-mono text-xs text-ink-2">{k}</dt>
                <dt className="text-ink-3">Answer correctness</dt><dd className="text-end font-medium num">{pct(a.answer_correctness)}</dd>
                <dt className="text-ink-3">Citation accuracy</dt><dd className="text-end font-medium num">{pct(a.citation_accuracy)}</dd>
                <dt className="text-ink-3">Abstention P / R</dt><dd className="text-end font-medium num"><span dir="ltr">{pct(a.abstention.precision)} / {pct(a.abstention.recall)}</span></dd>
              </dl>
            ))}
          </div>
        </div>
      )}
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
    <Panel id="report-reconciliation" className="scroll-mt-24">
      <PanelHeader title={t.evaluation.reconciliation} sub={`${c.cases} controlled cases · engine ${r.engine_version}`} />
      <div className="grid grid-cols-2 divide-line border-b border-line md:grid-cols-4 md:divide-x rtl:md:divide-x-reverse">
        <Stat label="Exact finding-set match" value={pct(c.exact_finding_set_match)} />
        <Stat label="False alarms on clean invoices" value={pct(c.clean_case_false_alarm_rate)} hint={`${c.clean_cases} clean / near-miss cases`} />
        <Stat label="End-to-end (PDF → findings)" value={e.exact_scenarios} hint={`P ${pct(e.precision)} · R ${pct(e.recall)}`} />
        <Stat label="Finding types" value={String(c.per_type.length)} />
      </div>
      <div className="grid grid-cols-1 gap-5 p-4 lg:grid-cols-2">
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

type RetrievalRow = { name: string; chunking: string; mrr: number; "recall@5": number };

function Metric({ icon: Icon, label, value, hint, href }: {
  icon: LucideIcon; label: React.ReactNode; value: string; hint: React.ReactNode; href: string;
}) {
  return (
    <a href={href} className="command-metric flex min-w-0 items-start gap-3 p-4 text-ink hover:border-line-strong">
      <Icon className="mt-1 h-5 w-5 shrink-0 text-accent" aria-hidden />
      <div className="min-w-0">
        <p className="text-3xl font-semibold tracking-tight num"><bdi>{value}</bdi></p>
        <p className="mt-1 font-medium">{label}</p>
        <p className="mt-1 text-xs text-ink-2">{hint}</p>
      </div>
    </a>
  );
}

function InputChart({ groups }: { groups: Record<string, { n: number; field_accuracy: number }> }) {
  const { t } = useI18n();
  const keys = Object.keys(t.evaluation.inputNames) as (keyof typeof t.evaluation.inputNames)[];
  return (
    <Panel>
      <PanelHeader title={t.evaluation.byInput} sub={t.evaluation.baseline} />
      <div className="flex items-end gap-2 p-5">
        <div className="mb-12 flex h-32 flex-col justify-between text-xs text-ink-3 num" aria-hidden><bdi>100%</bdi><bdi>50%</bdi><bdi>0%</bdi></div>
        <ul className="grid min-w-0 flex-1 grid-cols-3 gap-2 sm:gap-4">
          {keys.map((k) => {
            const g = groups[`render:${k}`];
            if (!g) return null;
            return <li key={k} className="min-w-0 text-center">
              <div className="flex h-32 items-end justify-center border-b border-line-strong bg-sunken/40">
                <div className="relative w-3/5 max-w-24 rounded-t-md" style={{ height: `${g.field_accuracy * 100}%`, background: "var(--series-1)" }}>
                  <span className="absolute bottom-full start-1/2 mb-1 -translate-x-1/2 font-medium text-ink num rtl:translate-x-1/2"><bdi>{pct(g.field_accuracy)}</bdi></span>
                </div>
              </div>
              <p className="mt-2 text-sm font-medium">{t.evaluation.inputNames[k]}</p>
              <bdi className="text-xs text-ink-3">n = {g.n}</bdi>
            </li>;
          })}
        </ul>
      </div>
    </Panel>
  );
}

export default function EvaluationPage() {
  const { t, locale } = useI18n();
  const { data, error, mutate } = useApi<Results>("/api/evaluation/results");
  if (error) return <ErrorState message={t.common.error} onRetry={() => mutate()} retryLabel={t.common.retry} />;
  if (!data) return <Skeleton className="h-96 w-full" />;
  const a = data.available;
  const clauseRows = (a.rag?.configs as RetrievalRow[] | undefined)?.filter((c) => c.chunking === "clause") ?? [];
  const rerank = clauseRows.find((c) => c.name === "hybrid_rerank");
  const bm25 = clauseRows.find((c) => c.name === "bm25_plain");
  const endToEnd = a.reconciliation?.end_to_end;
  const retrievalSample = a.rag && `${a.rag.dataset.answerable} ${t.evaluation.answerable}`;
  const reports = [
    a.extraction && { key: "extraction", name: t.evaluation.extraction, sample: `${a.extraction.dataset.evaluated} ${t.evaluation.documents}`, source: a.extraction.dataset.source },
    a.rag && { key: "rag", name: t.evaluation.rag, sample: `${a.rag.dataset.questions} ${t.evaluation.questions}`, source: a.rag.dataset.source },
    a.reconciliation && { key: "reconciliation", name: t.evaluation.reconciliation, sample: `${a.reconciliation.controlled.cases} ${t.evaluation.controlled}`, source: a.reconciliation.engine_version },
  ].filter(Boolean);
  return (
    <div className="space-y-5">
      <PageHeader title={t.evaluation.hero} sub={t.evaluation.subtitle}
        actions={reports.length > 0 && <a className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface px-4 py-2 text-sm font-medium hover:bg-sunken" href="#benchmark-reports">
          <FlaskConical className="h-4 w-4" aria-hidden />{t.evaluation.methodology}<ArrowDown className="h-4 w-4" aria-hidden />
        </a>} />
      {reports.length > 0 && <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {a.extraction && <Metric icon={FileCheck2} href="#report-extraction"
            label={<>{t.evaluation.fieldAccuracy}{locale === "he" && <small className="ms-1 text-xs text-ink-2" lang="en">Field accuracy</small>}</>}
            value={pct(a.extraction.systems.rule_based.overall_field_accuracy)}
            hint={<>{a.extraction.dataset.evaluated} {t.evaluation.documents} × {a.extraction.fields.length} {t.invoice.fields.toLocaleLowerCase()}</>} />}
          {rerank && <Metric icon={Search} href="#report-rag" label="Recall@5" value={pct(rerank["recall@5"])}
            hint={<><bdi>{rerank.chunking}/{rerank.name}</bdi> · {retrievalSample}</>} />}
          {bm25 && <Metric icon={ListOrdered} href="#report-rag" label="MRR · BM25" value={bm25.mrr.toFixed(3)}
            hint={<><bdi>{bm25.chunking}/{bm25.name}</bdi> · {retrievalSample}</>} />}
          {endToEnd && <Metric icon={BookOpenCheck} href="#report-reconciliation" label={t.evaluation.precision} value={pct(endToEnd.precision)}
            hint={<>{endToEnd.tp} / {endToEnd.tp + endToEnd.fp} {t.evaluation.findings} · {endToEnd.documents} {t.evaluation.documents}</>} />}
        </div>
        <div className="grid items-stretch gap-4 lg:grid-cols-2">
          {a.extraction && <InputChart groups={a.extraction.systems.rule_based.groups} />}
          {clauseRows.length > 0 && <Panel>
            <PanelHeader title={t.evaluation.retrievalComparison} sub={<><bdi>Recall@5 · clause</bdi> · {retrievalSample}</>} />
            <div className="p-5"><BarList max={1} items={clauseRows.map((c) => ({ label: c.name, value: c["recall@5"] }))} format={pct} /></div>
          </Panel>}
        </div>
        <div id="benchmark-reports" className="grid scroll-mt-24 items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <Panel><PanelHeader title={t.evaluation.runs} />
            <Table><thead><tr><Th>{t.evaluation.report}</Th><Th>{t.evaluation.sample}</Th><Th>{t.evaluation.generated}</Th></tr></thead>
              <tbody>{reports.map((r) => <tr key={r.key}><Td><a className="font-medium text-accent hover:underline" href={`#report-${r.key}`}>{r.name}</a></Td>
                <Td>{r.sample}</Td><Td><time dateTime={a[r.key].generated_at}>{new Date(a[r.key].generated_at).toLocaleString(locale === "he" ? "he-IL" : "en-GB", {dateStyle: "medium", timeStyle: "short"})}</time></Td></tr>)}</tbody>
            </Table>
          </Panel>
          <Panel><PanelHeader title={t.evaluation.methodology} />
            <div className="space-y-2 px-5 py-4 text-sm text-ink-2">
              <p>{t.evaluation.dataset} · {t.evaluation.baseline}</p>
              {a.extraction?.systems.llm?.skipped && String(a.rag?.llm_answers).startsWith("not run") && <p>{t.evaluation.paidLimit}</p>}
              {reports.map((r) => <p key={r.key} className="break-words"><a href={`#report-${r.key}`} className="underline underline-offset-2">{r.name}</a> · <bdi>{r.source}</bdi></p>)}
            </div>
          </Panel>
        </div>
      </>}
      {Object.keys(a).length === 0 && <Panel><EmptyState title={t.evaluation.notRun} body="python eval/run_rag_eval.py · run_extraction_eval.py · run_reconciliation_eval.py" /></Panel>}
      {a.extraction && <Extraction r={a.extraction} />}
      {a.extraction && <RulesFirstReport r={a.extraction} />}
      {a.rag && <Rag r={a.rag} />}
      {a.reconciliation && <Recon r={a.reconciliation} />}
    </div>
  );
}
