import type { Dictionary } from "./i18n/dictionaries";

type ParamValue = string | number | null | undefined;

/** A deterministic finding as returned by the API: either a stored discrepancy (key and params
 *  live in `evidence`) or a finding inside an investigation report (top level). */
export type FindingLike = {
  type: string;
  message: string;
  message_key?: string | null;
  params?: Record<string, ParamValue> | null;
  evidence?: Record<string, unknown> | null;
};

function displayValue(t: Dictionary, name: string, v: ParamValue): string {
  if (v === null || v === undefined || v === "") return name === "name" ? t.common.unknown : t.common.notPrinted;
  if (name === "status") return (t.status as Record<string, string>)[String(v)] ?? String(v);
  return String(v);
}

/**
 * Render the engine's message in the reader's language from its key and parameters.
 * Falls back to the stored English message for results produced before parameters existed,
 * or when a parameter is missing, so a placeholder is never shown.
 */
export function findingMessage(t: Dictionary, f: FindingLike): string {
  const ev = f.evidence ?? {};
  const key = f.message_key ?? (ev.message_key as string | undefined);
  const params = f.params ?? (ev.params as Record<string, ParamValue> | undefined);
  const template = key ? (t.findingMessage as Record<string, string>)[key] : undefined;
  if (!template || !params) return f.message;
  let complete = true;
  const out = template.replace(/\{(\w+)\}/g, (_, name: string) => {
    if (!(name in params)) complete = false;
    return displayValue(t, name, params[name]);
  });
  return complete ? out : f.message;
}
