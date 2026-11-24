---
name: "InvoiceFlow"
description: "Aurora Finance OS: a light, atmospheric financial-operations workspace. Frosted shell, opaque white evidence, one indigo voice."
colors:
  bg: "rgb(243 244 252)"
  surface: "rgb(255 255 255)"
  sunken: "rgb(245 246 252)"
  ink: "rgb(16 18 36)"
  ink-2: "rgb(70 74 98)"
  ink-3: "rgb(98 102 126)"
  line: "rgb(34 38 92 / 0.10)"
  line-strong: "rgb(170 174 204)"
  rule: "rgb(224 226 242)"
  accent: "rgb(88 76 214)"
  accent-soft: "rgb(237 235 254)"
  accent-ink: "rgb(62 52 168)"
  primary: "rgb(20 22 38)"
  primary-hover: "rgb(40 43 64)"
  primary-ink: "rgb(255 255 255)"
  ok: "rgb(18 110 52)"
  ok-soft: "rgb(228 246 235)"
  warn: "rgb(156 70 6)"
  warn-soft: "rgb(254 243 222)"
  danger: "rgb(186 26 46)"
  danger-soft: "rgb(255 233 236)"
  ai: "rgb(104 72 226)"
  ai-soft: "rgb(246 244 255)"
  ai-line: "rgb(222 216 252)"
  highlight: "rgb(250 204 21)"
  rail-active: "rgb(233 232 253)"
  atmosphere-periwinkle: "rgb(214 214 255)"
  atmosphere-ice: "rgb(214 236 255)"
  atmosphere-lavender: "rgb(241 232 255)"
  copy-invoice: "rgb(88 76 214)"
  copy-po: "rgb(2 132 199)"
  copy-gr: "rgb(21 128 61)"
  series-1: "#6a5ae0"
  series-2: "#d18a1f"
  series-3: "#1f9d5c"
  series-4: "#8b90b0"
  dark-bg: "rgb(10 10 16)"
  dark-surface: "rgb(19 19 28)"
  dark-ink: "rgb(237 237 245)"
  dark-accent: "rgb(156 146 255)"
typography:
  display:
    fontFamily: "Assistant, system-ui, sans-serif"
    fontSize: "3.75rem"
    fontWeight: 800
    lineHeight: "3.9rem"
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Assistant, system-ui, sans-serif"
    fontSize: "2.125rem"
    fontWeight: 800
    lineHeight: "2.5rem"
    letterSpacing: "-0.02em"
  figure:
    fontFamily: "Assistant, system-ui, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 800
    lineHeight: "2.5rem"
    letterSpacing: "-0.02em"
    fontFeature: "tnum, lnum"
  title:
    fontFamily: "Assistant, system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 700
    lineHeight: "1.65rem"
  body:
    fontFamily: "Assistant, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: "1.45rem"
  label:
    fontFamily: "Assistant, system-ui, sans-serif"
    fontSize: "0.84375rem"
    fontWeight: 600
    lineHeight: "1.25rem"
  code:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "0.78125rem"
    fontWeight: 400
    lineHeight: "1.125rem"
rounded:
  sm: "8px"
  control: "10px"
  button: "12px"
  lg: "14px"
  panel: "18px"
  hero: "22px"
  scene: "26px"
  pill: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "20px"
  xl: "24px"
  2xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.button}"
    height: "40px"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    height: "40px"
    padding: "0 16px"
  button-ghost:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.button}"
    height: "40px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    height: "40px"
    padding: "0 12px"
  card-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
  card-metric:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "18px 20px"
  nav-item-active:
    backgroundColor: "{colors.rail-active}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.lg}"
    height: "44px"
  pill-state:
    rounded: "{rounded.sm}"
    height: "24px"
    padding: "0 8px"
---

# Design System: InvoiceFlow

## Overview

**Creative North Star: "The Clear Morning Ledger"**

InvoiceFlow is a finance team's daily workspace for checking invoices against purchase orders and receipts. The Aurora system makes that work feel calm and lit from outside. A still, pale atmosphere of periwinkle, ice blue and lavender sits on the page ground. A frosted shell (sidebar, top bar, the dashboard hero) floats over it. Everything that carries evidence (invoices, tables, forms, findings, decisions) sits on opaque white, crisp and readable. The material makes a promise: the decoration stays outside the numbers.

Light is the flagship theme. Dark is a separately art-directed graphite theme with the same indigo voice, not an inversion. Density is moderate. The dashboard and workspace are scan-first Operate surfaces, while the sign-in brand panel and the upload scene carry the system's one expressive moment each: CSS-3D frosted invoice sheets.

Hebrew is the primary language and the layout is RTL-first, with English as an equal. Every spacing and direction rule is logical (start/end), and codes, numbers and IDs are isolated left-to-right.

**Key Characteristics:**
- Atmosphere on the page ground only, never behind data inside a card.
- Glass on the shell and hero; opaque white for everything else.
- One near-black primary button per view; indigo-violet for selection, focus and AI.
- Red, amber and green mean business state, nothing else.
- Heavy, tight headings in Assistant; tabular numerals everywhere money appears.
- 3D emblems are decorative, aria-hidden and still after their entrance.

## Colors

A cool, low-saturation navy-tinted neutral ramp carries the surfaces. One indigo-violet accent carries interaction. Three restrained state colours carry meaning.

### Primary
- **Ink Black Button** (primary): the single strongest action on a view, such as "review next invoice", "approve" or "upload". It is near-black, not a hue, so it never competes with state colours.
- **Aurora Indigo** (accent): selection, focus rings, the active nav item, links, chart series 1 and the invoice copy in the three-way match. Its soft tint (accent-soft) backs active and hover states. Accent-ink is the readable text version on that tint.

### Secondary
- **Assistant Violet** (ai, ai-soft, ai-line): marks AI-produced content only, such as the Copilot tile, the AI/offline mode badge and AI evidence labels. It is never used for actions.

### Tertiary
- **Source copy colours** (copy-invoice indigo, copy-po sky, copy-gr green): identify the three documents in a three-way match. Sky blue is deliberately not red: a PO copy is a source, not a finding.

### Neutral
- **Morning Mist** (bg): the page ground under the atmosphere.
- **Paper White** (surface): every card, table, form and evidence panel.
- **Shadow Mist** (sunken): wells, table headers, hovered secondary buttons.
- **Deep Navy Ink** (ink), **Slate Ink** (ink-2), **Quiet Ink** (ink-3): primary, secondary and muted text. Ink-3 still meets 4.5:1 on white.
- **Navy Hairline** (line): the navy at 10% alpha for every border. Line-strong is for emphasized borders and scrollbars.
- **Atmosphere washes** (periwinkle, ice, lavender): three radial gradients on `body`, fixed, at 45–55% alpha. They are also reused at low alpha inside the brand panel, the upload scene and the Copilot panel header.

### Named Rules
**The State Means Money Rule.** Red, amber and green appear only where a real business state exists: an open finding of that type, an overdue invoice, a completed receipt. A decorative red or a "nice" green is a bug.

**The One Voice Rule.** Indigo is the only interactive hue. A second accent colour for buttons or links is not allowed.

## Typography

**Body Font:** Assistant (with system-ui), weights 400–800, Hebrew + Latin.
**Mono Font:** Geist Mono, for invoice numbers, SKUs, PO numbers and IDs only.

**Character:** Assistant runs a small x-height, so the scale starts at 15px and headings carry real weight (700–800) with tight tracking. The result is confident and modern without a display face.

### Hierarchy
- **Display** (800, 3.75rem, -0.03em): the hero count on the dashboard ("needs review"). It is used once per view at most.
- **Headline** (800, 2.125rem): the page title (`PageHeader` h1) and greetings.
- **Figure** (800, 2.25rem, tabular): KPI card numbers.
- **Title** (700, 1.1875rem): panel headers.
- **Body** (400, 0.9375rem / 1.45rem): all running text and table cells.
- **Label** (600, 0.84375rem): field labels, pills, buttons (buttons are semibold).
- **Code** (Geist Mono 400, 0.78125rem): codes and identifiers inside `<bdi>`, left-to-right.

### Named Rules
**The Tabular Money Rule.** Every number that can be compared uses tabular, lining numerals (`.num`, all table cells). Amounts stay in their own currency and are never summed across currencies.

**The Mono Is For Codes Rule.** Geist Mono never sets prose, headings or amounts.

## Layout

The app shell is a 256px frosted sidebar on the start side plus a 64px transparent top bar with a pill search. Content is capped (`mx-auto`) and fluid inside. The dashboard runs hero → three KPI cards → queue (plus a 340px currency exposure panel when more than one currency is open). The investigation workspace is three columns at 1280px and up (evidence 1.25fr, findings 1.05fr, decision 0.85fr). Evidence and decision are sticky there; below 1280px everything stacks in reading order.

Spacing follows a 4px grid. Typical values are 16px gaps between cards, 18–20px card padding, 24–28px hero padding, and 12–16px on phones. Tables fall back to stacked list items below `lg`, with no horizontal page scroll at 375px.

## Elevation & Depth

A hybrid system. Depth comes from three soft, navy-tinted shadows plus surface material (glass and opaque). It is never from colour glows. On dark, shadows become black and depth leans on surface steps and hairlines.

### Shadow Vocabulary
- **Panel** (`0 1px 2px rgb(34 38 92 / .04), 0 14px 36px -18px rgb(70 66 160 / .22)`): every resting card.
- **Hero** (`inset 0 1px 0 rgb(255 255 255 / .9), 0 20px 50px -24px rgb(70 66 160 / .30)`): the frosted hero, giving it an inner top highlight.
- **Pop** (`0 24px 60px -18px rgb(46 42 120 / .30), 0 0 0 1px rgb(34 38 92 / .06)`): dialogs, the Copilot panel, the command palette, toasts.

### Named Rules
**The Glass Stops At The Data Rule.** `backdrop-filter` is used only on `.shell-glass` (sidebar, top bar) and `.command-hero`, never on tables, evidence, forms or scrolling lists.

## Shapes

Corners are generous and nested: 8px small chips and pills, 10px controls, 12px buttons and inputs, 14px nav items, 18px panels and KPI cards, 22px hero, 26px 3D scene sheets, full pills for search, filter chips and Copilot suggestions. Borders are always the navy hairline. State pills are 24px tall with a 1px tinted border.

## Components

### Buttons
- **Shape:** gently rounded (12px). Sizes are sm 32px, md 40px, lg 48px, icon 40px. Labels are semibold.
- **Primary:** near-black with white text, a faint inner top highlight and a soft dark drop shadow. Hover lifts to primary-hover.
- **Secondary:** white with a hairline and a 1px soft shadow. Hover darkens the border and moves to the sunken surface.
- **Ghost:** ink-2 text, with an indigo 7% wash on hover.
- **Danger:** white with a danger-tinted border and danger text. Hover moves to danger-soft.
- **Focus:** a 2px indigo outline, offset 2px, on every interactive element.

### Chips / Pills
- **State pills:** 24px, rounded 8px, bold label, soft state background, matching 1px border.
- **Suggestion chips** (Copilot, filters): full pill, white, semibold. Hover moves to an indigo tint with accent-ink text.

### Cards / Containers
- **Panel and metric cards:** opaque white, 18px radius, hairline border, panel shadow. Metric cards may carry a faint state-tinted gradient and a round icon tile.
- **Hero:** frosted glass at 62–82% white, blur 18px, 22px radius, hero shadow.

### Inputs / Fields
- **Style:** white, hairline border, 12px radius, 40px tall.
- **Focus:** indigo border plus a 4px indigo ring at 15%.
- **Error:** danger border and inline danger text tied with `aria-describedby`.

### Navigation
- **Top bar:** sticky, a near-opaque page-ground fill (95%) with blur and a hairline bottom border, so content never shows through it.
- **Sidebar:** frosted, with grouped sections under small muted labels. Items are 44px with 14px radius. The active item gets the rail-active indigo tint and accent-ink text; hover gets a faint ink wash. The user card sits at the bottom.
- **Mobile:** the sidebar becomes a sheet, opened from the top bar.

### Carbon-Copy Three-Way Match (signature)
The invoice, PO and receipt lines are stacked as offset copies (6px per copy, drifting toward the reading direction). Each copy uses its source colour. The mismatched quantity or price is struck through in red pen (`.red-pen-struck`) only when a real finding exists.

### Source Compare and Evidence Trace
In the workspace, three source cards compare the invoice subtotal, the ordered value of the matched PO lines and the received value. A card is red only with an open finding of that type. Evidence Trace rows list each extracted field with its page. Clicking a row highlights the field on the document. The document zooms to at least 160% and centres the box (a line wider than the frame aligns to its figures end). A dashed indigo connector runs from the row to the box on wide screens (1280px and up). The workspace opens already focused on the first disputed line.

### Invoice Emblem and Extraction Scene
These are CSS-3D frosted invoice sheets (no 3D library), aria-hidden. They enter once (`stack-in`) and then stay still. The upload scan line runs only while a real job is processing. Field cards show real extracted values or empty placeholders, never sample data.

### Copilot Panel
This is a floating 24px-radius panel with an atmosphere header and a violet gradient tile. Each answer is a white card headed by a "verified against the records" or "unverified" line plus an AI/offline badge. Sources are listed as linked rows with their kind.

## Do's and Don'ts

### Do:
- **Do** keep evidence, tables and forms on opaque white (surface) with the panel shadow.
- **Do** use exactly one primary (near-black) button per view.
- **Do** put the atmosphere on `body` only. Reuse it at low alpha inside a scene or brand panel, never behind a table.
- **Do** isolate codes and amounts with `<bdi>` and `.ltr`, and use logical start/end properties.
- **Do** check every text token at 4.5:1 on its real background in both themes; axe must stay at zero violations.
- **Do** let decorative 3D settle once and respect reduced motion. Entrances are CSS keyframes, so server and client markup match.

### Don't:
- **Don't** use red, amber or green for decoration or for a source that is not a finding.
- **Don't** add `backdrop-filter` to anything that scrolls or holds data.
- **Don't** introduce a second interactive hue, gradient text or coloured glows.
- **Don't** show fabricated numbers, deltas or percentages. A visual without real data is replaced or omitted.
- **Don't** sum amounts across currencies.
- **Don't** set prose or amounts in Geist Mono.
