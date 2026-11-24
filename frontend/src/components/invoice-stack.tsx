"use client";

import { Check } from "lucide-react";
import { cx } from "./ui";

/**
 * Decorative Aurora emblem: three frosted invoice sheets stacked in CSS 3D, the top one carrying a verified mark.
 * Pure CSS (no 3D library), purely decorative (aria-hidden), and it settles once: no looping motion. Under reduced
 * motion the entrance is skipped by the global rule and the stack simply sits still.
 */
export function InvoiceStack({ className, label }: { className?: string; label: string }) {
  const sheet = "absolute inset-0 rounded-[22px] border border-white/70 dark:border-white/10 shadow-[0_30px_60px_-30px_rgb(70_66_160/.45),inset_0_1px_0_rgb(255_255_255/.9)]";
  return (
    <div aria-hidden className={cx("pointer-events-none select-none [perspective:900px]", className)}>
      <div className="relative h-full w-full animate-[stack-in_900ms_cubic-bezier(.16,1,.3,1)_both] [transform-style:preserve-3d] [transform:rotateX(14deg)_rotateY(-26deg)_rotateZ(6deg)]">
        <div className={cx(sheet, "bg-gradient-to-br from-[#c7d2fe]/70 to-[#e0e7ff]/40 dark:from-[#4338ca]/35 dark:to-[#1e1b4b]/30 [transform:translateZ(-56px)_translate(-26px,30px)]")} />
        <div className={cx(sheet, "bg-gradient-to-br from-[#ddd6fe]/80 to-[#eef2ff]/50 dark:from-[#5b21b6]/35 dark:to-[#1e1b4b]/35 [transform:translateZ(-28px)_translate(-13px,15px)]")} />
        <div className={cx(sheet, "overflow-hidden bg-gradient-to-br from-white/95 to-[#f5f3ff]/80 dark:from-[#25233f]/95 dark:to-[#1a1830]/90 p-5 backdrop-blur-md")}>
          <p className="text-end text-lg font-extrabold text-[#3f3a8a]/80 dark:text-[#c7d2fe]/80">{label}</p>
          <div className="mt-4 space-y-2.5">
            <span className="block h-2 w-4/5 rounded-full bg-[#a5b4fc]/60" />
            <span className="block h-2 w-3/5 rounded-full bg-[#c4b5fd]/60" />
            <span className="block h-2 w-2/3 rounded-full bg-[#a5b4fc]/50" />
          </div>
          <div className="mt-5 space-y-2">
            <span className="block h-1.5 w-full rounded-full bg-[#e0e7ff] dark:bg-white/10" />
            <span className="block h-1.5 w-full rounded-full bg-[#e0e7ff] dark:bg-white/10" />
            <span className="block h-1.5 w-5/6 rounded-full bg-[#e0e7ff] dark:bg-white/10" />
          </div>
          <span className="absolute bottom-4 start-4 grid h-10 w-10 place-items-center rounded-full bg-gradient-to-br from-[#a78bfa] to-[#818cf8] text-white shadow-[0_8px_20px_-6px_rgb(99_102_241/.7)]">
            <Check className="h-5 w-5" strokeWidth={3} />
          </span>
        </div>
      </div>
    </div>
  );
}
