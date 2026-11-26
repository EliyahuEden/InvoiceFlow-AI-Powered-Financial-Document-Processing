"use client";

import { Building2, CalendarDays, Coins, Hash } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cx } from "./ui";

export type ExtractedFields = { supplier: string | null; number: string | null; date: string | null; total: string | null };

/**
 * Document to data: frosted invoice sheets in CSS 3D beside the four fields read from them. The scan line runs only
 * while a real job is processing (``active``) and stops when it ends; reduced motion turns it off. Field values come
 * from the most recent finished invoice; before any, each card says plainly that no value has been read yet, never sample data.
 */
export function ExtractionScene({ fields, active, sourceName }: { fields: ExtractedFields | null; active: boolean; sourceName?: string }) {
  const { t } = useI18n();
  const rows = [
    { icon: Building2, label: t.invoice.supplierName, value: fields?.supplier },
    { icon: Hash, label: t.invoice.invoiceNumber, value: fields?.number, ltr: true },
    { icon: CalendarDays, label: t.invoice.invoiceDate, value: fields?.date },
    { icon: Coins, label: t.invoice.total, value: fields?.total, ltr: true },
  ];
  const sheet = "absolute inset-0 rounded-[26px] border border-white/70 dark:border-white/10 shadow-[0_40px_70px_-36px_rgb(70_66_160/.55),inset_0_1px_0_rgb(255_255_255/.95)]";
  return (
    <div className="relative grid min-h-[330px] grid-cols-1 items-center gap-6 overflow-hidden rounded-2xl px-6 py-8 sm:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_70%_at_30%_40%,rgb(var(--atmosphere-a)/.55),transparent_70%),radial-gradient(50%_60%_at_80%_80%,rgb(var(--atmosphere-c)/.6),transparent_70%)]" />
      <div aria-hidden className="relative mx-auto h-[250px] w-[210px] [perspective:1000px]">
        <div className="relative h-full w-full [transform-style:preserve-3d] [transform:rotateX(10deg)_rotateY(22deg)_rotateZ(-6deg)] rtl:[transform:rotateX(10deg)_rotateY(-22deg)_rotateZ(6deg)]">
          <div className={cx(sheet, "bg-gradient-to-br from-[#c7d2fe]/70 to-[#e0e7ff]/40 dark:from-[#4338ca]/35 dark:to-[#1e1b4b]/30 [transform:translateZ(-70px)_translate(34px,-26px)] rtl:[transform:translateZ(-70px)_translate(-34px,-26px)]")} />
          <div className={cx(sheet, "bg-gradient-to-br from-[#ddd6fe]/75 to-[#eef2ff]/50 dark:from-[#5b21b6]/35 dark:to-[#1e1b4b]/35 [transform:translateZ(-35px)_translate(17px,-13px)] rtl:[transform:translateZ(-35px)_translate(-17px,-13px)]")} />
          <div className={cx(sheet, "overflow-hidden bg-gradient-to-br from-white/95 to-[#f5f3ff]/85 dark:from-[#25233f]/95 dark:to-[#1a1830]/90 p-5 backdrop-blur-md")}>
            <span className="block h-3 w-1/2 rounded-full bg-[#a5b4fc]/70" />
            <span className="mt-2 block h-2 w-1/3 rounded-full bg-[#c4b5fd]/60" />
            <div className="mt-5 space-y-2">
              {[0, 1, 2, 3].map((i) => <span key={i} className="block h-2 rounded-full bg-[#e0e7ff] dark:bg-white/10" style={{ width: `${88 - i * 9}%` }} />)}
            </div>
            <div className="mt-6 space-y-2 rounded-xl bg-[#eef2ff]/80 p-3 dark:bg-white/5">
              <span className="block h-2 w-3/4 rounded-full bg-[#c7d2fe]" />
              <span className="block h-2 w-2/3 rounded-full bg-[#c7d2fe]" />
              <span className="block h-2.5 w-1/2 rounded-full bg-[#a78bfa]/70" />
            </div>
            {active && <span className="absolute inset-x-0 top-0 h-16 animate-[scan_1.8s_ease-in-out_infinite] bg-gradient-to-b from-transparent via-[#a78bfa]/35 to-transparent" />}
          </div>
        </div>
      </div>
      <ul className="relative space-y-2.5" aria-label={t.upload.sceneTitle}>
        {rows.map(({ icon: Icon, label, value, ltr }) => (
          <li key={label} className="flex items-center gap-3 rounded-2xl border border-white/70 bg-surface/80 px-4 dark:border-white/10 py-3 shadow-[0_10px_28px_-18px_rgb(70_66_160/.5)] backdrop-blur">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><Icon className="h-5 w-5" aria-hidden /></span>
            <span className="min-w-0">
              <span className="block text-sm text-ink-3">{label}</span>
              {value ? <bdi className={cx("block truncate text-lg font-extrabold text-ink", ltr && "ltr num")}>{value}</bdi>
                : <span className="block text-base text-ink-3">{t.upload.noValueYet}</span>}
            </span>
          </li>
        ))}
        <li className="px-1 pt-1 text-sm text-ink-3">{fields ? <>{t.upload.readFrom} <bdi dir="auto">{sourceName}</bdi></> : t.upload.waiting}</li>
      </ul>
    </div>
  );
}
