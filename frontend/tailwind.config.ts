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
        sunken: v("sunken"),
        rail: { DEFAULT: v("rail"), ink: v("rail-ink"), "ink-2": v("rail-ink-2"), line: v("rail-line"), active: v("rail-active") },
        rule: v("rule"),
        ink: { DEFAULT: v("ink"), 2: v("ink-2"), 3: v("ink-3") },
        line: { DEFAULT: v("line"), strong: v("line-strong") },
        accent: { DEFAULT: v("accent"), soft: v("accent-soft"), ink: v("accent-ink") },
        ok: { DEFAULT: v("ok"), soft: v("ok-soft") },
        warn: { DEFAULT: v("warn"), soft: v("warn-soft") },
        danger: { DEFAULT: v("danger"), soft: v("danger-soft") },
        info: { DEFAULT: v("info"), soft: v("info-soft") },
        ai: { DEFAULT: v("ai"), soft: v("ai-soft"), line: v("ai-line") },
        hl: v("highlight"),
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      fontSize: {
        // Assistant runs a small x-height, so the scale starts at 15px; ~1.2 ratio.
        "2xs": ["0.71875rem", { lineHeight: "1rem" }],
        xs: ["0.78125rem", { lineHeight: "1.125rem" }],
        sm: ["0.84375rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.45rem" }],
        md: ["1.0625rem", { lineHeight: "1.55rem" }],
        lg: ["1.25rem", { lineHeight: "1.7rem" }],
        xl: ["1.5rem", { lineHeight: "1.9rem" }],
        "2xl": ["2rem", { lineHeight: "2.4rem" }],
        figure: ["2.5rem", { lineHeight: "2.8rem", letterSpacing: "-0.03em" }],
      },
      borderRadius: { sm: "10px", DEFAULT: "var(--radius-control)", md: "18px", lg: "var(--radius-panel)", xl: "var(--radius-hero)" },
      boxShadow: {
        raise: "var(--shadow-panel)",
        pop: "var(--shadow-pop)",
      },
      keyframes: {
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
        rise: { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: {
        shimmer: "shimmer 1.4s linear infinite",
        rise: "rise 180ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
