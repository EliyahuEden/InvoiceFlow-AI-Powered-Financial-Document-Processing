"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { dictionaries, type Dictionary, type Locale } from "./dictionaries";
import { LOCALE_COOKIE } from "./constants";

type Ctx = { locale: Locale; dir: "rtl" | "ltr"; t: Dictionary; setLocale: (l: Locale) => void };
const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ initial, children }: { initial: Locale; children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initial);
  const setLocale = useCallback((l: Locale) => {
    document.cookie = `${LOCALE_COOKIE}=${l}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = l;
    document.documentElement.dir = l === "he" ? "rtl" : "ltr";
    setLocaleState(l);
  }, []);
  const value = useMemo<Ctx>(
    () => ({ locale, dir: locale === "he" ? "rtl" : "ltr", t: dictionaries[locale], setLocale }),
    [locale, setLocale],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside provider");
  return ctx;
}

/** Pick the localized variant of an AI text object {he, en}, falling back to whatever exists. */
export function pickLang(v: Record<string, string> | string | null | undefined, locale: Locale): string {
  if (!v) return "";
  if (typeof v === "string") return v;
  return v[locale] ?? v.en ?? v.he ?? Object.values(v)[0] ?? "";
}
