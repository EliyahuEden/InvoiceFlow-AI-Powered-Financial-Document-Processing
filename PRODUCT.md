# InvoiceFlow: product context

_Inferred from the project brief; there was no interview. Assumptions are marked (A)._

## What it is
A B2B SaaS workspace where accounts-payable and procurement teams process supplier invoices. It reads Hebrew and English documents, extracts their fields, reconciles them against purchase orders and goods receipts using deterministic rules, explains discrepancies with cited clauses from agreements and policies, and routes decisions to authorized humans.

## Who uses it
- **Procurement managers** upload invoices, keep supplier and PO master data current, and correct extraction errors.
- **Finance reviewers** decide exceptions, approve invoices for payment, and read the audit trail.
- **Administrators** configure tolerances, approval thresholds, and members.
- **Read-only users** (auditors, managers) inspect records.

Use scene (A): Israeli mid-size companies. People work at office desktops in daylight, sit in long sessions of queue work, and switch between Hebrew and English often within one record.

## Surface mode
Operate. The visitor completes a task. Scanability, trust, and consistency beat expression.

## Principles
1. **Verified vs. AI is always visible.** Business records and deterministic results look solid and factual. AI-generated text has its own consistent treatment and label, and it always links to its sources.
2. **Hebrew-first, truly bidirectional.** RTL is the default layout. Numbers, SKUs and PO numbers stay LTR inside RTL text, and documents render in their own direction.
3. **Every number is traceable.** Each number shows where it came from: a document location, a calculation, or a record.
4. **Calm density.** Queues and tables hold many rows. Colour is kept for state, never decoration.

## Constraints
- No automatic payments, ever. AI output is advisory.
- Offline demo mode must be labelled clearly. It never passes off templates as model output.
