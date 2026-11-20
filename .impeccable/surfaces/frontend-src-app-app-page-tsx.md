---
version: 1
slug: "frontend-src-app-app-page-tsx"
primary_target: "frontend/src/app/(app)/page.tsx"
related_targets: ["frontend/src/app/(app)/exceptions/page.tsx","frontend/src/app/(app)/exceptions/[id]/page.tsx"]
---

## Scope
Operate surface: the authenticated InvoiceFlow app. Core screens redesigned: review dashboard (/), priority queue (/exceptions), investigation workspace (/exceptions/[id]); every other page inherits the system through shared components. Hebrew RTL default, English supported, light and dark.

## Audience and task
Finance reviewers and procurement in Israeli SMBs, at office desktops in daylight, in long queue sessions. Task: see which invoices need attention, why, and what first; inspect evidence; decide (approve, reject, request clarification, escalate); move to the next. Constraints: no automatic financial decisions; AI is advisory and labelled; priority is computed by the backend and shown identically everywhere.

## Direction contract
THESIS: An audited ledger, modernized: precise figures, quiet structure, and the auditor's mark reserved for the one number that is wrong. It refuses the category default of white KPI cards with a blue accent and colour used as decoration.
OWN-WORLD: Calm cool-neutral ground with a deep ink-navy shell rail; ink-navy figures in tabular numerals; hairline rules in a cool grey-green; one disciplined state vocabulary: auditor red only for critical discrepancies, amber for warnings, green for verified/completed, violet only for AI-generated text. Totals carry a double rule. A discrepant figure is shown struck through with the expected figure beside it in red. One workhorse sans for everything, tight 1.2 type scale.
STORY: The reviewer sees how much needs them and how much money is at risk, understands the top item's problem from its row, presses "Review next priority", sees the wrong figure marked against PO and receipt with cited evidence, decides with a note, and lands on the next item.
FIRST VIEWPORT: Ink rail (right in RTL) with navigation; top bar with organization, mode and the primary "Review next priority" button. A ledger header strip of four figures: needs review (critical/high split), money at risk over value under review, ready for approval, awaiting information, each a large tabular figure over a hairline. Below, the priority queue: dense ranked rows (rank, priority mark, invoice, supplier, reason in words, money at risk, due), the critical rows led by a red rule in the leading margin.
FORM: Ledger & Red Pen, position 1 of my grounded list (picked by the user over the rolled direction); seed:37d3a84c8a6aa7e0. Interpretation pinned by the user: "a modern, premium financial operations SaaS, not a literal paper ledger"; "Reserve red for genuine high-risk discrepancies and critical issues. Use amber for warnings and green for verified or completed states."
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Memorable moment
The red-pen correction: in the workspace's discrepancy table and on the PO page, the invoice figure struck through with the expected figure written in red beside it.

## Unresolved
Exact Hebrew copy for new labels; dark-mode tuning of the red so it stays legible without glowing.
