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

/**
 * The reviewer's language for a stored, English-only backend sentence (the case's proposed-action detail). The backend
 * saves the English text when it opens a case, so we find which finding's sentence it is in the English dictionary
 * (kept word-for-word equal to ACTION_FOR_FINDING in backend/app/services/reconciliation/service.py) and show that
 * finding's sentence in the current language. Unknown text is returned unchanged.
 */
export function translateStored(enDict: Readonly<Record<string, string>>, dict: Readonly<Record<string, string>>,
  text: string | null | undefined): string | null | undefined {
  if (!text) return text;
  const key = Object.keys(enDict).find((k) => enDict[k] === text);
  return key && Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : text;
}
