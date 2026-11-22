/**
 * The translated name of a value that comes from the backend (a status, role, finding type, action...).
 *
 * Replaces `(t.status as Record<string, string>)[value]`, which returned `undefined` (a blank pill) for any value the
 * dictionary did not know yet, and an inherited function for keys like "toString". Only the dictionary's own keys
 * count; an unknown value falls back to `fallback`, or to the value itself made readable ("on_hold" -> "on hold").
 */
export function label(dict: Readonly<Record<string, string>>, key: string | null | undefined, fallback?: string): string {
  if (key === null || key === undefined || key === "") return fallback ?? "—";
  if (Object.prototype.hasOwnProperty.call(dict, key)) return dict[key] as string;
  return fallback ?? key.replaceAll("_", " ");
}
