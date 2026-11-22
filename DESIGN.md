---
"name": "InvoiceFlow"
"description": "Modern Financial Command Center: a calm, neutral financial-operations workspace with a navy accent."
"colors":
  "bg": "rgb(247 247 248)"
  "surface": "rgb(255 255 255)"
  "sunken": "rgb(243 244 246)"
  "ink": "rgb(23 23 23)"
  "ink-2": "rgb(82 82 91)"
  "ink-3": "rgb(107 107 116)"
  "line": "rgb(228 228 231)"
  "line-strong": "rgb(161 161 170)"
  "rule": "rgb(206 217 240)"
  "accent": "rgb(44 65 126)"
  "accent-soft": "rgb(226 234 255)"
  "accent-ink": "rgb(25 43 94)"
  "primary": "rgb(17 19 25)"
  "primary-hover": "rgb(38 44 58)"
  "primary-ink": "rgb(255 255 255)"
  "primary-line": "rgb(17 19 25)"
  "ok": "rgb(17 113 81)"
  "ok-soft": "rgb(220 245 234)"
  "warn": "rgb(149 75 15)"
  "warn-soft": "rgb(255 239 212)"
  "danger": "rgb(167 39 39)"
  "danger-soft": "rgb(255 228 225)"
  "info": "rgb(48 75 133)"
  "info-soft": "rgb(229 237 255)"
  "ai": "rgb(44 65 126)"
  "ai-soft": "rgb(238 241 248)"
  "ai-line": "rgb(214 220 235)"
  "highlight": "rgb(219 162 16)"
  "rail": "rgb(244 244 245)"
  "rail-ink": "rgb(21 31 51)"
  "rail-ink-2": "rgb(66 84 118)"
  "rail-line": "rgb(200 213 240)"
  "rail-active": "rgb(255 255 255)"
  "atmosphere-a": "rgb(247 247 248)"
  "atmosphere-b": "rgb(247 247 248)"
  "hero": "rgb(255 255 255)"
  "hero-wave": "rgb(228 228 231)"
  "series-1": "#4369bb"
  "series-2": "#b27625"
  "series-3": "#21856b"
  "series-4": "#697e9f"
  "chart-grid": "#d9e3f4"
  "chart-axis": "#556684"
  "dark-bg": "rgb(20 20 21)"
  "dark-surface": "rgb(25 25 27)"
  "dark-sunken": "rgb(35 35 37)"
  "dark-ink": "rgb(237 237 237)"
  "dark-ink-2": "rgb(161 161 166)"
  "dark-ink-3": "rgb(138 138 144)"
  "dark-line": "rgb(46 46 50)"
  "dark-line-strong": "rgb(107 128 165)"
  "dark-rule": "rgb(57 75 108)"
  "dark-accent": "rgb(169 193 255)"
  "dark-accent-soft": "rgb(39 55 89)"
  "dark-accent-ink": "rgb(202 217 255)"
  "dark-primary": "rgb(8 12 21)"
  "dark-primary-hover": "rgb(21 31 49)"
  "dark-primary-ink": "rgb(246 249 255)"
  "dark-primary-line": "rgb(107 128 165)"
  "dark-ok": "rgb(116 220 175)"
  "dark-ok-soft": "rgb(23 57 48)"
  "dark-warn": "rgb(246 193 120)"
  "dark-warn-soft": "rgb(66 48 29)"
  "dark-danger": "rgb(255 159 148)"
  "dark-danger-soft": "rgb(73 38 42)"
  "dark-info": "rgb(167 195 255)"
  "dark-info-soft": "rgb(38 55 89)"
  "dark-ai": "rgb(169 193 255)"
  "dark-ai-soft": "rgb(33 41 61)"
  "dark-ai-line": "rgb(112 86 155)"
  "dark-highlight": "rgb(245 193 68)"
  "dark-rail": "rgb(15 15 16)"
  "dark-rail-ink": "rgb(232 239 255)"
  "dark-rail-ink-2": "rgb(168 187 219)"
  "dark-rail-line": "rgb(57 75 108)"
  "dark-rail-active": "rgb(45 63 97)"
  "dark-atmosphere-a": "rgb(20 20 21)"
  "dark-atmosphere-b": "rgb(20 20 21)"
  "dark-hero": "rgb(25 25 27)"
  "dark-hero-wave": "rgb(46 46 50)"
  "dark-series-1": "#9bbaff"
  "dark-series-2": "#e2b06c"
  "dark-series-3": "#79ceb0"
  "dark-series-4": "#b0bfd9"
  "dark-chart-grid": "#354969"
  "dark-chart-axis": "#9dafcd"
"typography":
  "body": {"fontFamily": "Assistant, system-ui, sans-serif", "fontSize": "0.9375rem", "lineHeight": "1.45rem"}
  "section-title": {"fontFamily": "Assistant", "fontSize": "1.25rem", "fontWeight": 600, "letterSpacing": "-0.025em"}
  "page-title": {"fontFamily": "Assistant", "fontSize": "2.25rem", "fontWeight": 600, "letterSpacing": "-0.025em"}
  "figure": {"fontFamily": "Assistant", "fontSize": "2.5rem", "lineHeight": "2.8rem", "letterSpacing": "-0.03em", "fontVariantNumeric": "tabular-nums"}
  "code": {"fontFamily": "JetBrains Mono, ui-monospace, monospace", "fontSize": "0.78125rem"}
"rounded":
  "control": "14px"
  "metric": "20px"
  "panel": "24px"
  "hero": "20px"
  "pill": "9999px"
"spacing":
  "base": "8px"
  "page-gutter": "16px / 24px / 32px"
  "panel-padding": "20px"
"elevation":
  "panel": "0 10px 32px -22px rgb(42 65 122 / .24)"
  "pop": "0 22px 64px -20px rgb(31 47 88 / .28)"
"motion":
  "fast": "160ms cubic-bezier(.16, 1, .3, 1)"
  "reduced": "all animation and transition durations collapse to 0.01ms"
---

# Design System: InvoiceFlow — Modern Financial Command Center

## Overview
A calm, premium financial-operations workspace for long review sessions. Neutral graphite surfaces in both themes keep the chrome quiet; colour is reserved for the navy accent and for meaning (status, money at risk, chart series). The 2026-11-22 polish pass (unslop) removed the earlier periwinkle washes, header glows, the animated sign-in aurora and the violet AI styling. Strong near-black type, tabular figures and one charcoal pill per screen keep the reviewer's attention on the problem that matters most. It supersedes the earlier "Ledger & Red Pen" appearance (2026-11-20); that direction's business, safety, provenance, accessibility and RTL rules remain in force.

The look was set by seven user-supplied concepts (`docs/design/command-center-references/`). They are visual references only: no number, label, metric or capability in them is used as data.

## Principles
1. **Exception-driven.** The first screen answers "what needs me, why, and what first"; the single primary action is *Review next priority*.
2. **Evidence before opinion.** Source documents, deterministic results and records are opaque, solid and factual. AI text is labelled AI and advisory and always cites real passages; AI actions look like any other action (no special colour, no sparkles).
3. **Colour is a state vocabulary.** It never decorates and never stands alone: every state also has a word or an icon.
4. **Quiet chrome, rich moments.** No gradients, glows or colour washes on surfaces. The richness goes into the evidence view (values traced to where they are printed) and the money-at-risk figures; the signature is the thin navy evidence box.
5. **Hebrew-first and truly bidirectional.** RTL is the default; identifiers, SKUs, amounts and hashes are isolated LTR islands (`<bdi>`, `.ltr`, `dir="auto"`).

## Colors
Semantic tokens live in `frontend/src/app/globals.css` (light under `:root`, dark under `[data-theme="dark"]`) and are exposed to Tailwind in `tailwind.config.ts`. The dark palette is designed separately (deep navy surfaces, lifted state colours), not inverted.

| Role | Token | Meaning — and only this |
|---|---|---|
| Critical | `danger` / `danger-soft` | blocking or high-risk discrepancies, critical priority, destructive confirmation |
| Warning | `warn` / `warn-soft` | warnings, pending information, delivery shortfalls, due-date urgency, offline demo mode |
| Verified | `ok` / `ok-soft` | verified, matched, completed, received in full |
| AI advisory | `ai` / `ai-soft` / `ai-line` | explicitly labelled AI-generated or advisory content, live-model indicator |
| Information | `info` / `accent` | navigation, neutral information, links, focus, selection |
| Primary action | `primary` / `primary-hover` / `primary-ink` | the one charcoal pill per screen |
| Evidence | `highlight` | the source-passage / field highlight on documents |
| Surfaces | `hero` (= surface) | page headers are plain surfaces with a hairline; `atmosphere-*` and `hero-wave` are kept only as neutral aliases |

Text: `ink` (headlines, figures), `ink-2` (body), `ink-3` (secondary, ≥4.5:1 on surface). Lines: `line`, `line-strong`. Charts use `series-1…4` in fixed order with `chart-grid` / `chart-axis`.

## Typography
Assistant (Hebrew + Latin, 400–700) for everything; JetBrains Mono only for codes and hashes. Scale starts at 15px body (Assistant's small x-height) with roughly a 1.2 ratio: `sm` 13.5, `base` 15, `md` 17, `lg` 20 (section titles, 600), `3xl/4xl` 30–36 (page titles, 600, -0.025em), `figure` 40 and `6xl/7xl` for the one hero count. Figures always use `tabular-nums lining-nums`. No ultra-light weights. Headings use `text-wrap: balance`.

## Layout
- **Shell:** an 84px icon rail on the inline-start edge (right in Hebrew, left in English) on wide screens; every icon has an accessible name and a tooltip, and *All destinations* opens a labelled, grouped drawer with every permitted page (also the mobile menu). A translucent top bar carries the breadcrumb, AI/offline mode, the language and theme toggles, the user and sign-out. A skip link jumps to `#main`.
- **Page:** max width 1560px, gutters 16 / 24 / 32px, 8px spacing rhythm, generous space between groups and tight rows inside tables.
- **Layouts:** `.command-layout` (content + 280–320px aside at ≥1280px) for dashboard-style pages; `.workspace-layout` for the investigation workspace — evidence (sticky), findings, decision (sticky, own scroll) — collapsing to a stack with the decision kept reachable on narrow screens.

- **Login:** a split screen on wide screens: a quiet `.brand-panel` (product promise, three capability points, an invoice slice whose total sits in the navy evidence box, a synthetic-data note) beside the sign-in form and demo accounts. On phones the panel is hidden and the form keeps the tagline.

## Navigation and keyboard
- **Command palette** (`command-palette.tsx`, cmdk inside a Radix dialog): Ctrl/⌘+K or the top-bar search pill. It searches invoices, suppliers and purchase orders through the existing list APIs (so tenant scoping and permissions come from the backend), offers *Review next priority*, theme and language actions, and every permitted destination with its key hint.
- **Shortcuts** (`shortcuts.tsx`, `?` opens the list): `G` then `D`/`Q`/`I`/`U`/`S`/`P`/`K` to navigate; in the workspace `N` next item (through the unsaved-work guard), `E` evidence, `D` decision. Keys are ignored while typing. No approve, reject or other financial decision has a single-key shortcut.

- **AP Copilot** (`copilot.tsx`): a side sheet from the inline-end edge, opened by the "Ask Copilot" top-bar
  button, `/` or the palette. Suggested questions, the reviewer's message as a charcoal bubble, answers with an
  AI badge, linked citation chips per record, a collapsed "Steps" list of the read-only tools used, follow-up
  chips, and an amber "Not verified" badge when the figures could not be checked. A read-only notice sits under
  the title.

## Motion
Motion (`motion/react`, LazyMotion) gives each page a 180ms fade-and-rise; queue rows rise in with a 24ms stagger capped at eight rows; dialogs fade and scale in; nothing loops (the sign-in aurora was removed). Figures never animate, and `prefers-reduced-motion` turns all of it off.

## Elevation & Depth
Two shadows only: `--shadow-panel` (resting panels, soft and offset) and `--shadow-pop` (drawers, tooltips, menus). Panels declare elevation once: a thin border plus the panel shadow; no ghost cards, no nested glass. Frosting (translucent surface) is used for `.command-hero` and `.command-metric` only.

## Shapes
Controls 14px, metric tiles 20px, panels 24px, hero 28px; pills (`rounded-full`) for buttons, inputs, filters, badges and status. Tables keep compact rows inside rounded panels.

## Components
- **Buttons** (`ui.tsx`): `primary` charcoal pill (one per screen), `secondary` surface pill with a hairline ring, `ghost`, `danger` (outline, red text), `ai` (same as secondary: AI actions get no special colour). Sizes sm 32 / md 40 / lg 48px. Pressed state nudges 1px; disabled at 45% opacity; focus ring from `accent`.
- **Panel / PanelHeader:** `.command-panel` opaque surface, 24px radius; header with an `lg` semibold title and `ink-2` subtitle.
- **Hero and metrics:** `.command-hero` atmospheric header with a quiet wave; `.command-metric` translucent tiles whose figures come from the API with their denominators.
- **Tables:** `.command-table` with a sunken header row, hairline rows, hover tint and tabular figures; on small screens core lists switch to information-complete stacked rows.
- **Status and priority:** `StatusPill`, `PriorityBadge` and rank chips pair colour with words; business status, priority and due urgency are separate badges.
- **Evidence:** `DocumentViewer` (real page images, zoom/page tools, field and citation highlights); provenance chips open the source location.
- **AI advisory:** `AiBlock` on a quiet navy-tinted surface with an "AI-generated" heading and an "Advisory only" footer; citations open the real highlighted passage; abstention and missing evidence are stated plainly.
- **Decision panel:** approve (proposed resolution), reject, request clarification (procurement or supplier), escalate — notes, overrides and permission rules from the backend; never "approve payment" by AI.

## Do's and Don'ts
- Do keep money separated by currency; never convert or sum across currencies.
- Do show a metric only with its real source, name and denominator; omit unsupported charts.
- Do keep red for critical only, amber for warnings/pending/shortfalls, green for verified; AI output is marked by its label, not by a colour.
- Don't put gradients or glass behind documents, tables, forms or citations.
- Don't add buttons without a real action (no fake search, no "Run evaluation" without an endpoint).
- Don't use mockup numbers, confidence percentages or trends that the backend does not provide.
- Don't animate mission-critical values; keep transitions 120–200ms and respect reduced motion.
