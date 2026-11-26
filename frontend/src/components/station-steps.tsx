"use client";

import { Check } from "lucide-react";
import { cx } from "./ui";

/** A horizontal stepper of named stations. ``current`` is the active index (-1 = nothing yet); with ``done`` the
 *  last station is complete too. ``detail`` (a real job percentage) shows under the active station. */
export function StationSteps({ names, current, done = false, detail }: { names: string[]; current: number; done?: boolean; detail?: string }) {
  return (
    <ol className="flex w-full items-start">
      {names.map((name, i) => {
        const complete = i < current || (done && i <= current);
        const active = i === current && !done;
        return (
          <li key={name} className="relative flex min-w-0 flex-1 flex-col items-center gap-2 text-center" aria-current={active ? "step" : undefined}>
            {i < names.length - 1 && <span aria-hidden className={cx("absolute top-[13px] h-[3px] w-full rounded-full ltr:left-1/2 rtl:right-1/2",
              i < current || (done && i < current) ? "bg-accent" : "bg-ink/[.08]")} />}
            <span aria-hidden className={cx("relative z-[1] grid h-7 w-7 place-items-center rounded-full border-2 transition-colors",
              complete && "border-accent bg-accent text-white",
              active && "border-accent bg-surface ring-4 ring-accent/20",
              !complete && !active && "border-ink/15 bg-surface")}>
              {complete && <Check className="h-4 w-4" strokeWidth={3} />}
              {active && <span className="h-2.5 w-2.5 rounded-full bg-accent" />}
            </span>
            <span className={cx("max-w-full break-words px-1 text-sm leading-tight", active || complete ? "font-bold text-ink" : "text-ink-3")}>{name}</span>
            {active && detail && <span className="-mt-1 text-xs font-bold text-accent num">{detail}</span>}
          </li>
        );
      })}
    </ol>
  );
}
