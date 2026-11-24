---
version: 1
slug: "frontend-src-app-app-page-tsx"
primary_target: "frontend/src/app/(app)/page.tsx"
related_targets: ["frontend/src/app/(app)/exceptions/page.tsx","frontend/src/app/(app)/exceptions/[id]/page.tsx","frontend/src/app/login/page.tsx","frontend/src/app/(app)/invoices/upload/page.tsx"]
---

## Scope
Operate surface: the whole authenticated InvoiceFlow app plus sign-in pages. Deep redesigns: dashboard (/), priority queue (/exceptions), investigation workspace (/exceptions/[id]), upload (/invoices/upload), Copilot and insights. Every other route inherits through shared components. Hebrew RTL default, English supported, light flagship with an art-directed dark theme. Plan: docs/AURORA_PLAN.md.

## Audience and task
Finance reviewers and procurement in Israeli SMBs in long queue sessions; recruiters and engineers opening the portfolio demo. Task: see what needs attention, why and how much is at risk, review evidence, decide, move on. Constraints: real data only (no fabricated metrics or charts), AI advisory and labelled, no automatic payment, WCAG 2.2 AA (axe 0), every string in Hebrew and English.

## Direction contract
THESIS: Aurora Finance OS: a calm, luminous finance workspace where the atmosphere is pale light and every piece of evidence is crisp paper; urgent money is impossible to miss. Refuses grey enterprise tables and neon dark "AI" chrome.
OWN-WORLD: Pale periwinkle, ice-blue and lavender-white atmosphere behind a frosted shell; opaque white content cards with hairlines and soft large-radius shadows; deep charcoal type; one near-black primary button per view; indigo/violet for selection, focus and AI marks; red/amber/green only for business states, as soft tinted badges. Assistant with heavy headings, tabular numerals. Dark theme: graphite with the same indigo.
STORY: The reviewer greets the day, sees how many invoices need review and the money at risk, starts the top case, compares invoice, order and receipt with the source value traced on the document, decides, and moves on.
FIRST VIEWPORT: Frosted sidebar (inline-start) with the logo, grouped navigation and user; slim top bar with business switcher, search and Copilot. Dashboard hero card: needs-review count, money at risk badge, urgent breakdown and the dark "Review next priority" button, beside a real received-vs-exceptions chart; a decorative CSS-3D invoice stack in the hero's quiet corner; three KPI cards; the priority queue table.
FORM: Owner-pinned direction from the brief and four reference images (art direction only); seed: none (pinned) — "Create an original design language called Aurora Finance OS ... Light theme should be the visual flagship" and, for the first viewport, "Risk-first Morning Command Center ... The first 5 seconds must clearly answer: What needs attention? Why? How much is at risk? What should I do next?" (brief §4).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Memorable moment
The investigation workspace: three source cards (invoice, order, receipt) with the disagreeing value marked, and a connector from the extracted total to its highlighted spot on the original invoice.

## Unresolved
Exact pale-surface text contrast; whether the CSS-3D upload scene needs any library (plan: none).
