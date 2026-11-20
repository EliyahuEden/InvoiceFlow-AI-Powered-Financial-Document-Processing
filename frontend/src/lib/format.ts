import type { Locale } from "./i18n/dictionaries";

const SYMBOL: Record<string, string> = { ILS: "₪", USD: "$", EUR: "€", GBP: "£" };

/** Format a decimal string without floating-point arithmetic (amounts arrive as strings). */
export function money(value: string | null | undefined, currency?: string | null, locale: Locale = "he"): string {
  if (value === null || value === undefined || value === "") return "—";
  const neg = value.startsWith("-");
  const [int, frac = ""] = value.replace("-", "").split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const body = `${grouped}.${(frac + "00").slice(0, 2)}`;
  const sym = currency ? SYMBOL[currency] ?? `${currency} ` : "";
  void locale;
  return `${neg ? "−" : ""}${sym}${body}`;
}

export function num(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const s = String(value);
  const [int, frac] = s.split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return frac && !/^0+$/.test(frac) ? `${grouped}.${frac.replace(/0+$/, "")}` : grouped;
}

export function date(value: string | null | undefined, locale: Locale): string {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return d.toLocaleDateString(locale === "he" ? "he-IL" : "en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function dateTime(value: string | null | undefined, locale: Locale): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(locale === "he" ? "he-IL" : "en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export function relative(value: string, locale: Locale): string {
  const diff = (Date.now() - new Date(value).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (diff < 60) return rtf.format(-Math.round(diff), "second");
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), "minute");
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), "hour");
  return rtf.format(-Math.round(diff / 86400), "day");
}

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
