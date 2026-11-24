import type { Config } from "tailwindcss";

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        primary: { DEFAULT: v("primary"), hover: v("primary-hover"), ink: v("primary-ink"), line: v("primary-line") },
        hero: { DEFAULT: v("hero"), wave: v("hero-wave") },
        surface: v("surface"),
        raised: v("raised"),
        sunken: v("sunken"),
        rail: { DEFAULT: v("rail"), ink: v("rail-ink"), "ink-2": v("rail-ink-2"), line: v("rail-line"), active: v("rail-active") },
        rule: v("rule"),
        ink: { DEFAULT: v("ink"), 2: v("ink-2"), 3: v("ink-3") },
        // hairlines: one colour per theme shown at a theme-set opacity (light on dark, dark on light)
        line: { DEFAULT: "rgb(var(--line) / calc(<alpha-value> * var(--line-a)))", strong: v("line-strong") },
        accent: { DEFAULT: v("accent"), soft: v("accent-soft"), ink: v("accent-ink") },
        ok: { DEFAULT: v("ok"), soft: v("ok-soft") },
        warn: { DEFAULT: v("warn"), soft: v("warn-soft") },
        danger: { DEFAULT: v("danger"), soft: v("danger-soft") },
        info: { DEFAULT: v("info"), soft: v("info-soft") },
        ai: { DEFAULT: v("ai"), soft: v("ai-soft"), line: v("ai-line") },
        hl: v("highlight"),
        copy: { invoice: v("copy-invoice"), po: v("copy-po"), gr: v("copy-gr") },
        glass: "rgb(var(--glass) / calc(<alpha-value> * var(--glass-a)))",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        // Assistant runs a small x-height, so the scale starts at 15px; headings carry weight (700-800) like the references.
        "2xs": ["0.71875rem", { lineHeight: "1rem" }],
        xs: ["0.78125rem", { lineHeight: "1.125rem" }],
        sm: ["0.84375rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.45rem" }],
        md: ["1.0625rem", { lineHeight: "1.55rem" }],
        lg: ["1.1875rem", { lineHeight: "1.65rem" }],
        xl: ["1.375rem", { lineHeight: "1.85rem", letterSpacing: "-0.01em" }],
        "2xl": ["1.75rem", { lineHeight: "2.2rem", letterSpacing: "-0.015em" }],
        "3xl": ["2.125rem", { lineHeight: "2.5rem", letterSpacing: "-0.02em" }],
        "4xl": ["2.625rem", { lineHeight: "2.9rem", letterSpacing: "-0.02em" }],
        figure: ["2.25rem", { lineHeight: "2.5rem", letterSpacing: "-0.02em" }],
        display: ["3.75rem", { lineHeight: "3.9rem", letterSpacing: "-0.03em" }],
      },
      borderRadius: {
        sm: "8px", DEFAULT: "var(--radius-control)", md: "10px", lg: "14px", xl: "var(--radius-panel)", "2xl": "var(--radius-hero)", "3xl": "26px",
      },
      boxShadow: {
        raise: "var(--shadow-panel)",
        pop: "var(--shadow-pop)",
        hero: "var(--shadow-hero)",
      },
      keyframes: {
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
        rise: { from: { opacity: "0", transform: "translateY(3px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: {
        shimmer: "shimmer 1.4s linear infinite",
        rise: "rise 160ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
