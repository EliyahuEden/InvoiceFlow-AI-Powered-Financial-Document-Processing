"use client";

import { Check, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import type { InvoiceDetail } from "@/lib/types";
import { cx } from "./ui";

type State = "done" | "current" | "todo" | "stopped";

/** Where an invoice is on its way from upload to payment, from its status and payment record. */
export function journeyStates(inv: Pick<InvoiceDetail, "status" | "payment">): State[] {
  const paid = inv.payment?.status === "paid";
  switch (inv.status) {
    case "processing": return ["done", "current", "todo", "todo", "todo", "todo"];
    case "failed": return ["done", "stopped", "todo", "todo", "todo", "todo"];
    case "exception": case "on_hold": case "needs_review": return ["done", "done", "done", "current", "todo", "todo"];
    case "reconciled": return ["done", "done", "done", "done", "current", "todo"];
    case "rejected": return ["done", "done", "done", "done", "stopped", "todo"];
    case "approved": return paid ? ["done", "done", "done", "done", "done", "done"] : ["done", "done", "done", "done", "done", "current"];
    default: return ["done", "done", "todo", "todo", "todo", "todo"];
  }
}

/** The invoice journey as one disciplined line of stations: uploaded, read, matched, reviewed, approved, paid. */
export function StationLine({ invoice }: { invoice: Pick<InvoiceDetail, "status" | "payment"> }) {
  const { t } = useI18n();
  const j = t.invoice.journey;
  const names = [j.uploaded, j.read, j.matched, j.reviewed, j.approved, j.paid];
  const states = journeyStates(invoice);
  return (
    <ol aria-label={j.title} className="flex w-full max-w-2xl items-start">
      {names.map((name, i) => {
        const s = states[i] ?? "todo";
        const nextDone = (states[i + 1] ?? "todo") !== "todo";
        return (
          <li key={name} className="relative flex min-w-0 flex-1 flex-col items-center gap-1.5 last:flex-none" aria-current={s === "current" ? "step" : undefined}>
            {i < names.length - 1 && (
              <span aria-hidden className={cx("absolute top-[7px] h-px w-full ltr:left-1/2 rtl:right-1/2", nextDone ? "bg-accent/70" : "bg-ink/[.12]")} />
            )}
            <span aria-hidden className={cx("relative z-[1] grid h-[15px] w-[15px] place-items-center rounded-full border",
              s === "done" && "border-accent bg-accent text-primary-ink",
              s === "current" && "border-accent bg-bg ring-[3px] ring-accent/25",
              s === "todo" && "border-ink/20 bg-bg",
              s === "stopped" && "border-danger bg-danger text-primary-ink")}>
              {s === "done" && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
              {s === "stopped" && <X className="h-2.5 w-2.5" strokeWidth={3} />}
              {s === "current" && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}
            </span>
            <span className={cx("truncate text-2xs", s === "current" ? "font-medium text-ink" : s === "stopped" ? "text-danger" : s === "done" ? "text-ink-2" : "text-ink-3")}>
              {name}<span className="sr-only">{` — ${j[s]}`}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
