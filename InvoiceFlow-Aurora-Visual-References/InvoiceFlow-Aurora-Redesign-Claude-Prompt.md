# InvoiceFlow — Aurora Finance OS
## Comprehensive Frontend Redesign and Interaction Engineering Brief for Claude Code

### Your role

Act as a world-class **Principal Product Designer, Staff Frontend Engineer, Design Systems Architect, Creative Technologist, and UX Quality Engineer**. Your assignment is to transform my **existing and working** InvoiceFlow application into an exceptionally polished, visually distinctive, trustworthy, production-grade AI financial operations platform.

**Repository:** https://github.com/EliyahuEden/InvoiceFlow-AI-Powered-Financial-Document-Processing

**Mandatory visual references:** I am attaching four concept screenshots to this prompt:

1. **Risk-first Dashboard / Command Center** — premium pale-lavender and ice-blue shell, urgent work made obvious, elevated KPI cards, subtle decorative 3D invoice emblem.
2. **Invoice Investigation Workspace** — original invoice/document on one side, reconciled records and highlighted discrepancies in the center, actionable sticky decision panel, precise source-to-field traceability.
3. **Immersive Upload and Processing** — beautiful but functional document dropzone, restrained dimensional document layers, extracted structured fields, real pipeline progress.
4. **AI Copilot and Verified Insights** — analytical workspace, interactive sources, explainable AI and elegant data visualizations.

Use these images as **art direction and interaction concepts**, not literal screenshots to copy, and do **not** import their fictional numbers, entities, statuses, charts, or capabilities as production data. The app must reflect real backend data, permissions and behavior. If a proposed feature is unsupported, either implement it correctly end-to-end where safe and in scope, use a properly identified demo-only path, or omit it rather than faking it.

## 1. Goal and experience bar

My target is an experience that immediately makes recruiters, hiring managers, AI engineers and senior frontend engineers think: **“This looks and feels like a premium venture-backed fintech/AI product.”** I want exceptional aesthetics **and** serious engineering quality, accessibility and performance. This is not a simple color refresh, a landing page reskin, or a collection of unintegrated Dribbble components.

Create an original design language called **Aurora Finance OS**:

- Calm and luxurious like premium financial software; clean, precise and efficient like the strongest developer tools; expressive and innovative like the best AI products.
- Pale periwinkle, icy blue, lavender-white and cool pearl atmospheric accents. Deep charcoal near-black typography and strong information hierarchy. A single bold dark primary call-to-action per view. Controlled indigo/violet accents; red, amber and green ONLY for meaningful business states.
- Dimensional, tactile visual surfaces: carefully tuned inner highlights, hairline borders, restrained reflections, soft large-radius shadows, airy glass only in shell/hero/decorative summary areas. Financial evidence, forms, invoices and tables must be crisp, opaque and highly readable.
- Elegant typography that fully supports **Hebrew-first RTL** and English mixed with IDs, amounts, dates, currency, filenames and codes. Refine the existing Assistant type system unless there is a demonstrated superior alternative. Use tabular numerals, thoughtful density, scale and whitespace.
- A sophisticated and consistent information architecture, purposeful animations, rich micro-interactions and clear workflow feedback.
- Light theme should be the visual flagship; create a separately art-directed, equally beautiful dark mode instead of a naive inversion.
- High-quality responsive variants for large desktop, laptop, tablet and mobile; keyboard-and-mouse users remain first-class.

### Important repository-specific design decision

Read `DESIGN.md` and the current tokens/components before coding. The current document intentionally moved toward neutral graphite and removed prior periwinkle ambience, header glows and sign-in aurora. For **this assignment**, intentionally evolve that direction back toward **restrained Aurora richness**, while preserving the strong principles that matter: exception-driven workflow, evidence before opinion, semantic status colors, trustworthy provenance, Hebrew/RTL accessibility, deterministic financial figures and one clear primary action. Update `DESIGN.md` so the source of truth matches the implemented result.

## 2. Audit before implementation — but do implement

First inspect the entire frontend and its integrations: route structure, components, styles, tokens, page states, user permissions, real API responses, invoice lifecycle, authentication, dashboard, queue, document viewer, invoices, suppliers, purchase orders, analytics, Copilot, settings, knowledge and audit. Also inspect applicable root or nested `AGENTS.md` instructions.

Produce a **compact implementation plan and route/component coverage matrix** identifying:

1. Existing functionality and assets to preserve.
2. Existing UI patterns worth refining versus truly missing interactions.
3. Data availability and backend capability checks for every proposed visualization or state.
4. High-impact screen redesigns and shared design-system changes.
5. Dependencies, architectural risks, performance considerations and acceptance tests.

Then **execute the redesign** in achievable milestones. Do not stop after planning or produce a design-only document. Ask for my decision only where a choice is genuinely blocking, unsafe, or requires credentials/paid services. Preserve my work and existing capabilities throughout.

## 3. Global visual design system

Create/update centrally managed CSS variables and Tailwind mappings for:

- Background atmosphere, elevated shell and hero, opaque content surface, sunken surface, separators, text levels, overlays, primary button, focus, selected state, all semantic statuses and chart series.
- Light/dark palette, including accessible focus/hover/pressed/disabled states.
- Typography with balanced Hebrew heading treatment, numeric treatment, a restrained font scale and exact type hierarchy.
- Space scale, max content widths, sidebar geometry, radii, consistent card paddings, adaptive table density and elevation tiers.
- Motion tokens (duration, easing, stagger, spring) plus `prefers-reduced-motion` behavior.
- Reusable patterns for `PageHeader`, `HeroPanel`, `KpiCard`, `RiskBanner`, `PriorityPill`, `StateBadge`, `EvidenceLink`, `SourcePopover`, `EmptyState`, `Skeleton`, `ChartShell`, `ActionDock`, `DocumentPreview`, `ProcessingStepper`, `InsightCard`, `CommandSearch`, and high-quality dialogs/sheets/forms.

Make the design unmistakably cohesive. Avoid generic AI-generated SaaS clutter, too many gradients, floating decorations behind operational data, duplicate component systems or uncontrolled one-off utility-class styling.

## 4. Signature experience: Risk-first Morning Command Center

The first 5 seconds must clearly answer: **What needs attention? Why? How much is at risk? What should I do next?**

- Visually exceptional, calm Aurora background and an intelligent hero that uses available real metrics and plain-language priority reasons.
- Clear distinction between urgent review items, late items, discrepancies, blocked cases, ready-to-review cases and already-handled items.
- One prominent `Review next priority` CTA integrated with the existing workflow, never a dead-end button.
- Premium KPI cards with clear denominators, dates and currency; charts only when backed by trustworthy data and meaningful axes/filters.
- A priority queue preview with severity, due-date urgency, supplier, invoice reference, financial exposure, explanation and action.
- Reusable refined filters, search, date range, table sorting, row selection, hover and keyboard navigation where supported.
- Rich but subtle animation: dashboard entrance, card reveal, hover depth and smooth filter updates; DO NOT animate financial numbers in ways that imply changing reality.
- If helpful, use one small, elegant 3D document sculpture within a decorative hero zone; it must never obstruct data and must degrade beautifully.

## 5. Signature experience: Investigation and Evidence Workspace

This is the **single most important UX/engineering feature**. Make it a showpiece of explainable AI and professional document review.

- Create a refined three-zone desktop investigation layout: original document viewer, structured findings/reconciliation, persistent decision panel. Keep reviewer actions available when scrolling; adapt gracefully for narrower screens.
- Clicking or hovering a field, extracted value, discrepancy, line item or Copilot citation should highlight the **actual matching region** on the source invoice when page and coordinates are available. When only page-level provenance is available, navigate to the verified page without inventing bounding boxes. When provenance is absent, clearly say so.
- The document viewer must retain accurate zoom, pan, pagination and source display. Use elegant focus states, callout pulses, reveal/scroll alignment, contextual source popovers and subtle connected-state visual feedback.
- Compare invoice vs PO vs goods receipt with clear categories: exact match, short receipt, price discrepancy, unsupported field, missing evidence, and other real rules.
- A user can follow a finding back to the source, understand the reason, choose an authorized resolution and move to the next item without losing unsaved changes.
- Preserve approval/escalation/request clarification rules, server authority, audit logging and safe-next-item behavior. Never imply an AI model can authorize financial payment.
- Rich transitions between queue card and workspace should preserve spatial context where practical, without delaying work.
- For charts or comparisons, never invent confidence percentages or fake quantitative significance.

## 6. Signature experience: Immersive Upload and Processing

Transform upload into a recognizable product moment:

- Premium drag-and-drop zone with accessible fallback browse control, validated file-type/size handling, multi-file selection if supported, readable file thumbnails/previews, remove/retry and explicit errors.
- Add a **purposeful dimensional document-extraction visual**: e.g., tasteful floating glass/paper invoice layers and source values flowing into structured fields, with fine lighting/refraction and restrained 3D parallax. It should communicate document-to-structured-data transformation, not generic flying objects.
- Use actual backend/job events to show `Uploaded → Extracting → Matching → Ready for review` (adapt labels to real states). Distinguish progress that can be measured from an indeterminate active step. Never fake a percentage or indicate completion prematurely.
- If 3D enriches the upload area, consider CSS 3D plus Motion first; evaluate Rive versus React Three Fiber/Three.js based on bundle impact, accessibility, actual interactivity and fallback. Choose **one** suitable technique; do not add a heavyweight stack only for novelty.
- Handle queues, failures, duplicate documents, retries, completion and next action beautifully.
- Avoid an animation that runs forever or a busy graphic that dominates the whole screen.

## 7. AI Copilot and Verified Intelligence

- Evolve the existing Copilot rather than rebuilding working functionality.
- Give it elegant, readable answer cards, strong trust labels, source chips, contextual links, follow-up affordances, reasoning/tool-step disclosure where already available, precise loading/streaming feedback if supported, abstention/missing-data states and verified versus advisory treatment.
- Clicking a citation should navigate to its real document/record and highlight verified source material when available.
- Allow context-aware questioning about current invoice, supplier, exceptions or risk, but respect current tool permissions and tenant boundaries.
- Upgrade analytical views with beautiful Recharts compositions, relevant tooltips, drilldowns that open the underlying records and legible comparisons. Every displayed statistic must be reproducible from API data.
- Consider subtle multi-layer 2.5D source cards in the provenance area, but preserve a flat, fast and accessible functional alternative.
- No fabricated AI answers, sources, SQL execution, review actions or progress.

## 8. Advanced motion and creative technology

Deliver at least several **coherent signature interactions**, not merely a fade on every route:

1. Shared-element or layout-aware transitions: queue → invoice workspace, selected KPI → filtered records, selected source chip → evidence.
2. Responsive springs and hover/pressed feedback: buttons, cards, toggles, tabs, menus, tooltips and drawers.
3. A genuinely satisfying upload/extraction visualization, with real state transitions.
4. Smooth interactive line/area/bar charts, tooltip tracking, focus and drilldown.
5. A tasteful 3D brand illustration or scroll-responsive scene on authentication/demo landing, separate from the operational workspace.
6. Beautiful first-run, empty, success, error, skeleton and processing states; contextually useful copy, not generic clip art.
7. Optional subtle mouse-aware illumination or depth on decorative hero/feature surfaces, never on important tables or source text.

**Motion implementation:** Prefer the already installed `motion/react` with `LazyMotion`; shared layout IDs, `AnimatePresence`, variants, reduced-motion handling and reusable motion tokens. Keep normal utility interaction transitions around 120–250 ms, major navigation around 180–350 ms. Avoid long waiting animations, scroll-jacking, constant particle motion, animated financial figures and distracting effects. GPU-accelerate transform/opacity when possible; avoid expensive blur/filter updates on scrolling elements.

**3D implementation:** Start with an isolated performance proof of concept. Use optional lazy-loaded `three` / `@react-three/fiber` / `@react-three/drei`, Rive, or lightweight CSS 3D only if it beats a simpler technique and remains performant. Limit 3D to brand/login/upload/demo components, not daily invoice tables. Support `prefers-reduced-motion`, keyboard access, device constraints, low-end GPUs, canvas-disabled fallback and graceful static imagery. If a scene is unsupported, the app must still look gorgeous and be fully usable.

## 9. Other screens and workflow-wide polish

Apply the new design language consistently across every existing route and meaningful state: invoices, queue, dashboard, suppliers, purchase orders, receipts, knowledge/evaluations if present, audit, settings, authentication, user/tenant flows, analytics and any other discovered pages.

The dashboard, priority queue and investigation screen get deep redesigns. Other pages receive deliberate consistency and selective restructuring when needed. In purchase order views, clearly distinguish **ordered quantity versus received quantity**. Preserve existing command palette, shortcuts, navigation taxonomy, themes and Copilot integration; make them more beautiful, not less useful.

Ensure polished responsive tables/cards, filter chips, action menus, breadcrumbs, quick search, confirmations, toasts, keyboard shortcut help, empty/loading/error/permission-denied/offline views. Avoid horizontal overflow and dead-end mobile flows.

## 10. Implementation and quality guardrails

- **Preserve business logic** and existing backend contracts unless a well-justified, tested enhancement is required for the requested UI. No destructive migrations or unapproved external services.
- **Financial truth:** never sum different currencies as one amount; no made-up exposure values, historical trends, dates, confidences or chart data; maintain correct decimal/currency formatting.
- **AI truth:** visually separate advisory generated content from verified deterministic facts; evidence must point to actual source material; show uncertainty and no-evidence states.
- **Security:** no credentials in frontend, no trust in client-side authorization, respect existing RBAC, tenant isolation, audit trail and sensitive document access.
- **RTL and bilingual:** Hebrew is first-class and defaults to RTL; isolate Latin IDs, mixed bidi strings, files, numbers, amounts, hashes, charts and keyboard glyphs. English LTR must be equally clean.
- **Accessibility:** visible focus, correct semantic HTML, dialogs/focus management, full keyboard usability, aria labeling, contrast, disabled semantics, reduced motion, suitable tap targets and screen-reader alternatives for charts/3D.
- **Performance:** code splitting, lazy 3D imports, sensible image optimization, avoid uncontrolled rerenders, virtualize very large lists if necessary, optimize animation and loading, maintain Core Web Vitals. Desktop GPU effects must not make phone/tablet use sluggish.
- **Visual regression:** preserve or expand existing Vitest/Playwright coverage; add screenshot baselines for key pages and states, at least desktop and mobile, Hebrew and English, light and dark. Consider Storybook stories for shared critical components if worthwhile.
- **Documentation:** keep component architecture and design decisions understandable. Document any intentional deviation from attached mockups, known limits and any new dependencies.
- **Restraint:** do not reproduce screenshot text or bogus metrics. Never add decorative fake buttons, pretend an endpoint exists, or break a robust workflow to make a still image look nicer.

## 11. Work sequence and deliverables

### Phase A — Audit and design foundation
Inventory routes, active components and flows; map the existing stack and APIs; establish tokens and reusable shell; implement light/dark, Hebrew/English foundations. Produce before/after screenshots.

### Phase B — High-impact product screens
Implement Dashboard, Priority Queue and Investigation Workspace with real data, evidence interactions, refined controls and an operational decision flow.

### Phase C — Premium interactions and 3D
Implement refined motion system, upload pipeline experience, one thoughtful interactive dimensional scene, Copilot/source interactions and animations with performance/fallback gates.

### Phase D — Entire app polish
Bring all remaining pages, system states, responsive variants and accessibility up to the same standard. Eliminate visual inconsistencies.

### Phase E — Proof and handoff
Run all feasible local checks (`typecheck`, `lint`, `test`, `build`, Playwright end-to-end/visual tests), inspect actual browser screenshots at target sizes and fix observed regressions. Provide a usable demo sequence and a concise implementation report.

**For each phase:** explain concrete completed changes, list modified paths, mention data or backend dependencies, show screenshots of actual rendered UI (not only generated concepts), and report testing status and remaining issues honestly.

## 12. Acceptance criteria — the definition of done

- Within 5 seconds, a reviewer can identify risk exposure, the urgent work and the primary next action on the Dashboard.
- A reviewer can navigate queue → invoice → verified source highlight → decision → next item reliably, with beautiful and meaningful motion.
- Upload works with actual backend state and has best-in-class visual feedback, including a performant 3D or 2.5D premium moment where appropriate.
- Copilot answer evidence can be followed to authentic source records, with obvious distinction between AI suggestions and facts.
- The app has a cohesive premium visual system, not disconnected redesigns; all present screens look intentional.
- Desktop, mobile, Hebrew RTL, English LTR and both themes are fully usable; reduced-motion users retain complete functionality.
- No fake data/features are introduced, existing behavior is not broken, and build/tests pass or all unresolved failures are accurately documented.
- The final result **feels like a real exceptional fintech/AI product, not a static Dribbble remake**.

**Begin by inspecting the project and reporting the concise audit/implementation plan, then implement and validate the upgrades incrementally. You are authorized to modify this local project as needed for this task, while respecting all repository instructions, preserving unrelated work, and asking before destructive operations, paid integrations or production deployments.**
