/**
 * Shapes of the benchmark files in eval/results/*_latest.json, as served by GET /api/evaluation/results.
 * Written from the files themselves; anything a run can leave out is optional, so the page has to handle it.
 */

type Meta = { generated_at: string; git_rev?: string | null; command: string; notes?: string[] };
export type Prf = { precision: number | null; recall: number | null; f1?: number | null };

export type ExtractionSystem = {
  documents_fully_correct: number | null;
  latency_ms_p50: number | null;
  line_items: Prf;
  groups: Record<string, { field_accuracy: number; n: number }>;
  per_field: Record<string, Prf & { accuracy: number | null }>;
  missing_field_handling: Record<string, { absent_in_document: number; correctly_null: number }>;
  error_examples: { file: string; field: string; expected: string | null; predicted: string | null }[];
  overall_field_accuracy?: number | null;
  rules_first_router?: RulesFirstRouter;
  llm_calls?: number;
  llm_errors?: number;
  tokens?: { per_call?: number } | null;
  skipped?: boolean;
  carried_over?: { llm?: LlmInfo | null };
};
export type LlmInfo = { model?: string | null; provider?: string | null; endpoint?: string | null };
export type RulesFirstRouter = {
  documents: number; sent_to_llm: number; share_sent_to_llm: number; gap_counts: Record<string, number>;
  with_errors?: number; errors_sent?: number;
};
export type ExtractionResult = Meta & {
  dataset: { documents: number; evaluated: number; ocr: string; source?: string };
  fields: string[];
  systems: { rule_based: ExtractionSystem; rules_first?: ExtractionSystem; llm?: Partial<ExtractionSystem> & { skipped?: boolean } };
  llm?: LlmInfo | null;
};

export type RetrievalRow = {
  name: string; chunking: string; n_chunks?: number; latency_ms_p50?: number | null;
  "recall@1"?: number; "recall@3"?: number; "recall@5"?: number; mrr?: number; "ndcg@5"?: number; "all@5"?: number;
  by_category?: Record<string, { mrr?: number }>;
};
export type AnswerScore = {
  answer_correctness: number | null; citation_accuracy: number | null;
  abstention?: { precision: number | null; recall: number | null };
  injection_parroting?: string; groundedness?: string;
};
export type RagResult = Meta & {
  dataset: { questions: number; answerable: number; documents: number; source?: string };
  models: { embedding: string; reranker?: string | null };
  configs: RetrievalRow[];
  best_config?: { name: string; chunking: string } | null;
  answers: Record<string, AnswerScore>;
  held_out?: {
    dataset: { questions: number; answerable: number }; abstain_logit?: number;
    retrieval: RetrievalRow[]; answers: Record<string, AnswerScore>;
  };
  llm_answers?: string;
};

export type ReconResult = Meta & {
  engine_version: string;
  controlled: {
    cases: number; clean_cases: number; exact_finding_set_match: number; clean_case_false_alarm_rate: number;
    per_type: { type: string; tp: number; fp: number; fn: number; precision: number | null; recall: number | null }[];
  };
  end_to_end: {
    exact_scenarios: string; precision: number | null; recall: number | null; tp: number; fp: number; documents: number;
    rows: { file: string; expected: string[]; got: string[]; exact: boolean }[];
  };
};

export type EvaluationResults = {
  available: { extraction?: ExtractionResult; rag?: RagResult; reconciliation?: ReconResult; agent?: unknown };
};

/** A metric with a fixed number of decimals, or a dash when a run did not produce it. */
export function fixed(v: number | null | undefined, digits: number): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits);
}
