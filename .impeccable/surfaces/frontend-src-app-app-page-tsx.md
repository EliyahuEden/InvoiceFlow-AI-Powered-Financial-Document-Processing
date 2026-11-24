---
version: 1
slug: "frontend-src-app-app-page-tsx"
primary_target: "frontend/src/app/(app)/page.tsx"
related_targets: ["frontend/src/app/(app)/exceptions/page.tsx","frontend/src/app/(app)/exceptions/[id]/page.tsx","frontend/src/app/login/page.tsx"]
---

## Scope
Operate surface: the whole authenticated InvoiceFlow app plus the sign-in pages (login, sign-up, forgot/reset password, accept invite). Core screens: review dashboard (/), priority queue (/exceptions), investigation workspace (/exceptions/[id]), invoice inbox and detail, purchase orders, suppliers, settings. Every other page inherits the system through shared components. Hebrew RTL default, English supported, dark-first with an equally polished light theme. Replaces the 2026-11-22 "Command Center" look (owner: "looks like trash"; wants a high-tech SaaS product).

## Audience and task
Finance reviewers and procurement in Israeli SMBs in long queue sessions; also recruiters and engineers opening the portfolio demo for five minutes. Task: see what needs attention and why, inspect evidence, decide, move on. Constraints: no automatic financial decisions; AI advisory and labelled; WCAG 2.2 AA with the axe scan at 0; every string in Hebrew and English.

## Direction contract
THESIS: A precise instrument for money, not a dashboard of cards: the three-way match made visible as a carbon-copy stack, everything else quiet. Refuses the white-KPI-card SaaS default and the neon-on-black "dark mode" cliché.
OWN-WORLD: Dark-first graphite: near-black ground, three surface steps, hairline borders at low opacity, one sharp accent (electric indigo-blue) for selection, focus and the primary action only. State colours muted and meaningful: red critical, amber warning/pending, green verified. AI text marked by label, not colour. Crisp grotesk UI type with Hebrew support, mono for codes and amounts columns, tight 1.2 scale, rank by weight and size. Radii small (6/8/12). Light theme: cool white with the same structure.
STORY: The reviewer sees how much needs them, opens the top case, sees the invoice, PO and receipt layers fall out of register exactly where the money is wrong, reads the cited reason, decides, lands on the next item.
FIRST VIEWPORT: Slim graphite sidebar (inline-start) with grouped navigation and the workspace switcher; compact top bar with command-search (⌘K), AI mode, Copilot, theme/language, user. Dashboard: one line of four dense figures with denominators, then the priority queue as a steady table (columns never move, rows update in place), primary "Review next priority" top-end.
FORM: Triplicate carbon-copy form, position 4 of my grounded list (assigned by the roll), translated into the owner-pinned Linear/Vercel world; seed:51d1f0d9c0e721bd. Signature: "carbon-copy three-way match" (invoice / PO / receipt as three offset layers per line; misregistration marks the discrepancy). Raises: lifecycle "station line" on invoice pages (from the transit-map challenger: state as stations on one disciplined line); fixed columns, rows update in place (split-flap); strict 4px grid alignment (Crouwel grid); elevation used only for layers that float (acetate manual: ply is the only rank); small type scale, rank by weight (timetable).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Memorable moment
The carbon-copy match on the investigation workspace: three layers of the same line, the discrepant cell visibly out of register, the delta marked.

## Unresolved
Final accent hue tuned for 4.5:1 in both themes; Hebrew font choice verified for glyph coverage and weight range.
