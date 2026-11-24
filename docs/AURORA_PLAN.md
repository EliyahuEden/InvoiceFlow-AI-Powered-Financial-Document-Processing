# Aurora Finance OS — work plan

Brief: `InvoiceFlow-Aurora-Visual-References/InvoiceFlow-Aurora-Redesign-Claude-Prompt.md` and its four reference images
(01 risk dashboard, 02 investigation workspace, 03 immersive upload, 04 Copilot and insights). The images are art direction:
no number, name, status or chart in them is product data.

## Direction (pinned by the owner)
- **Light is the flagship:** pale periwinkle / ice-blue / lavender-white atmosphere behind the shell; opaque white
  content surfaces; deep charcoal type; one dark (near-black) primary button per view; indigo/violet for selection,
  focus and AI marks; red/amber/green only for business states.
- **Depth only where it is not data:** glass, inner highlights and soft large shadows on the shell, hero and summary
  cards. Invoices, tables, forms and evidence stay crisp and opaque.
- **Dark mode:** the 2026-11-24 graphite system becomes the separately art-directed dark theme (indigo accents kept).
- **Type:** Assistant (Hebrew + Latin) as the brief prefers, heavier headings like the references, tabular numerals;
  Geist Mono only for codes, SKUs and IDs.
- **Kept from the graphite pass:** carbon-copy three-way match (it maps to reference 02's source comparison), the invoice
  journey station line (reference 03's pipeline stepper), the steady queue table, all a11y/RTL work.

## Data check for every proposed visual
| Visual in the references | Real data | Decision |
|---|---|---|
| Dashboard "needs review" count + money at risk | `/api/review/summary` | Build (per currency, never summed) |
| Urgent breakdown (critical / high / reasons) | summary `by_level`, queue reasons | Build |
| "Risk trend %" chart | none (no risk history) | Replace with **received vs exceptions per day** from `/api/insights/dashboard` `daily` |
| KPI cards overdue / mismatches / ready (+ money) | counts in summary; money per card only where the API gives it | Build counts; money only where real |
| Priority queue preview | summary `top` | Build |
| Investigation: invoice vs PO vs receipt cards | invoice + `purchase_order` + receipts | Build (MatchStack evolves into the three source cards) |
| Source → field connector line | `field_sources` bbox per field | Build where bbox exists; page-only or "no provenance" otherwise |
| Decision panel, assignee/priority | decision API exists; assignee field does not | Build decisions; omit assignee |
| Upload pipeline Uploaded → Extracting → Matching → Ready | job status/progress/message | Build from real job events; % only when the job reports it |
| Extracted-field cards during upload | invoice fields after extraction | Show when the invoice exists; no fake values while processing |
| Copilot verified summary + sources + traceability | Copilot answer, citations, steps | Build from real answer; traceability from citations |
| Insights KPIs, discrepancy drivers bar, trend line | insights `kpis`, `discrepancy_types`, `daily` | Build with real series; no fabricated % deltas |

## Milestones
- **A. Foundation** — Aurora tokens (light + dark), Assistant type scale, atmosphere background, glass shell sidebar and
  top bar, `PageHeader`, `HeroPanel`, `KpiCard`, `StateBadge`, `PriorityPill`, buttons/inputs/tables restyled, motion
  tokens. Before/after screenshots.
- **B. Signature screens** — dashboard (ref 01), priority queue, investigation workspace (ref 02) with source comparison
  cards, evidence connector and sticky decision panel.
- **C. Interactions** — upload pipeline (ref 03) with a CSS-3D document-layer scene (lazy, reduced-motion fallback; no
  three.js unless it clearly beats CSS 3D), Copilot answer cards and sources (ref 04), insights charts (Recharts),
  shared-element transitions (queue row → workspace), sign-in brand scene.
- **D. Whole app** — inbox, invoice detail tabs, suppliers, POs (ordered vs received), knowledge, audit, settings,
  evaluation, observability, auth pages, empty/error/loading states, mobile.
- **E. Proof** — typecheck, lint, unit tests, build, Playwright incl. a11y scan (0 violations), screenshots desktop/mobile ×
  he/en × light/dark, finish review, DESIGN.md rewritten to match.

## Risks
- Contrast on pale/glass surfaces (check every text token ≥ 4.5:1 on its real background).
- Glass/blur cost on scrolling surfaces: blur only on fixed shell and hero, never on tables.
- Bundle: no new 3D dependency without a measured win; Recharts already lazy on chart pages.
