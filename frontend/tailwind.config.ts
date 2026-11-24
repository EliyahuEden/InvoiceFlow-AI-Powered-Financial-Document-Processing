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
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        // Dense product scale (Geist runs a large x-height): 14px body, ~1.15 steps, rank by weight before size.
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        xs: ["0.75rem", { lineHeight: "1.05rem" }],
        sm: ["0.8125rem", { lineHeight: "1.2rem" }],
        base: ["0.875rem", { lineHeight: "1.35rem" }],
        md: ["0.9375rem", { lineHeight: "1.45rem" }],
        lg: ["1.0625rem", { lineHeight: "1.55rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.02em" }],
        "3xl": ["1.625rem", { lineHeight: "2.1rem", letterSpacing: "-0.02em" }],
        "4xl": ["1.875rem", { lineHeight: "2.3rem", letterSpacing: "-0.025em" }],
        figure: ["1.75rem", { lineHeight: "2.1rem", letterSpacing: "-0.025em" }],
      },
      borderRadius: {
        sm: "6px", DEFAULT: "var(--radius-control)", md: "8px", lg: "var(--radius-panel)", xl: "12px", "2xl": "12px", "3xl": "14px",
      },
      boxShadow: {
        raise: "var(--shadow-panel)",
        pop: "var(--shadow-pop)",
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
