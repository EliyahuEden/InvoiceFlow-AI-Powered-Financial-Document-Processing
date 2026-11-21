# Modern Financial Command Center implementation plan

> Execute in this session using subagent-driven-development for independent page groups and direct integration of the shared foundation. User explicitly requests implementation without another approval gate.

**Goal:** Replace InvoiceFlow's Ledger & Red Pen appearance with the supplied pastel periwinkle financial command center while preserving real data, financial logic, permissions, evidence and every review workflow.

**Baseline:** `705cd68`. Work on `codex/financial-command-center`; no commits or pushes without a separate request. The original app/database and API credentials remain separate from disposable offline browser verification.

## Inventory and ownership

| Family | Routes | Existing shared behavior | Arrangement |
|---|---|---|---|
| Review | `/`, `/exceptions`, `/exceptions/[id]` | backend summary/queue/next, URL filters, session progress, four decisions, conflicts, drafts | bespoke dashboard with priority column, ranked queue, document/findings/decision zones |
| Invoice journey | `/invoices`, `/invoices/upload`, `/invoices/[id]` and review/reconciliation/investigation/history tabs | status counts, search/page/sort, upload/SSE/polling, provenance, correction guard, approvals | shared hero/table; split evidence and form |
| Knowledge/quality | `/knowledge`, `/knowledge/[id]`, `/evaluation`, `/observability` | upload/index/query, source citations, abstention, actual benchmark JSON, model telemetry | query/evidence split; real metric/chart groups |
| Records | supplier and PO list/detail | master-data search/forms, received/invoiced quantities, linked records | shared record header and opaque data tables |
| Operations | investigation list/detail, audit, settings, standalone document, login | trace tools, immutable history/hash, RBAC settings, PDF tools, authentication | existing structures with consistent shell/primitives |

Roles remain administrator, finance reviewer, procurement manager and read-only. Backend-returned permissions remain authoritative. UI state coverage includes loading/empty/error, processing/partial success/duplicate/failure, critical/high/normal priority, separate business status and urgency, saved/dirty/conflict/escalated/queue clear, live AI/offline/advisory/abstention, both themes and both reading directions.

## Direction contract

Modern Financial Command Center is pinned by the user's seven supplied concepts and detailed brief. Pale periwinkle/powder-blue atmosphere, opaque readable working surfaces, selective translucent hero panels, near-black type and charcoal pill primaries. An elegant narrow icon rail mirrors in RTL; a labelled grouped drawer preserves every destination. Semantic status colors retain their meanings; violet identifies advisory AI. Reference image numbers, wording and capabilities are illustrative and never data sources. Existing DESIGN.md appearance is explicitly superseded; its safety/provenance/accessibility constraints persist.

## Phases

- [ ] 1. Record this inventory, archive the supplied reference files, capture before screenshots for three core and representative secondary screens in both locales/themes.
- [ ] 2. Define semantic light/dark tokens in globals/Tailwind; implement atmospheric shell, accessible rail/drawer and shared headers, panels, controls, tables, states and AI/evidence containers. Add behavioral tests for navigation/discoverability/focus.
- [ ] 3. Recompose dashboard, queue and workspace. Keep actual priority reasons/counts/currencies, all filters/approvals, document highlights and exact decision/next/skip/draft/conflict behavior.
- [ ] 4. Redesign inbox, upload, invoice details/tabs and field correction surfaces. Preserve processing state, provenance, all significant digits and correction guards; use existing actual actions only.
- [ ] 5. Adapt knowledge, evaluation, POs, suppliers, investigations, observability, audit, settings and login with a consistency pass. No invented aggregate/trend/confidence/evaluation runner or backend changes for styling.
- [ ] 6. Verify frontend unit/typecheck/lint/build, serial Playwright on disposable offline data, all routes at 1440/1024/375 in Hebrew/English and light/dark. Inspect visual/keyboard/contrast/evidence/role behavior, fix material findings, capture after screenshots and replace DESIGN.md plus design sidecar with the built system.

## Shared frontend contract

Keep existing component APIs and semantic tokens compatible. Root owns globals.css, tailwind.config.ts, ui.tsx, shell.tsx, domain.tsx, document-viewer.tsx, list.tsx, dictionaries and capture/test orchestration. Page workers own disjoint route/component files. New semantic classes: `command-hero` (selective atmospheric header), `command-metric`, `command-panel`, `command-aside`, `command-layout`, `workspace-layout`, `workspace-evidence`, `workspace-findings`, `workspace-decision`. All use shared tokens; no per-page gradient copies.

## Verification boundaries

Existing Vitest and Playwright guard the business interactions. New tests target new navigation/keyboard/role behavior rather than CSS implementation. Reversible styling is verified by real before/after captures and overflow/contrast checks. Browser tests may mutate only the disposable seeded database. No paid model calls. Backend files, routes, financial decisions and audit logic are outside cosmetic scope. Preserve documented nominal FX limitation; do not implement conversion in a visual redesign.
