"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { useSession } from "./session";

/** Inside a "Try the demo" workspace: whose data this is, and when it is deleted. */
export function SandboxBanner() {
  const { me } = useSession();
  const { t, locale } = useI18n();
  if (!me?.sandbox) return null;
  const at = me.sandbox.expires_at ? new Date(me.sandbox.expires_at) : null;
  const when = at ? new Intl.DateTimeFormat(locale === "he" ? "he-IL" : "en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit" }).format(at) : null;
  const b = t.sandbox;
  return (
    <div role="note" className="mx-auto mb-4 flex w-full max-w-[1520px] flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl border border-accent/20 bg-accent-soft/70 px-4 py-2.5 text-sm text-accent-ink">
      <FlaskConical className="h-4 w-4 shrink-0" aria-hidden />
      <span className="font-semibold">{b.title}</span>
      <span className="text-ink-2">{b.body}{when && <> {b.deleted} <bdi className="font-semibold text-ink">{when}</bdi>.</>}</span>
      <Link href="/signup" className="ms-auto font-semibold underline underline-offset-4 hover:text-ink">{b.signup}</Link>
    </div>
  );
}
