"use client";

export type Theme = "light" | "dark";

export function currentTheme(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

/** Apply and remember the theme, and tell every listener (top bar icon, palette). */
export function setTheme(next: Theme) {
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("if_theme", next); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent<Theme>("if:theme", { detail: next }));
}
