# InvoiceFlow — Page-by-Page Aurora Redesign Kit

**For Claude Code or another coding agent.** Eleven screen-specific implementation prompts, each paired with one generated visual reference. The ten inspected application screens correspond to supplied full-page PDF captures numbered 4–13. A bonus Audit Trail reference is inferred from navigation; its actual page was **not** included. The already-redesigned Overview Dashboard (screenshot 3) and Login screen (screenshot 14) are visual baselines, **not** redesign targets.

## How to use

1. Open the existing [InvoiceFlow repository](https://github.com/EliyahuEden/InvoiceFlow-AI-Powered-Financial-Document-Processing) in Claude Code.
2. Choose one page below and attach its correspondingly numbered `.png` reference from the accompanying `references/` folder. Optionally attach the current PDF capture of that page as a **before** reference.
3. Paste that page's standalone prompt. Each is written to be executed, not merely planned.
4. After implementing a page, have Claude show **actual rendered desktop/mobile screenshots** and working tests before moving on.
5. Work in the recommended order: **01 Priority Queue → 02 Inbox → 03 Upload → 04 Investigations → 06 Purchase Orders → 07 Knowledge → 05 Suppliers → 08 Evaluation → 09 Observability → 10 Settings → 11 Audit**. This builds core workflows first.

### Global visual and engineering constraints for every page

- **Source of truth:** The current Overview Dashboard is already good. Treat its real implementation as the style foundation. Preserve the existing InvoiceFlow wordmark, icon system, navigation/sidebar/top bar, content width, light pearl/lavender ambience, opaque white rounded cards, quiet violet selections, charcoal primary actions and semantic status colors. The generated images are *directional design references*, **not** pixel-perfect instructions, and their generated logos/text/numbers can be inaccurate.
- **Purposeful richness:** Add meaningful hierarchy, refined surface depth, motion, hover, inline contextual detail, elegant filters, skeletons and high-quality empty/error/success states. No decorative 3D behind financial evidence, no noisy gradients on data tables, no gratuitous charts or unnecessary new dependencies.
- **Functional truth:** Audit frontend/backend routes, models, permissions and states first. Preserve working workflows. Do not fabricate fields, amounts, model calls, policy passages, confidence scores, historical trends, ROI, cost estimates, percentages or actions. A button is present only if it does something real. In demo mode, use existing clearly labeled synthetic/demo data. Never add or convert sums across different currencies.
- **Localization:** English LTR and Hebrew RTL must be equally polished. Use bidi isolation for identifiers, currencies, dates, amounts and filenames. Support mobile/tablet as well as wide desktop. Follow keyboard and screen-reader semantics and `prefers-reduced-motion`.
- **Implementation:** Prefer current Next.js/React/Tailwind/Radix/Motion/Recharts stack. Avoid replacing global infrastructure. Preserve tenant isolation, authentication, role checks and backend authority. Do not invent APIs, payments, approval permissions or migration changes.
- **Verification:** Inspect relevant route source, implement incrementally, run typecheck, build, available tests and meaningful Playwright scenarios. Compare actual rendered screenshots at 1440×900 and 390×844 (or sensible equivalent); test both themes and locales and all reachable screen states. Fix overflow, clipping and interaction regressions.

---

## 01 — Exceptions & Approvals: Priority Queue

**Reference:** `references/01-priority-queue.png` · **Original:** `full-page-snap-screenshot (4)(1).pdf`

```text
Act as InvoiceFlow's Principal Product Designer and Staff Frontend Engineer. Redesign and implement the existing Exceptions & Approvals / Priority Queue route. I am attaching reference 01 and the existing project is the source of truth. The Overview Dashboard already has the visual language I want; MATCH its premium pearl-lavender shell, crisp white panels, subtle depth, charcoal CTA and meaningful red/amber/green states. Preserve existing API logic, priority ranking, auditing, review actions, keyboard shortcuts, authorization and multilingual RTL support.

CURRENT UX PROBLEM: The queue is a visually flat table with a dense set of selects and a disconnected right sidebar. It shows priorities but does not make each item's urgency/reason easy enough to read or explain why the next item matters.

IMPLEMENT: (1) A compact, high-information header: cases needing review, critical count, amount at risk separated by actual currency, due/overdue information sourced from the API. (2) One prominent working "Review next priority" action; it must use the existing priority/next-item workflow, not a client-side guess. (3) A readable, searchable, sortable priority list where each row highlights rank, priority, supplier + invoice, plain-language reason, due urgency, amount/currency, and next action. (4) Consolidate search, severity, reason, supplier, due, status and sorting into a flexible filter bar with an "Advanced filters" disclosure rather than many cramped fixed dropdowns. (5) A responsive contextual "Why this is first" / Queue Health side panel driven by the selected record's actual priority reasons, evidence links and current queue metrics. (6) Expand/collapse details or preview without losing scroll position; transitions should preserve row context as the user opens an investigation. (7) Proper empty, loading, stale, unauthorized and error states.

Show visual clarity at first glance; semantic color must encode actual state only. Never aggregate different currencies, fabricate due dates or create a payment-approval action from a visual mockup. Implement and validate the real page and show desktop/mobile screenshots, tests and affected files.
```

## 02 — Invoice Inbox

**Reference:** `references/02-invoice-inbox.png` · **Original:** `full-page-snap-screenshot (5).pdf`

```text
Redesign and IMPLEMENT InvoiceFlow's existing Invoice Inbox, using reference 02 and the current already-polished Overview Dashboard as the exact shared design language. Inspect the real invoice list API, lifecycle statuses, extraction methods, permissions, pagination and existing route before coding. Preserve Upload, Archive, Export, search, links and invoice drilldown functionality.

CURRENT UX PROBLEM: A generic large table plus redundant statistics and a cramped row of status tabs. It makes it hard to quickly preview the document behind a row, spot a pipeline blockage, or jump to the next useful action.

IMPLEMENT: (1) A strong but calm page header, one prominent working Upload action, subtle Archive/Export controls only where already supported. (2) An elegant lifecycle summary showing relevant stages such as received, processing, exception, ready for review — display only actual supported states and counts; no unsupported new statuses. (3) Compact meaningful KPI tiles with denominators and correct date ranges. (4) One coherent searchable/filterable/sortable invoice table: invoice + filename, supplier, linked PO, invoice date, original-currency total, extraction/processing method, status, received time and actionable row menu. (5) A contextual preview panel on row selection with the existing real invoice image/PDF thumbnail, extracted fields if available, provenance/source information, and a real Open invoice action. (6) Keyboard row selection and accessible preview drawer; mobile list cards with essential information rather than a squeezed desktop table. (7) Beautiful loading, empty, failed upload, and archived states.

Pay close attention to state wording: "Ready for approval" is not the same as already approved or paid. Do not fabricate the example document content, statuses, totals, ingestion source or extracted metadata visible in the concept screenshot. Keep real business semantics and API behavior. Run the build/tests and inspect actual desktop/mobile browser screenshots.
```

## 03 — Upload Invoices

**Reference:** `references/03-immersive-upload.png` · **Original:** `full-page-snap-screenshot (6).pdf`

```text
Implement a premium, exceptionally polished document-upload experience for InvoiceFlow using reference 03. Match the existing Overview Dashboard's Aurora visual language. Inspect the current upload endpoint, file type and size limits, demo samples, actual async processing-job states, retry behaviors and validation before restructuring this route.

CURRENT UX PROBLEM: The captured page spreads critical elements across a very long canvas and appears to contain enormous blank sections. Confirm in a real browser whether this is a screenshot stitching artifact or an actual layout issue; do not assume the capture itself proves a code defect. The main action, progress and sample files need to fit together as one coherent workflow.

IMPLEMENT: (1) Put a beautiful drag-and-drop drop zone, clear Choose files action and exact accepted file types/limits above the fold. (2) Include one tasteful 2.5D/3D invoice-processing illustration INSIDE the hero/drop-zone surface: stacked translucent paper, a controlled scan beam and source→structured-field connectors; it must never interfere with inputs and should fall back to static imagery. Prefer lightweight CSS/Motion; consider Rive or Three.js only after a measurable performance check. (3) Adjacent actual-status pipeline Uploaded → Reading → Extracting → Matching → Ready for review, adjusted to backend states. Use indeterminate active states when real percentages are unavailable. (4) A processing jobs list with clear file name, current stage, errors, retry, open-result action, and multiupload handling as supported. (5) A compact Try a sample panel using existing real sample-upload handlers, not decorative fake demos. (6) Meaningful hover, drag enter, progress and completion feedback with reduced-motion support; mobile stacks action before illustration.

Preserve existing actual upload restrictions, security checks, session scoping, document processing and duplicate handling. Do NOT copy the concept mockup's example 50 MB limit or job progress; use the code's actual values. Show visual screenshots of idle, dragging, processing, success and failure and verify upload tests.
```

## 04 — AI Investigations

**Reference:** `references/04-ai-investigations.png` · **Original:** `full-page-snap-screenshot (7).pdf`

```text
Transform the AI Investigations route from a plain activity table into a premium, explainable AI casework interface. Use reference 04 and preserve the current InvoiceFlow Overview design system. Inspect real investigation records, model/tool metadata, run status transitions, proposed resolutions, source citations and detail routes before implementing.

CURRENT UX PROBLEM: Runs are rows of invoice IDs, status, model and tool-call counts; the reviewer cannot quickly see what AI discovered, how it reached the result, which parts are evidence, or what to do next.

IMPLEMENT: (1) Clear page-level segmentation Running / Needs attention / Completed only if actual underlying statuses can support it. (2) Search and filter by invoice, supplier, status, time and available run metadata. (3) Make each row/card express invoice + supplier, current execution status, a concise real advisory recommendation when stored, one-sentence reason, evidence count if available and secondary technical metadata behind an expandable detail. (4) Clicking a run opens a beautiful right contextual Investigation 360 pane with a structured provenance timeline: source invoice, linked PO/receipt, relevant policy/citation, and AI-proposed action only from real persisted data; no invented chain links. (5) Citation chips should take the user to verifiable source records/pages, with exact passage or field highlight only when location evidence actually exists. (6) One Open investigation action that navigates to the real workspace without executing an approval; a smooth row→detail transition and accessible fallback. (7) Clear not-run, failed, pending, no-evidence and historical-run states.

AI suggestions MUST be labeled advisory and never look like server-authorized decisions. Do not invent an explanation, confidence or tool trace absent from the backend. Preserve original auditability, tenant scope and model provenance. Verify real run details, links, accessibility, mobile and build/test status.
```

## 05 — Suppliers / Supplier 360

**Reference:** `references/05-suppliers.png` · **Original:** `full-page-snap-screenshot (8).pdf`

```text
Redesign InvoiceFlow's Suppliers route as an elegant, useful Supplier Directory with contextual Supplier 360 detail. Follow the provided 05 mockup and the visual foundations of the existing Overview Dashboard: pale lavender atmospheric shell, immaculate white cards, fine separators, purple selection and semantic statuses. Inspect current supplier API fields, routes and permissions before adding interface sections.

CURRENT UX PROBLEM: The existing page is essentially a search field and one flat table. It has little overview, poor discoverability of linked records, and no convenient supplier context.

IMPLEMENT: (1) Compact header with supplier count and other REAL available summary data such as linked/open POs and invoices. (2) Search supplier legal name, Hebrew alias and tax ID; optional status/payment-terms filters that actually work. (3) Stronger row hierarchy with initials mark, bilingual supplier name, tax ID as a protected LTR island, terms, linked PO/invoice counts and status; subtle hover/selection. (4) A contextual Supplier 360 panel with factual company metadata, recent linked invoices, recent POs, and linked agreements if those sources truly exist, each opening the existing record route. (5) Clear primary Open supplier action if a detail route already exists, otherwise use the honest side panel without fake drilldowns. (6) Polished empty/missing-data states (e.g., No contact details recorded), accessible table sort and mobile information cards.

Do NOT invent supplier risk scores, email/phone/address, supplier avatars/logos, contracts, contact people, payment histories or trends merely because the image contains them. Preserve RBAC and source data. Implement, test interactions and show actual before/after browser shots.
```

## 06 — Purchase Orders and Goods Receipts

**Reference:** `references/06-purchase-orders.png` · **Original:** `full-page-snap-screenshot (9).pdf`

```text
Make InvoiceFlow's Purchase Orders route feel like a modern procurement reconciliation workspace, using reference 06 and the existing Overview Dashboard's Aurora language. Inspect purchase-order line-item APIs, goods receipts, matching invoices, current amount/currency handling and statuses before coding.

CURRENT UX PROBLEM: The table mostly shows PO number, supplier, date, line count, amount and status. It does not visually explain the key procurement distinction of how much was ORDERED versus how much has actually been RECEIVED.

IMPLEMENT: (1) Actionable header and factual state totals by Open, Partially received and Received (where supported), never sum across currencies. (2) A fast searchable, filterable, sortable table with PO number, supplier, date, original-currency total and unmistakable Ordered vs Received progress as two labeled quantities with a proportion bar or line-item breakdown when the data supports it. (3) Partially received orders highlighted in amber but never incorrectly marked complete. (4) Contextual PO detail panel: supplier, line items with ordered/received quantities, goods receipt references and matching invoice references, all links real. (5) Progress labels must clarify units/denominators and handle over-receipt, missing receipt or incomparable units honestly. (6) Refined segmented tabs, row transitions, mobile layout and empty/error/loading states.

Do not generate received quantities from status alone; use actual goods receipt data. Avoid fake purchasing actions or new business flows not supported by the backend. Preserve full order-versus-receipt correctness and financial validation. Implement with tests, especially partial receipt calculations, and actual desktop/mobile screenshots.
```

## 07 — Agreements & Knowledge / RAG

**Reference:** `references/07-knowledge-rag.png` · **Original:** `full-page-snap-screenshot (10).pdf`

```text
Redesign the Agreements & Knowledge page into an impressive but trustworthy AI knowledge research workbench. Follow reference 07 and the existing InvoiceFlow Overview styling, preserving real RAG request flows, retrieval strategies, citation navigation, document index metadata and API contracts.

CURRENT UX PROBLEM: The page has a small search area, example questions, an empty retrieved-passages box, and a long document table. It does not clearly express the core AI value: answer + ranked source evidence + source preview.

IMPLEMENT: (1) A prominent high-contrast Ask your company policies search box with accessible Enter/Ask submission and contextual examples. (2) Clearly separated retrieval strategy controls BM25, Dense, Hybrid and Hybrid+rerank only if these correspond to real configured modes. (3) On a real response: a readable answer card with AI-advisory label and numbered clickable citations; an adjacent retrieved-passage panel with source title, version, relevant excerpt and rank, only showing confidence/score if actually available and calibrated. (4) Clicking a citation opens a document/source preview with the actual verified page or clause highlighted when source locations are available. (5) A compact document library below with language, type, effective date, version, index status and functioning filters. (6) Beautiful initial empty state, searching/loading, no results, ambiguous answers, abstention and provider-offline states. (7) Fully RTL-aware Hebrew/English text, including excerpts and bidi identifiers.

Do not copy the AI-generated mockup's invented policy paragraphs or confidence numbers. Never invent a verified source. For every result, source metadata must come from the retrieval system. Show a real query demo and test citations, language switching, mobile and keyboard flows.
```

## 08 — AI Evaluation / Quality Lab

**Reference:** `references/08-ai-evaluation.png` · **Original:** `full-page-snap-screenshot (11).pdf` (three captured image segments)

```text
Redesign the existing AI Evaluation page into a high-quality engineering-grade AI Quality Lab, inspired by reference 08 and visually consistent with InvoiceFlow Overview. FIRST inspect how the current static/offline benchmark reports are produced, which datasets and results exist, whether any time-series or live evaluation API exists, and the existing methodology notes.

CURRENT UX PROBLEM: Valuable metrics (Field accuracy, Recall@5, MRR, precision, extraction by input, retrieval comparison, field breakdowns, report details) are packed into an extremely long page. A recruiter cannot understand the strengths, weaknesses and exact evaluation basis quickly.

IMPLEMENT: (1) Elegant KPI strip with precise metric names, actual values, dataset and sample size; add delta-vs-prior-run only if prior runs truly exist. (2) Tabbed sections Extraction / RAG Retrieval / Reconciliation, preserving all existing results and links. (3) Rich but honest charts for document type comparison, retrieval strategy comparison, and error categories; label axes and sample sizes. (4) Drill into field-level accuracy/precision/recall/F1 and reproducible error examples in collapsible panels. (5) Make methodology, synthetic dataset provenance, limitations, benchmark dates and reproduction commands discoverable but not overwhelming, with one supporting side column. (6) Add a Run evaluation button ONLY IF an authenticated, authorized endpoint exists and can return a real result; this page currently looks offline/report-based, so otherwise use view/download documentation rather than a fake trigger. (7) Ensure dense metrics are keyboard accessible, responsive and legible; support data table equivalent to charts.

NEVER mix extraction metrics, retrieval metrics and end-to-end results as though directly comparable. Never invent historical trend deltas, extra benchmark runs, confidence or metric denominators shown in the reference image. Validate calculations and screenshots at several viewports, plus build/tests.
```

## 09 — AI Observability

**Reference:** `references/09-ai-observability.png` · **Original:** `full-page-snap-screenshot (12).pdf`

```text
Transform the existing AI Observability view into a credible observability console for agent runs and document-processing operations while keeping the gorgeous calm InvoiceFlow palette. Use reference 09 as the layout target but inspect real telemetry and data availability before choosing charts or KPIs.

CURRENT UX PROBLEM: The current view has useful raw tool-call frequency and validation counts but much empty or flat surface. Model-call reporting and recent-call data may be absent, and this should be presented honestly instead of leaving confusing blank tables.

IMPLEMENT: (1) A context-rich status header with chosen timeframe, environment/mode when available, and a prominent honest notice if model-call cost or model call data are unavailable. (2) KPI cards for factual agent runs, tool calls, rejected calls and extraction jobs only if backend returns them. (3) Well-designed, accessible charts for actual tool usage, validation events and extraction methods; no invented trend time-series. (4) A filterable trace/run list showing recorded time, workflow, type, model/tool, latency and status where present, with meaningful empty state otherwise. (5) Selected trace opens a clean contextual event timeline with real tool names, durations, input/output metadata only after sensitive fields are sanitized, and links to related invoices if authorized. (6) Gorgeous skeleton/error/no-model-usage states, lightweight visual motion, compact filters, keyboard and mobile navigation.

Do not imply provider prices, spend, latency, tokens, model IDs, historical totals or raw confidential payloads if the backend does not supply them. Read the existing "No price table configured" state and preserve it. Do not add a Configure pricing action unless fully implemented and authorized. Verify the page in both populated-agent and empty-model-call states.
```

## 10 — Organization Settings

**Reference:** `references/10-organization-settings.png` · **Original:** `full-page-snap-screenshot (13).pdf` (two captured image segments)

```text
Reimagine the existing Organization Settings screen into a premium, efficient administrative console matching InvoiceFlow Overview. Use reference 10 as a visual concept and inspect every current form/control, permissions gate, approval rule, security setting, session/device feature, 2FA workflow, team view and role permission matrix before moving anything.

CURRENT UX PROBLEM: A very long continuous page combines deterministic matching tolerances, approval thresholds, session settings, signed-in devices, team, password, 2FA and permissions. Important settings are easy to miss, related controls are far apart, and save/validation behavior is unclear.

IMPLEMENT: (1) In-page category navigation or tabs: General, Matching Rules, Approval Policy, Security & Sessions, Team & Roles — map existing controls exactly. (2) Show one focused setting group at a time with clear labels, units, helper text, current values and constraints. (3) Matching thresholds should distinguish absolute currency amount versus percent versus quantity and keep currency policy accurate. (4) An optional sticky changes summary and Save/Discard area ONLY if the existing backend supports editable settings; show disabled/review-only state for non-admins. (5) Clear server-side error/validation and accessible unsaved changes guard; never silently mutate finance policy. (6) Device session management, password changes and 2FA must preserve security semantics, reauthentication and secrets handling. (7) Team roles table and permission matrix must remain discoverable and not imply permissions users do not have. (8) Polish success, no-access and responsive/mobile states.

The concept's "Auto approve" and impact summary are illustrative only. DO NOT introduce any automatic payment approval or policy side effects unless already securely implemented. Preserve robust backend authority and auditability. Show working admin and restricted-user screenshots plus tests.
```

## 11 — BONUS: Audit Trail

**Reference:** `references/11-bonus-audit-trail.png` · **Original:** **not attached** (identified in navigation only)

```text
BONUS TASK: InvoiceFlow's navigation includes an Audit Trail page, but no screenshot of its current UI was attached. First find and inspect the actual route and data model; do not infer features from the visual mockup. Then redesign it into an exceptionally clear, immutable, trustworthy audit explorer consistent with the current Aurora Overview Dashboard, using reference 11 as art direction.

IMPLEMENT only with real data: (1) Search/filter for actor, event action, record type and date where supported. (2) A clear chronological event list grouped by date, with human-readable event labels, actor identity, affected invoice/PO, UTC/local timestamp semantics and status where applicable. (3) Selected event opens an evidence-style inspector with event metadata, authorized linked records and old/new field diffs when those diffs are already recorded. (4) Present immutability honestly; if records are not cryptographically signed, do not imply they are. (5) Only expose Export audit log if supported and RBAC-authorized. (6) Support huge log pagination/virtualization, accessible keyboard navigation, search loading/empty/error states, redaction of secrets and sensitive document content, and complete English/Hebrew layouts.

Preserve backend audit event integrity; this is a READ-only interface. Implement verified UI, tests and screenshots. If the route is absent, report that as a separate feature decision rather than inventing an audit system from scratch.
```

---

## Global final QA task to send after all screens are redesigned

```text
Perform a full end-to-end UI/UX quality and consistency review of InvoiceFlow after the page-by-page Aurora redesigns. Treat the existing Overview Dashboard and approved Login as the visual benchmarks. Inspect every authenticated route and all reachable states, including detail views and drawers, in English LTR and Hebrew RTL, light/dark, desktop/tablet/mobile. Resolve inconsistent tokens, typography, table density, spacing, shadows, radii, controls, status colors, sticky panels and navigation behavior. Validate all controls against real backend endpoints: no fake buttons, sample data in production, fabricated evidence, fictitious metrics or dangerous approval shortcuts. Audit accessibility, keyboard, color contrast, reduced motion, responsiveness and performance. Run typecheck/lint/build/tests and available Playwright e2e plus visual screenshot comparisons. Preserve real invoice processing, financial currency semantics, AI citation provenance, RBAC, tenant isolation, audit trail and authentication. Deliver actual before/after screenshots of each page, a report of verified improvements, test results and remaining blockers.
```

### Design image caveat

Generated reference PNGs are conceptual illustrations. They may include inconsistent text, sample numerical values, trends, dates, policy clauses, model costs, usage counts, contact details or controls not present in the app. **Treat them strictly as layout, hierarchy, typography, color and interaction references.** Claude must cross-check every feature against actual repository code and real data before implementation.
