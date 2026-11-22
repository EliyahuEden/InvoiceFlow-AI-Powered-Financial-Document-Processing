export type Source = { page?: number | null; text?: string | null; bbox?: number[] | null; verified?: boolean; corrected_by?: string };

export type PriorityReason = { code: string; params: Record<string, string | number | null> };
export type ReviewQueueItem = {
  exception_id: string; invoice_id: string; invoice_number: string | null;
  supplier_id: string | null; supplier_name: string | null; supplier_name_en: string | null;
  total: string | null; currency: string | null; amount_at_risk: string;
  amount_at_risk_base?: string | null; fx_as_of?: string | null; // shekel value for ranking (Bank of Israel rate)
  due_date: string | null; due_in_days: number | null; status: string; finding_types: string[];
  priority: { level: string; reasons: PriorityReason[]; rank: number };
  proposed_action: string | null; has_ai_summary: boolean; escalated_by: string | null; created_at: string;
};
export type ReviewSummary = {
  needs_review: number; by_level: { critical: number; high: number; normal: number };
  value_under_review: string; amount_at_risk: string; currency: string;
  ready_for_approval: number; awaiting_info: number; escalated: number; processing: number;
  due_soon: number; overdue: number; top: ReviewQueueItem[];
  totals_by_currency?: { currency: string | null; value_under_review: string; amount_at_risk: string }[];
};
export type ReviewNext = { item: ReviewQueueItem | null; position: number; total: number };
export type NextResp = ReviewNext;

export type InvoiceLine = {
  id: string; line_no: number; sku: string | null; description: string; quantity: string | null; unit_price: string | null;
  discount: string | null; line_total: string | null; source: Source;
};

export type Discrepancy = {
  id: string; type: string; severity: string; message: string; expected: string | null; actual: string | null;
  difference: string | null; status: string; invoice_line_id: string | null; po_line_id: string | null;
  evidence: Record<string, unknown> & { amount_at_risk?: string | null; invoice_line_no?: number | null;
    message_key?: string; params?: Record<string, string | number | null> };
};

export type LineMatch = {
  invoice_line_no: number; invoice_line_id: string | null; po_line_id: string | null; po_line_no: number | null;
  method: "sku" | "description" | "ambiguous" | "none"; score: number;
  candidates: { po_line_id: string; po_line_no: number; description: string; unit_price: string; score: number }[];
};

export type InvoiceDetail = {
  id: string; status: string; invoice_number: string | null; supplier_id: string | null; supplier_name: string | null;
  supplier_name_en: string | null; supplier_matched: boolean; invoice_date: string | null; currency: string | null;
  total: string | null; po_reference: string | null; language: string | null; extraction_method: string | null;
  created_at: string; filename: string | null; text_method: string | null; security_flag: boolean;
  supplier_name_raw: string | null; supplier_tax_id_raw: string | null; due_date: string | null; payment_terms: string | null;
  allocation_number: string | null;
  subtotal: string | null; discount_total: string | null; tax_total: string | null; tax_rate: string | null;
  field_sources: Record<string, Source>; missing_fields: string[];
  validation_warnings: { code: string; message: string; severity?: string; field?: string; snippets?: string[] }[];
  revision?: string;
  lines: InvoiceLine[];
  document: { id: string; filename: string; mime_type: string; page_count: number | null; text_method: string | null;
    language: string | null; status: string; error: string | null; size_bytes: number; sha256: string } | null;
  supplier: { id: string; name: string; name_en: string | null; tax_id: string | null } | null;
  purchase_order: { id: string; po_number: string; currency: string; status: string;
    lines: { id: string; line_no: number; sku: string | null; description: string; quantity: string; unit_price: string; received: string }[] } | null;
  reconciliation: { id: string; outcome: string; mode: string; engine_version: string; created_at: string;
    tolerances: Record<string, string | number>; checks: { check: string; passed: boolean; detail: string }[];
    line_matches: LineMatch[]; supplier_match: Record<string, unknown> | null; po_match: Record<string, unknown> | null;
    triggered_by: string } | null;
  discrepancies: Discrepancy[];
  exception: { id: string; status: string; title: string; proposed_action: string | null; has_ai_summary: boolean } | null;
  approvals: { id: string; step: number; required_role: string; status: string; decided_by: string | null; decided_at: string | null; comment: string | null }[];
  agent_runs: { id: string; status: string; mode: string; created_at: string }[];
  job: { id: string; status: string; progress: number; message: string | null; attempts: number; error: string | null } | null;
};

export type AiSummary = {
  stale?: boolean;
  headline: Record<string, string>; summary: Record<string, string>; recommendation: Record<string, string>;
  confidence: string; mode: string; deterministic_action: string; ai_recommended_action?: string;
  findings: { type: string; severity: string; message: string; amount_at_risk?: string | null;
    message_key?: string | null; params?: Record<string, string | number | null> | null;
    explanation: Record<string, string>; citations: import("@/components/domain").CitationT[] }[];
  security_notes: { code: string; message: string; snippets?: string[] }[];
  open_questions?: string[]; disclaimer: string; generated_at: string; evidence_count: number; prompt_version: string;
};
