"use client";

import { AlertTriangle, BadgeCheck, CircleDot, FileSearch, FileText, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { pickLang, useI18n } from "@/lib/i18n";
import { priorityReasonText } from "@/lib/review";
import type { PriorityReason } from "@/lib/types";
import { cx } from "./ui";
import { label as labelOf } from "@/lib/i18n/label";

type Tone = "neutral" | "ok" | "warn" | "danger" | "info" | "accent" | "ai";
const TONE: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-2 ring-line-strong/60",
  ok: "bg-ok-soft text-ok ring-ok/20",
  warn: "bg-warn-soft text-warn ring-warn/25",
  danger: "bg-danger-soft text-danger ring-danger/20",
  info: "bg-info-soft text-info ring-info/20",
  accent: "bg-accent-soft text-accent-ink ring-accent/20",
  ai: "bg-ai-soft text-ai ring-ai-line",
};

const STATUS_TONE: Record<string, Tone> = {
  processing: "info", queued: "info", running: "info", needs_review: "warn", pending_info: "warn", pending: "warn",
  awaiting_approval: "info", reconciled: "ok", exception: "warn", failed: "danger", blocked: "danger",
  rejected: "neutral", approved: "ok", resolved: "ok", completed: "ok", succeeded: "ok", indexed: "ok", matched: "ok",
  received: "ok", on_hold: "warn", draft: "neutral", open: "neutral", discrepancies: "warn", partially_received: "warn",
  escalated: "warn",
};

export function PriorityBadge({ level }: { level: string }) {
  const { t } = useI18n();
  return <Pill tone={level === "critical" ? "danger" : level === "high" ? "warn" : "info"}>
    {(t.review as Record<string, unknown>)[level] as string ?? level}
  </Pill>;
}

export function ReasonText({ reason, currency }: { reason: PriorityReason; currency?: string | null }) {
  const { t } = useI18n();
  return <span>{priorityReasonText(t, reason, currency)}</span>;
}

export function Pill({ tone = "neutral", children, className, icon }: {
  tone?: Tone; children: React.ReactNode; className?: string; icon?: React.ReactNode;
}) {
  return (
    <span className={cx("inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full px-2 text-xs font-medium ring-1 ring-inset", TONE[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const { t } = useI18n();
  const label = labelOf(t.status, status);
  return (
    <Pill tone={STATUS_TONE[status] ?? "neutral"} icon={<CircleDot className="h-3 w-3" aria-hidden />}>
      {label}
    </Pill>
  );
}

export function SeverityDot({ severity }: { severity: string }) {
  const { t } = useI18n();
  const c = severity === "critical" ? "bg-danger" : severity === "warning" ? "bg-warn" : "bg-info";
  // the colour alone is not enough: the dot is a named image, in the reader's language
  const label = labelOf(t.severity, severity);
  return <span role="img" aria-label={label} title={label} className={cx("inline-block h-2 w-2 shrink-0 rounded-full", c)} />;
}

export function FindingTag({ type, severity }: { type: string; severity?: string }) {
  const { t } = useI18n();
  const label = labelOf(t.finding, type);
  const tone: Tone = severity === "critical" ? "danger" : severity === "warning" ? "warn" : severity === "info" ? "info" : "neutral";
  return <Pill tone={tone}>{label}</Pill>;
}

export function ActionLabel({ action }: { action: string | null | undefined }) {
  const { t } = useI18n();
  if (!action) return <>—</>;
  return <>{labelOf(t.action, action)}</>;
}

/** Container for anything a model (or offline template) wrote. Never used for verified data. */
export function AiBlock({ mode, children, className, title }: {
  mode?: string | null; children: React.ReactNode; className?: string; title?: string;
}) {
  const { t } = useI18n();
  const offline = !mode || mode.startsWith("offline");
  return (
    <div className={cx("rounded-lg border border-ai-line bg-ai-soft/60", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ai-line/70 px-4 py-2">
        <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-ai">
          <FileSearch className="h-4 w-4" aria-hidden />
          {title ?? t.ai.generated}
        </span>
        <span className="text-xs text-ai/80">{offline ? t.ai.template : `${t.ai.liveMode}: ${mode?.replace("llm:", "")}`}</span>
      </div>
      <div className="px-4 py-3">{children}</div>
      <p className="border-t border-ai-line/70 px-4 py-2 text-xs text-ai/90">{t.ai.advisory}</p>
    </div>
  );
}

export function VerifiedTag({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-ok">
      <BadgeCheck className="h-3.5 w-3.5" aria-hidden />
      {label ?? t.ai.verified}
    </span>
  );
}

export type CitationT = {
  title: string; page: number; quote: string; document_id?: string | null; section?: string | null;
  doc_type?: string; effective_date?: string | null; chunk_id?: string;
};

export function Citation({ c, index }: { c: CitationT; index?: number }) {
  const { t, locale } = useI18n();
  const href = c.document_id
    ? `/documents/${c.document_id}?page=${c.page}&q=${encodeURIComponent(c.quote.slice(0, 160))}&title=${encodeURIComponent(c.title)}`
    : undefined;
  const body = (
    <>
      <div className="flex items-center gap-1.5 text-xs text-ink-3">
        {index !== undefined && (
          <span className="grid h-4 min-w-4 place-items-center rounded bg-ai/15 px-1 text-2xs font-semibold text-ai">{index}</span>
        )}
        <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span className="truncate font-medium text-ink-2">{c.title}</span>
        <span className="shrink-0">· {t.common.page_short} {c.page}</span>
        {c.effective_date && <span className="shrink-0 ltr">· {c.effective_date}</span>}
      </div>
      <blockquote dir="auto" className="mt-1.5 border-s-2 border-ai-line ps-2.5 text-sm leading-relaxed text-ink">
        “{c.quote}”
      </blockquote>
    </>
  );
  void locale;
  return href ? (
    <Link href={href} className="block rounded-md border border-line bg-surface p-2.5 transition-colors hover:border-ai-line hover:bg-ai-soft/40" title={t.ai.openSource}>
      {body}
    </Link>
  ) : (
    <div className="rounded-md border border-line bg-surface p-2.5">{body}</div>
  );
}

export function SecurityNotice({ items }: { items: { message: string; snippets?: string[] }[] }) {
  const { t } = useI18n();
  if (!items?.length) return null;
  return (
    <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft px-4 py-3">
      <p className="flex items-center gap-2 text-sm font-semibold text-danger">
        <ShieldAlert className="h-4 w-4" aria-hidden /> {t.invoice.security}
      </p>
      {items.map((it, i) => (
        <div key={i} className="mt-1.5 text-sm text-ink">
          <p>{it.message}</p>
          {it.snippets?.slice(0, 2).map((s, j) => (
            <code key={j} dir="auto" className="mt-1 block rounded bg-surface/80 px-2 py-1 font-mono text-xs text-ink-2">{s}</code>
          ))}
        </div>
      ))}
    </div>
  );
}

export function WarningList({ items }: { items: { code: string; message: string }[] }) {
  if (!items?.length) return null;
  return (
    <ul className="space-y-1.5">
      {items.map((w, i) => (
        <li key={i} className="flex gap-2 text-sm text-ink-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
          <span><span className="font-mono text-xs text-ink-3">{w.code}</span> — {w.message}</span>
        </li>
      ))}
    </ul>
  );
}

export function AiText({ value }: { value: Record<string, string> | string | null | undefined }) {
  const { locale } = useI18n();
  return <span dir="auto">{pickLang(value, locale)}</span>;
}
